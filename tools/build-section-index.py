#!/usr/bin/env python3
"""Rebuild a section's listing page as a searchable, grouped index.

    python3 tools/build-section-index.py shikshapatra
    python3 tools/build-section-index.py shikshapatra --preview   # write index.preview.html

Why
---
A section listed its recordings newest-first, as one flat run of cards. Nobody
looks for a granth by the day it happened to be recorded — they want
शिक्षापत्र २९, or स्कन्ध ३ अध्याय ३२. With 44 sessions that already meant
scrolling and reading dates, and the lists only grow.

So the date becomes metadata and the scripture reference becomes the index:

  * a filter box that narrows the list as you type
  * sessions grouped under their शिक्षापत्र / अध्याय, with sticky headings
  * jump chips to reach a group in one tap
  * a sort toggle, because people following the daily सत्र do want date order
  * compact two-column rows: reference left, date right in tabular figures

Everything runs client-side; the site stays a set of static files.

The script reads the cards already in the page, so it keeps whatever the existing
generator produced, and rewrites only the region between the section bar and the
end of the list.
"""
from __future__ import annotations

import html
import json
import pathlib
import re
import sys

def dev_to_int(s: str) -> int | None:
    t = ''.join(str(DEV.index(c)) if c in DEV else c for c in s)
    return int(t) if t.isdigit() else None


def parse_cards(body: str) -> list[dict]:
    """Pull href, date and title out of the existing session cards."""
    out = []
    for m in re.finditer(
        r'<a class="session-card" href="([^"]+)">.*?'
        r'class="card-date">(.*?)</div>.*?'
        r'class="card-title">(.*?)</div>', body, re.S):
        href, date, title = m.groups()
        clean = lambda x: re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', x))).strip()
        out.append({'href': href,
                    'date': clean(date).replace('\U0001F4C5', '').strip(),
                    'title': clean(title)})
    return out


def parse_generated(s: str) -> list[dict]:
    """Read the session list back out of a page this script generated.

    A generated page carries its sessions as a JSON block rather than as card
    markup, so without this a second run found no cards and refused to rebuild —
    meaning the grouping could never be changed again once applied.
    """
    m = re.search(r'var DATA = (\[.*?\]);', s, re.S)
    if not m:
        return []
    return [{'href': x['h'], 'date': x['d'], 'title': x['t']} for x in json.loads(m.group(1))]


def read_sessions(s: str, body: str) -> list[dict]:
    """Every session on the page, whichever form it is stored in.

    Both forms are read and merged on href, so a newly added session card can be
    pasted into an already-generated page and picked up by the next rebuild.
    """
    seen, out = set(), []
    for c in parse_generated(s) + parse_cards(body):
        if c['href'] in seen:
            continue
        seen.add(c['href'])
        out.append(c)
    return out


DEV = '०१२३४५६७८९'
GUJ = '૦૧૨૩૪૫૬૭૮૯'


def num(s: str) -> int | None:
    """Read a number written in Devanagari, Gujarati or Latin digits.

    The Subodhini sessions mix scripts freely — ३/३२/१६-२२ and ૩/૩૨/૧૬-૨૨ are the same
    reference — so the digits have to be normalised before anything can be grouped.
    """
    out = ''
    for c in s:
        if c in DEV: out += str(DEV.index(c))
        elif c in GUJ: out += str(GUJ.index(c))
        elif c.isdigit(): out += c
        else: return None
    return int(out) if out else None


def _digits(s: str) -> str:
    return ''.join(str(DEV.index(c)) if c in DEV else str(GUJ.index(c)) if c in GUJ else c for c in s)


def dv(n) -> str:
    """Write a number in Devanagari digits, since the headings are read in Hindi."""
    return ''.join(DEV[int(c)] if c.isdigit() else c for c in str(n))


MONTHS = ['जनवरी','फ़रवरी','मार्च','अप्रैल','मई','जून','जुलाई','अगस्त',
          'सितम्बर','अक्टूबर','नवम्बर','दिसम्बर']


