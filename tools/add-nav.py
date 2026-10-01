#!/usr/bin/env python3
"""Put a consistent navigation bar at the top of every page of the collection.

Run it after adding new summary pages:

    python3 tools/add-nav.py                 # every tracked .html page
    python3 tools/add-nav.py shikshapatra    # just one section

What each page gets
-------------------
A summary page (``shikshapatra/2026-06-24.html``) gets two links:

    ← शिक्षापत्र            back to that section's list
    🏠 मुख्य पृष्ठ          back to the collection home

A section list (``shikshapatra/index.html``) gets only the home link, since its
own list is already the level above.

The collection home (``index.html``) is left alone — it carries the bar back to
pushtimarg.net instead.

The bar is sticky so it stays reachable however far down a long summary the
reader has scrolled; on a phone there is no browser back button on screen at all,
which is the whole reason this exists.

Re-running is safe: any bar this script previously inserted is stripped and
rewritten, so changing the design here updates every page.
"""
from __future__ import annotations

import html
import pathlib
import re
import subprocess
import sys
from collections import Counter

MARK_START = '<!-- nav:start -->'
MARK_END = '<!-- nav:end -->'
CSS_START = '/* nav:css:start */'
CSS_END = '/* nav:css:end */'

CSS = f"""{CSS_START}
  .ghnav{{position:sticky;top:0;z-index:950;display:flex;align-items:center;
    justify-content:center;gap:10px;flex-wrap:wrap;padding:9px 14px;
    background:linear-gradient(180deg,#FFD75E,#F0C832 55%,#D9A91C);
    border-bottom:2px solid #8E1A12;box-shadow:0 3px 12px rgba(0,0,0,.3);
    font-family:'Noto Serif Devanagari',Georgia,serif}}
  .ghnav a{{display:inline-flex;align-items:center;gap:7px;min-height:40px;
    padding:7px 16px;border-radius:999px;text-decoration:none;
    font-size:1rem;font-weight:700;line-height:1.2;transition:filter .15s}}
  .ghnav a:hover{{filter:brightness(1.08)}}
  .ghnav a:focus-visible{{outline:3px solid #3D0D00;outline-offset:2px}}
  .ghnav .nav-back{{background:#8E1A12;color:#FFD75E;
    box-shadow:0 1px 4px rgba(0,0,0,.3)}}
  .ghnav .nav-home{{background:rgba(255,255,255,.75);color:#3D0D00;
    border:1.5px solid rgba(61,13,0,.3)}}
  @media(max-width:520px){{
    .ghnav{{gap:7px;padding:8px 10px}}
    .ghnav a{{font-size:.92rem;padding:7px 13px;min-height:38px}}
  }}
  @media(prefers-reduced-motion:reduce){{.ghnav a{{transition:none}}}}
{CSS_END}
"""

HOME = '<a class="nav-home" href="{href}"><span aria-hidden="true">\U0001F3E0</span>मुख्य पृष्ठ</a>'
BACK = '<a class="nav-back" href="{href}"><span aria-hidden="true">←</span>{label}</a>'


# A few headings are too long to sit in the bar; these read better and still name
# the section unambiguously.
SHORT = {
    'subodhini-gujarati': 'सुबोधिनी — ગુજરાતી',
    'bhagavad-varta': 'भगवद् वार्ता',
    'vallabh-sukhdham': 'वल्लभ सुखधाम',
}


def section_label(folder: pathlib.Path) -> str:
    """Read a section's own heading so the back link says where it goes."""
    if folder.name in SHORT:
        return SHORT[folder.name]
    idx = folder / 'index.html'
    if not idx.exists():
        return folder.name
    s = idx.read_text(encoding='utf-8', errors='replace')
    m = re.search(r'<h1[^>]*>(.*?)</h1>', s, re.S) or re.search(r'<title>(.*?)</title>', s, re.S)
    if not m:
        return folder.name
    t = html.unescape(re.sub(r'<[^>]+>', '', m.group(1)))
    t = re.sub(r'\s+', ' ', t).strip().strip('॥').strip()
    # A long heading would wrap the bar onto two lines on a phone.
    return (t[:26] + '…') if len(t) > 27 else t


def strip_previous(s: str) -> str:
    """Remove a bar this script added before, so a re-run replaces rather than stacks."""
    s = re.sub(re.escape(MARK_START) + r'.*?' + re.escape(MARK_END), '', s, flags=re.S)
    s = re.sub(re.escape(CSS_START) + r'.*?' + re.escape(CSS_END), '', s, flags=re.S)
    # the first version of this bar, before it had markers
    s = re.sub(r'<a class="ghhome".*?</a>\n?', '', s, flags=re.S)
    s = re.sub(r'\n?\s*/\* Way back to the collection home.*?@media\(max-width:520px\)\{\.ghhome[^}]*\}\}\n?',
               '', s, flags=re.S)
    return s


def process(path: pathlib.Path) -> str:
    s = path.read_text(encoding='utf-8', errors='replace')
    s = strip_previous(s)

    parts = path.parts
    depth = len(parts) - 1
    links = []
    if depth and parts[-1] != 'index.html':
        links.append(BACK.format(href='index.html', label=section_label(path.parent)))
    links.append(HOME.format(href=('../' * depth) + 'index.html' if depth else 'index.html'))
    bar = f'{MARK_START}<nav class="ghnav">{"".join(links)}</nav>{MARK_END}\n'

    if '</style>' in s:
        i = s.index('</style>')
        s = s[:i] + CSS + s[i:]
    elif '</head>' in s:
        i = s.index('</head>')
        s = s[:i] + '<style>\n' + CSS + '</style>\n' + s[i:]
    else:
        return 'skipped-no-stylesheet'

    m = re.search(r'<body[^>]*>', s)
    if m:
        s = s[:m.end()] + '\n' + bar + s[m.end():]
    else:
        # Some pages omit <body> and let the browser infer it; put the bar after the head.
        j = s.index('</style>') + len('</style>')
        s = s[:j] + '\n\n' + bar + s[j:]

    path.write_text(s, encoding='utf-8')
    return 'updated'


def main() -> None:
    tracked = subprocess.run(['git', 'ls-files', '*.html'],
                             capture_output=True, text=True, check=True).stdout.split()
    pages = [pathlib.Path(p) for p in tracked]
    if len(sys.argv) > 1:
        wanted = tuple(sys.argv[1:])
        pages = [p for p in pages if str(p).startswith(wanted)]
    # the collection home has its own bar back to pushtimarg.net
    pages = [p for p in pages if str(p) != 'index.html']

    counts = Counter(process(p) for p in pages)
    for k, v in sorted(counts.items()):
        print(f'  {k:24} {v}')


if __name__ == '__main__':
    main()
