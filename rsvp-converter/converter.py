#!/usr/bin/env python3
"""
Book -> .rsvp converter for the rsvpnano ESP32-S3 reader.

.rsvp format (plain text, ASCII-ish):
    @rsvp 1
    @title <title>
    @author <author>
    @source <source>
    @chapter <chapter name>
    @para
    word
    word
    word
    @para
    word
    ...

Supported inputs: .epub, .txt, .md, .html
"""

import os
import re
import html
from io import BytesIO

from bs4 import BeautifulSoup
import markdown as md_lib


RSVP_HEADER = "@rsvp 1"

# Chapter headings in plain text files. Numbered, roman, "Prologue", etc.
_CHAPTER_RE = re.compile(
    r"^\s*(chapter\s+[ivxlcdm0-9]+|prologue|epilogue|part\s+[ivxlcdm0-9]+)\b.*$",
    re.IGNORECASE,
)

# Split words: keep contractions and intra-word punctuation, drop whitespace runs.
_WORD_RE = re.compile(r"\S+")


def _clean_text(text):
    """Normalise whitespace, strip control chars."""
    text = html.unescape(text)
    text = text.replace("\xa0", " ").replace("​", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _split_paragraphs(block):
    """Yield non-empty paragraphs from a multi-line block."""
    for para in re.split(r"\n\s*\n", block):
        para = para.strip()
        if para:
            yield " ".join(line.strip() for line in para.splitlines() if line.strip())


def _emit_paragraph(out, paragraph):
    words = _WORD_RE.findall(paragraph)
    if not words:
        return
    out.append("@para")
    out.extend(words)


def _emit_chapter(out, name):
    name = _clean_text(name) or "Chapter"
    out.append(f"@chapter {name}")


def _header(title, author, source):
    lines = [RSVP_HEADER]
    if title:
        lines.append(f"@title {_clean_text(title)}")
    if author:
        lines.append(f"@author {_clean_text(author)}")
    if source:
        lines.append(f"@source {_clean_text(source)}")
    return lines


# ── Format-specific parsers ───────────────────────────────────────────────────

def convert_txt(data, title=None, author=None, source=None):
    text = data.decode("utf-8", errors="replace")
    out = _header(title or "Untitled", author or "Unknown", source or "txt")

    current_chapter = None
    pending = []

    def flush():
        if not pending:
            return
        block = "\n".join(pending)
        for para in _split_paragraphs(block):
            _emit_paragraph(out, para)
        pending.clear()

    started = False
    for line in text.splitlines():
        if _CHAPTER_RE.match(line):
            flush()
            current_chapter = line.strip()
            _emit_chapter(out, current_chapter)
            started = True
            continue
        pending.append(line)

    if not started:
        # No chapter headings detected — wrap whole thing in one chapter.
        _emit_chapter(out, "Chapter 1")
    flush()
    return "\n".join(out) + "\n"


def convert_md(data, title=None, author=None, source=None):
    html_text = md_lib.markdown(data.decode("utf-8", errors="replace"))
    return _convert_html_string(html_text, title, author, source or "md")


def convert_html(data, title=None, author=None, source=None):
    return _convert_html_string(
        data.decode("utf-8", errors="replace"),
        title, author, source or "html",
    )


def _convert_html_string(html_text, title=None, author=None, source=None):
    soup = BeautifulSoup(html_text, "lxml")

    # Try to pull a title from <title> / <h1> if not supplied.
    if not title:
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.h1:
            title = soup.h1.get_text(strip=True)

    out = _header(title or "Untitled", author or "Unknown", source or "html")

    body = soup.body or soup
    chapter_opened = False

    for el in body.find_all(["h1", "h2", "h3", "p", "div", "blockquote", "li"]):
        if el.name in ("h1", "h2", "h3"):
            name = _clean_text(el.get_text(" "))
            if not name:
                continue
            _emit_chapter(out, name)
            chapter_opened = True
        else:
            text = _clean_text(el.get_text(" "))
            if not text:
                continue
            if not chapter_opened:
                _emit_chapter(out, "Chapter 1")
                chapter_opened = True
            _emit_paragraph(out, text)

    if not chapter_opened:
        # Last resort: dump raw text.
        text = _clean_text(body.get_text(" "))
        if text:
            _emit_chapter(out, "Chapter 1")
            _emit_paragraph(out, text)

    return "\n".join(out) + "\n"


def convert_epub(data, title=None, author=None, source=None):
    # Imported lazily — ebooklib is heavy.
    from ebooklib import epub, ITEM_DOCUMENT

    book = epub.read_epub(BytesIO(data))

    if not title:
        meta_title = book.get_metadata("DC", "title")
        if meta_title:
            title = meta_title[0][0]
    if not author:
        meta_author = book.get_metadata("DC", "creator")
        if meta_author:
            author = meta_author[0][0]

    out = _header(title or "Untitled", author or "Unknown", source or "epub")

    chapter_opened = False
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "lxml")
        # Each EPUB document = a chapter. Use its first heading or filename.
        heading_el = soup.find(["h1", "h2", "h3"])
        chapter_name = (
            _clean_text(heading_el.get_text(" "))
            if heading_el
            else os.path.splitext(os.path.basename(item.get_name()))[0]
        )
        if not chapter_name:
            chapter_name = "Chapter"
        _emit_chapter(out, chapter_name)
        chapter_opened = True

        for p in soup.find_all(["p", "blockquote", "li"]):
            text = _clean_text(p.get_text(" "))
            if text:
                _emit_paragraph(out, text)

    if not chapter_opened:
        _emit_chapter(out, "Chapter 1")

    return "\n".join(out) + "\n"


# ── Dispatcher ────────────────────────────────────────────────────────────────

_HANDLERS = {
    ".txt":  convert_txt,
    ".md":   convert_md,
    ".markdown": convert_md,
    ".html": convert_html,
    ".htm":  convert_html,
    ".epub": convert_epub,
}


def supported_extensions():
    return sorted(_HANDLERS.keys())


def convert(filename, data, title=None, author=None):
    """
    Convert raw file bytes -> .rsvp text. Dispatches by extension.
    Returns (rsvp_text, output_filename).
    """
    ext = os.path.splitext(filename)[1].lower()
    handler = _HANDLERS.get(ext)
    if handler is None:
        raise ValueError(f"Unsupported file type: {ext}")

    rsvp_text = handler(data, title=title, author=author, source=filename)
    base = os.path.splitext(os.path.basename(filename))[0]
    return rsvp_text, f"{base}.rsvp"