def group_of(title: str, folder: str, date: str = '') -> tuple:
    """Return (sort key, group heading, the part of the title that varies).

    Each section numbers its sessions its own way, so each gets its own reading.
    """
    t = _digits(title)

    # शिक्षापत्र २९_श्लोक ३-६   ->  grouped by patra
    m = re.search(r'शिक्षापत्र\s*(\d+)', t)
    if m:
        rest = title.split('_', 1)[1].strip() if '_' in title else 'सम्पूर्ण'
        return int(m.group(1)), f'शिक्षापत्र {dv(m.group(1))}', rest

    # सुबोधिनी_हिंदी_३/३२/१६-२२   ->  स्कन्ध ३ · अध्याय ३२
    if folder.startswith('subodhini'):
        m = re.search(r'(\d+)\s*/\s*(\d+)(?:\s*/\s*([\d\-–]+))?', t)
        if m:
            sk, ad, sl = int(m.group(1)), int(m.group(2)), m.group(3)
            return (sk * 1000 + ad, f'स्कन्ध {dv(sk)} · अध्याय {dv(ad)}',
                    f'श्लोक {dv(sl)}' if sl else 'सम्पूर्ण अध्याय')
        tail = title.split('_')[-1].strip()
        return None, 'अन्य सत्र', tail if tail and not tail.startswith('सुबोधिनी') else 'सम्पूर्ण'

    # ब्रह्मसूत्राणुभाष्य-३/२/१०-१५  ->  अध्याय ३, with पाद/अधिकरण and सूत्र alongside.
    # A handful of titles spell the reference out in words instead
    # ("द्वितीय अध्याय, प्रथम पाद — सूत्र १३ से १५ तक"), so those are read separately —
    # a bare \d+ search picked up the सूत्र number and invented an अध्याय १३.
    if folder == 'brahmasutra':
        m = re.search(r'भाष्य\s*[-–—]\s*(\d+)(?:\s*/\s*([^/]+?))?(?:\s*/\s*([\d\-–/]+))?(\s+.*)?$', t.strip())
        if m:
            ad, mid, su = int(m.group(1)), (m.group(2) or '').strip(), (m.group(3) or '').strip()
            bits = []
            if mid: bits.append(f'अधिकरण {dv(mid)}' if mid.isdigit() else dv(mid))
            if su: bits.append(f'सूत्र {dv(su)}')
            if (m.group(4) or '').strip(): bits.append(m.group(4).strip())
            return ad, f'अध्याय {dv(ad)}', ' · '.join(bits) or 'सम्पूर्ण'
        ORD = {'प्रथम': 1, 'द्वितीय': 2, 'तृतीय': 3, 'चतुर्थ': 4}
        m = re.search(r'(' + '|'.join(ORD) + r')\s*अध्याय', title)
        if m:
            ad = ORD[m.group(1)]
            rest = re.split(r'अध्याय\s*,?\s*', title, maxsplit=1)[-1].strip()
            return ad, f'अध्याय {dv(ad)}', rest or 'सम्पूर्ण'
        return None, 'अध्याय क्रम रहित', re.split(r'\s*:\s*', title, maxsplit=1)[-1].strip() or title

    # षोडशग्रन्थ_बालबोध_श्लोक_८-११   ->  grouped by granth
    if folder == 'shodash-granth':
        parts = title.split('_')
        if len(parts) >= 2 and parts[1].strip():
            name = parts[1].strip()
            # One tab per granth: the same name arrives spelled several ways
            # (सिद्धांत मुक्तावली / सिद्धांतमुक्तावली / सिद्धान्तमुक्तावली), so drop
            # spaces and write a nasal before त/थ/द/ध/न as न् before grouping.
            name = re.sub(r'\s+', '', name)
            name = re.sub(r'ं(?=[तथदधन])', 'न्', name)
            rest = dv(_digits(' '.join(parts[2:]))).replace('श्लोक', 'श्लोक ').strip()
            rest = re.sub(r'\s+', ' ', rest) or 'सम्पूर्ण'
            return None, name, rest
        return None, 'अन्य सत्र', title

    # Sections whose every session carries the same title (प्रमेयरत्नसंग्रह, भगवद् वार्ता)
    # have no internal reference to group by, so the month is the only real axis.
    if folder in ('prameya-ratna', 'bhagavad-varta'):
        m = re.match(r'(\d{4})-(\d{2})', date or '')
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            return y * 100 + mo, f'{MONTHS[mo-1]} {dv(y)}', title
        return None, 'दिनांक रहित', title

    # Descriptive titles: the work named before the dash is the group
    head = re.split(r'\s*[—–-]\s*', title)[0].strip()
    return None, head[:34] if head else 'अन्य सत्र', title

