"""Unit tests for rsvp-converter/converter.py — synthetic inputs, all formats."""
import os, sys, io, zipfile, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "rsvp-converter"))

import converter


def _assert_valid_rsvp(text, label):
    assert text.startswith("@rsvp 1\n"), f"{label}: missing @rsvp header"
    assert "@title " in text, f"{label}: missing @title"
    assert "@author " in text, f"{label}: missing @author"
    assert re.search(r"^@chapter ", text, re.M), f"{label}: missing @chapter"
    assert re.search(r"^@para$", text, re.M), f"{label}: missing @para"
    # At least one bare word line.
    body_lines = [l for l in text.splitlines() if l and not l.startswith("@")]
    assert len(body_lines) >= 3, f"{label}: too few word lines ({len(body_lines)})"
    # No spaces in word lines (one word per line).
    for l in body_lines[:20]:
        assert " " not in l, f"{label}: multi-word line: {l!r}"


def test_txt():
    src = (
        "Chapter 1\n\nIt was a bright cold day in April,\n"
        "and the clocks were striking thirteen.\n\n"
        "Chapter 2\n\nWinston Smith pushed open the door.\n"
    ).encode()
    text, name = converter.convert("nineteen.txt", src, title="1984", author="Orwell")
    _assert_valid_rsvp(text, "txt")
    assert name == "nineteen.rsvp"
    assert text.count("@chapter ") == 2
    print("[PASS] txt")


def test_md():
    src = b"# My Book\n\n## Chapter One\n\nHello there friend.\n\n## Chapter Two\n\nMore words follow here.\n"
    text, name = converter.convert("notes.md", src, title="Notes", author="Me")
    _assert_valid_rsvp(text, "md")
    assert name == "notes.rsvp"
    assert text.count("@chapter ") >= 2
    print("[PASS] md")


def test_html():
    src = (
        b"<html><head><title>Doc</title></head><body>"
        b"<h1>Intro</h1><p>This is the opening paragraph here.</p>"
        b"<h2>Section</h2><p>Second paragraph with words.</p>"
        b"</body></html>"
    )
    text, name = converter.convert("doc.html", src, title="Doc", author="Anon")
    _assert_valid_rsvp(text, "html")
    assert name == "doc.rsvp"
    print("[PASS] html")


def _build_minimal_epub():
    """Build a tiny but valid EPUB 2 in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>'
            '</container>')
        z.writestr("OEBPS/content.opf",
            '<?xml version="1.0"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="2.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:title>Tiny Test Book</dc:title>'
            '<dc:creator>Test Author</dc:creator>'
            '<dc:identifier id="bookid">tiny-1</dc:identifier>'
            '<dc:language>en</dc:language>'
            '</metadata>'
            '<manifest>'
            '<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            '</manifest>'
            '<spine toc="ncx"><itemref idref="ch1"/></spine>'
            '</package>')
        z.writestr("OEBPS/toc.ncx",
            '<?xml version="1.0"?>'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
            '<head><meta name="dtb:uid" content="tiny-1"/></head>'
            '<docTitle><text>Tiny</text></docTitle>'
            '<navMap><navPoint id="n1" playOrder="1"><navLabel><text>Ch 1</text></navLabel><content src="ch1.xhtml"/></navPoint></navMap>'
            '</ncx>')
        z.writestr("OEBPS/ch1.xhtml",
            '<?xml version="1.0"?>'
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            '<head><title>Ch 1</title></head>'
            '<body><h1>Opening</h1><p>Once upon a time there was a small test.</p>'
            '<p>It had two paragraphs.</p></body></html>')
    return buf.getvalue()


def test_epub():
    src = _build_minimal_epub()
    text, name = converter.convert("tiny.epub", src)
    _assert_valid_rsvp(text, "epub")
    assert name == "tiny.rsvp"
    assert "Tiny Test Book" in text  # from EPUB metadata
    assert "Test Author" in text
    print("[PASS] epub")


def test_unsupported():
    try:
        converter.convert("x.pdf", b"%PDF-1.4")
    except ValueError:
        print("[PASS] unsupported rejected")
        return
    raise AssertionError("expected ValueError for .pdf")


if __name__ == "__main__":
    failures = 0
    for fn in [test_txt, test_md, test_html, test_epub, test_unsupported]:
        try:
            fn()
        except Exception as e:
            failures += 1
            print(f"[FAIL] {fn.__name__}: {e}")
    print(f"\n{'-'*40}")
    print(f"converter.py: {5 - failures}/5 passed")
    sys.exit(1 if failures else 0)
