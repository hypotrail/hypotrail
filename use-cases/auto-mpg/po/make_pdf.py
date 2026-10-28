"""Write the sample PO page as a PDF, for the workshop (owner remark R68, minimal version).

    python use-cases/auto-mpg/po/make_pdf.py

Reads ``fiche-cas-usage-mpg.md`` next to this script and writes ``fiche-cas-usage-mpg.pdf``.
A minimal pure-Python PDF writer, no dependency: A4 pages, the standard Helvetica fonts in
WinAnsi encoding (so ``pypdf`` extracts the French text as written), ``# `` and ``## ``
headings, ``- `` bullets, a line in ``**`` written in bold, ``<!-- page -->`` for a page
break, and a footer that says the scenario is fictitious. The output is deterministic.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'fiche-cas-usage-mpg.md'
TARGET = HERE / 'fiche-cas-usage-mpg.pdf'
WIDTH, HEIGHT, MARGIN = 595, 842, 64
FOOTER = 'Scénario fictif pour la simulation · Confluence « Produit véhicules » · page {n}/{total}'
# (font, size, leading, characters per line, indent, space before)
STYLES = {'h1': ('F2', 15, 20, 58, 0, 0), 'h2': ('F2', 12, 17, 74, 0, 10),
          'p': ('F1', 10, 14, 92, 0, 4), 'bold': ('F2', 10, 14, 86, 0, 6),
          'li': ('F1', 10, 14, 88, 14, 2), 'crumb': ('F1', 8, 12, 115, 0, 2)}


def _blocks(markdown: str) -> list[list[tuple[str, str]]]:
    """Pages of ``(style, text)`` blocks."""
    pages, blocks = [], []
    for line in markdown.splitlines():
        line = line.strip()
        if not line:
            continue
        if line == '<!-- page -->':
            pages.append(blocks)
            blocks = []
        elif line.startswith('# '):
            blocks.append(('h1', line[2:]))
        elif line.startswith('## '):
            blocks.append(('h2', line[3:]))
        elif line.startswith('- '):
            blocks.append(('li', line[2:]))
        elif line.startswith('**') and line.endswith('**'):
            blocks.append(('bold', line[2:-2]))
        elif line.startswith('Confluence >'):
            blocks.append(('crumb', line))
        else:
            blocks.append(('p', line))
    pages.append(blocks)
    return pages


def _text(value: str) -> bytes:
    data = value.encode('cp1252')          # fails loudly on a character WinAnsi lacks
    return data.replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')


def _page_stream(blocks, n: int, total: int) -> bytes:
    out, y = [], HEIGHT - MARGIN
    for style, text in blocks:
        font, size, leading, chars, indent, before = STYLES[style]
        y -= before
        lines = textwrap.wrap(text, chars - (2 if style == 'li' else 0))
        for i, line in enumerate(lines):
            y -= leading
            if y < MARGIN + 30:
                raise SystemExit(f'page {n} overflows; move a <!-- page --> break up')
            x = MARGIN + indent
            if style == 'li' and i == 0:
                out.append(b'BT /F1 %d Tf %d %d Td (' % (size, x - 10, y) + _text('•')
                           + b') Tj ET')
            out.append(b'BT /%s %d Tf %d %d Td (' % (font.encode(), size, x, y) + _text(line)
                       + b') Tj ET')
        if style == 'h1':
            y -= 4
    footer = FOOTER.format(n=n, total=total)
    out.append(b'BT /F1 8 Tf %d %d Td (' % (MARGIN, MARGIN - 24) + _text(footer) + b') Tj ET')
    return b'\n'.join(out)


def build(markdown: str) -> bytes:
    pages = _blocks(markdown)
    total = len(pages)
    # Objects: 1 catalog, 2 pages, 3 Helvetica, 4 Helvetica-Bold, then a page and its stream.
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', None,
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica '
               b'/Encoding /WinAnsiEncoding >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold '
               b'/Encoding /WinAnsiEncoding >>']
    kids = []
    for n, blocks in enumerate(pages, start=1):
        stream = _page_stream(blocks, n, total)
        page_id, stream_id = len(objects) + 1, len(objects) + 2
        kids.append(page_id)
        objects.append(b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] '
                       b'/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> '
                       b'/Contents %d 0 R >>' % (WIDTH, HEIGHT, stream_id))
        objects.append(b'<< /Length %d >>\nstream\n' % len(stream) + stream
                       + b'\nendstream')
    objects[1] = (b'<< /Type /Pages /Kids [' + b' '.join(b'%d 0 R' % k for k in kids)
                  + b'] /Count %d >>' % total)
    out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b'%d 0 obj\n' % i + body + b'\nendobj\n'
    xref = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)
    out += b''.join(b'%010d 00000 n \n' % o for o in offsets)
    out += (b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n'
            % (len(objects) + 1, xref))
    return bytes(out)


def main() -> int:
    TARGET.write_bytes(build(SOURCE.read_text(encoding='utf-8')))
    print(f'wrote {TARGET}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