CSS = """
/* section-index:css:start */
.slx{max-width:860px;margin:0 auto;padding:0 14px 40px}
.slx-tools{position:sticky;top:56px;z-index:40;background:var(--cream,#FFF8E7);
  padding:12px 0 10px;border-bottom:1px solid rgba(139,0,0,.15)}
.slx-search{display:flex;align-items:center;gap:9px;background:#fff;
  border:2px solid var(--dark-red,#8B0000);border-radius:999px;padding:7px 16px}
.slx-search input{flex:1;min-width:0;border:0;outline:0;background:transparent;
  font-family:inherit;font-size:1rem;color:#2C1A00;padding:5px 0}
.slx-search input::placeholder{color:#a08a6a}
.slx-clear{border:0;background:none;cursor:pointer;font-size:1.1rem;color:#8B0000;
  padding:0 4px;visibility:hidden}
.slx-clear.on{visibility:visible}
.slx-row2{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:10px}
.slx-chip{border:1.5px solid rgba(139,0,0,.35);background:#fff;color:#8B0000;
  border-radius:999px;padding:4px 12px;font:600 .85rem/1.3 inherit;cursor:pointer;
  font-variant-numeric:tabular-nums}
.slx-chip:hover{background:#FFF0D0}
.slx-sort{margin-left:auto;display:flex;gap:0;border:1.5px solid rgba(139,0,0,.35);
  border-radius:999px;overflow:hidden}
.slx-sort button{border:0;background:#fff;color:#8B0000;cursor:pointer;
  font:600 .85rem/1 inherit;padding:7px 14px}
.slx-sort button[aria-pressed="true"]{background:var(--dark-red,#8B0000);color:#FFD700}
.slx-count{font-size:.85rem;color:#7a5c38;margin:12px 2px 6px}
.slx-group{margin-top:18px}
.slx-ghead{position:sticky;top:var(--slx-ghead-top,116px);z-index:30;
  background:linear-gradient(180deg,#FFD75E,#F0C832);
  border:1.5px solid rgba(139,0,0,.3);border-radius:8px;
  padding:8px 14px;font:700 1.02rem/1.3 inherit;color:#3D0D00;
  display:flex;align-items:center;gap:10px}
.slx-ghead .n{margin-left:auto;font-size:.78rem;font-weight:600;color:#7a2a12;
  background:rgba(255,255,255,.6);border-radius:999px;padding:2px 10px}
.slx-item{display:flex;align-items:center;gap:12px;background:#fff;
  border:1px solid rgba(139,0,0,.16);border-left:4px solid var(--orange,#FF6600);
  border-radius:7px;padding:10px 14px;margin-top:7px;text-decoration:none;
  color:#2C1A00;transition:transform .12s,box-shadow .12s}
.slx-item:hover{transform:translateX(3px);box-shadow:0 3px 10px rgba(139,0,0,.16)}
.slx-ref{flex:1;min-width:0;font-weight:600;font-size:.98rem}
.slx-date{flex:0 0 auto;font-size:.82rem;color:#7a5c38;font-variant-numeric:tabular-nums;
  white-space:nowrap}
.slx-empty{text-align:center;color:#8B0000;padding:34px 10px;font-size:1rem}
@media(max-width:560px){
  .slx-tools{top:52px}.slx-ghead{font-size:.96rem}
  .slx-item{padding:9px 11px;gap:8px}.slx-ref{font-size:.92rem}
  .slx-date{font-size:.76rem}.slx-sort{margin-left:0;width:100%}
  .slx-sort button{flex:1}
}
@media(prefers-reduced-motion:reduce){.slx-item{transition:none}}
/* section-index:css:end */
"""

JS = """
<script>
(function(){
  var DATA = __DATA__;
  var list = document.getElementById('slx-list');
  var countEl = document.getElementById('slx-count');
  var chipWrap = document.getElementById('slx-chips');
  var input = document.getElementById('slx-q');
  var clear = document.getElementById('slx-clear');
  var order = 'granth';

  function groups(items){
    var by = {}, seq = [];
    items.forEach(function(it){
      if(!by[it.g]){ by[it.g] = {name: it.g, key: it.k, rows: []}; seq.push(by[it.g]); }
      by[it.g].rows.push(it);
    });
    return seq;
  }

  function render(){
    var q = input.value.trim().toLowerCase();
    var items = DATA.filter(function(it){
      return !q || (it.t + ' ' + it.d + ' ' + it.g).toLowerCase().indexOf(q) !== -1;
    });
    countEl.textContent = items.length + ' / ' + DATA.length + ' सत्र';
    clear.className = 'slx-clear' + (q ? ' on' : '');
    list.innerHTML = '';

    if(!items.length){
      list.innerHTML = '<div class="slx-empty">कोई सत्र नहीं मिला</div>';
      return;
    }

    if(order === 'date'){
      items = items.slice().sort(function(a,b){ return a.d < b.d ? 1 : a.d > b.d ? -1 : 0; });
      items.forEach(function(it){ list.appendChild(row(it, true)); });
      return;
    }

    var seq = groups(items.slice().sort(function(a,b){
      if(a.k !== b.k) return (a.k === null) - (b.k === null) || a.k - b.k;
      return a.d < b.d ? -1 : 1;
    }));
    seq.forEach(function(g){
      var box = document.createElement('div');
      box.className = 'slx-group';
      var h = document.createElement('div');
      h.className = 'slx-ghead';
      h.id = 'g' + (g.key === null ? 'x' : g.key);
      h.innerHTML = '<span>' + g.name + '</span><span class="n">' + g.rows.length + ' सत्र</span>';
      box.appendChild(h);
      g.rows.forEach(function(it){ box.appendChild(row(it, false)); });
      list.appendChild(box);
    });
  }

  function row(it, showGroup){
    var a = document.createElement('a');
    a.className = 'slx-item';
    a.href = it.h;
    a.innerHTML = '<span class="slx-ref">' + (showGroup ? it.g + ' · ' : '') + it.r +
                  '</span><span class="slx-date">' + it.d + '</span>';
    return a;
  }

  input.addEventListener('input', render);
  clear.addEventListener('click', function(){ input.value = ''; input.focus(); render(); });
  chipWrap.addEventListener('click', function(e){
    var b = e.target.closest('.slx-chip'); if(!b) return;
    if(order !== 'granth'){ order = 'granth'; syncSort(); render(); }
    var el = document.getElementById('g' + b.dataset.k);
    if(!el) return;
    // Not scrollIntoView: that puts the heading flush with the top of the window,
    // where the sticky search bar covers it.
    // The heading's own CSS 'top' is exactly where it comes to rest when stuck —
    // just below the toolbar — so landing it there needs no guessed padding.
    // A fixed guess was one group out on sections whose header is a different height.
    // stickyTop() is where this heading comes to rest, just under the toolbar,
    // so landing it there needs no guessed padding.
    var pad = stickyTop();
    // offsetTop, not getBoundingClientRect: the headings are sticky, so once one is
    // stuck its viewport rect reports the stuck position rather than where it lives.
    var y = 0, n = el;
    while(n){ y += n.offsetTop; n = n.offsetParent; }
    window.scrollTo(0, Math.max(0, y - pad));
  });
  // The toolbar wraps onto two rows of jump chips on a phone, so its height is not
  // something CSS can hard-code: measure it and let the group headings stick below it.
  // With a fixed value the headings parked behind the toolbar and every jump chip
  // appeared to land one group early.
  function stickyTop(){
    var tools = document.querySelector('.slx-tools');
    if(!tools) return 116;
    var own = parseFloat(getComputedStyle(tools).top);
    return (isFinite(own) ? own : 0) + tools.offsetHeight;
  }
  function syncStickyTop(){
    document.documentElement.style.setProperty('--slx-ghead-top', stickyTop() + 'px');
  }
  window.addEventListener('resize', syncStickyTop);

  function syncSort(){
    document.querySelectorAll('.slx-sort button').forEach(function(b){
      b.setAttribute('aria-pressed', String(b.dataset.o === order));
    });
    chipWrap.style.display = order === 'granth' ? '' : 'none';
  }
  document.querySelectorAll('.slx-sort button').forEach(function(b){
    b.addEventListener('click', function(){ order = b.dataset.o; syncSort(); render(); });
  });
  syncSort(); render(); syncStickyTop();
})();
</script>
"""


MARK_START = '<!-- section-index:start -->'
MARK_END = '<!-- section-index:end -->'


def build(folder: str, preview: bool = False) -> None:
    d = pathlib.Path(folder)
    page = d / 'index.html'
    s = page.read_text(encoding='utf-8')
    body = s[s.index('<body'):]
    cards = read_sessions(s, body)
    if not cards:
        print(f'  {folder}: no session cards found — left unchanged')
        return

    data, keys = [], {}
    for c in cards:
        k, gname, rest = group_of(c['title'], folder, c['date'])
        keys.setdefault(gname, k)
        data.append({'h': c['href'], 'd': c['date'], 't': c['title'],
                     'g': gname, 'k': k, 'r': rest or 'सम्पूर्ण'})

    chips = ''.join(
        f'<button class="slx-chip" data-k="{"x" if k is None else k}">{html.escape(n)}</button>'
        for n, k in sorted(keys.items(), key=lambda kv: (kv[1] is None, kv[1] or 0)))

    ui = f'''{MARK_START}<div class="slx">
  <div class="slx-tools">
    <div class="slx-search">
      <span aria-hidden="true">🔍</span>
      <input id="slx-q" type="search" placeholder="खोजें — प्रकरण, श्लोक अथवा दिनांक"
             aria-label="सत्र खोजें">
      <button id="slx-clear" class="slx-clear" type="button" aria-label="खोज हटाएँ">✕</button>
    </div>
    <div class="slx-row2">
      <div id="slx-chips">{chips}</div>
      <div class="slx-sort">
        <button data-o="granth" aria-pressed="true">ग्रन्थ-क्रम</button>
        <button data-o="date" aria-pressed="false">नवीनतम</button>
      </div>
    </div>
  </div>
  <div id="slx-count" class="slx-count"></div>
  <div id="slx-list"></div>
</div>
{MARK_END}
'''
    # On a page this script has already written, replace its own block; on an
    # untouched one, replace everything from the section bar to the end of the
    # old card list. Without the markers a second run had nothing it recognised
    # and stopped, so the grouping could not be revised after being applied.
    if MARK_START in s and MARK_END in s:
        start = s.index(MARK_START)
        end = s.index(MARK_END) + len(MARK_END)
    elif '<div class="slx">' in s:
        # An early generated page, written before the markers existed.
        m = re.search(r'<div class="slx">.*?<div id="slx-list"></div>\s*</div>\n?', s, re.S)
        start, end = m.start(), m.end()
    else:
        start = s.index('<div class="section-bar">')
        end = s.index('</div>', body.index('</a>', body.rindex('<a class="session-card"'))
                      + len(s) - len(body)) + len('</div>')
    s = s[:start] + ui + s[end:]

    # Swallow the blank lines around the old block as well. Leaving them behind added
    # one newline on every run, so a rebuild of an already-grouped page still produced a
    # one-line diff — which made the workflow commit on every upload instead of stopping
    # at "nothing to do".
    s = re.sub(r'\n*/\* section-index:css:start \*/.*?/\* section-index:css:end \*/\n*',
               '\n', s, flags=re.S)
    s = s[:s.index('</style>')] + CSS + s[s.index('</style>'):]
    s = re.sub(r'\n*<script>\n\(function\(\)\{\n  var DATA.*?</script>\n*', '\n', s, flags=re.S)
    s = s.replace('</body>', JS.replace('__DATA__', json.dumps(data, ensure_ascii=False)) + '\n</body>')

    # Each run strips a block and splices a new one, which otherwise leaves a few
    # blank lines behind that pile up with every rebuild.
    s = re.sub(r'\n{3,}', '\n\n', s)

    out = d / ('index.preview.html' if preview else 'index.html')
    out.write_text(s, encoding='utf-8')
    print(f'  {folder}: {len(data)} sessions in {len(keys)} groups -> {out}')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    build(args[0], preview='--preview' in sys.argv)
