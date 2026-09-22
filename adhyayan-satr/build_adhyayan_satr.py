#!/usr/bin/env python3
"""
build_adhyayan_satr.py — Adhyayan Satra HTML Generator
=======================================================
Usage:
    python3 build_adhyayan_satr.py <PLAYLIST_OR_VIDEO_URL> [options]

Examples:
    python3 build_adhyayan_satr.py "https://www.youtube.com/playlist?list=PLdT357W2xFj4" \
        --title "वेदान्तचिन्तामणि तृतीय एवं चतुर्थ प्रकरण" \
        --speaker "गोस्वामी श्रीशरदकुमारजी" \
        --granth "वेदान्तचिन्तामणि" \
        --session "भाद्रपद २०८३ · सितंबर २०२६"

    # Single video:
    python3 build_adhyayan_satr.py "https://www.youtube.com/watch?v=exdiVaCoAZg" ...

Options:
    --title      ग्रन्थ + प्रकरण का पूरा नाम  (required)
    --speaker    वक्ता का नाम (default: गोस्वामी श्रीशरदकumarजी)
    --granth     ग्रन्थ का नाम for banner box
    --session    सत्र की जानकारी for banner box (e.g. "भाद्रपद २०८३ · ३ दिन")
    --out        Output HTML filename (default: auto-generated from title)
    --chunk      Chunk size in minutes (default: 15)
    --captions   Path to folder with pre-downloaded .vtt files (skips yt-dlp)
    --api        API to use: anthropic | gemini | none (default: auto-detect)

Requirements:
    pip install anthropic requests
    brew install yt-dlp  (or pip install yt-dlp)
"""

import argparse, json, os, re, sys, time
from pathlib import Path
from datetime import datetime

# ─── CONFIG ─────────────────────────────────────────────────────────────────

INSTITUTION = "श्रीवल्लभाचार्य विद्यापीठ"
ADDRESS     = "२६, श्रीवल्लभाचार्य नगर, रेखड़ हॉस्पिटल के पीछे, हालोल, ३८९ ३४०, जिला पंचमहाल, गुजरात"
WEBSITE     = "www.vallabhacharyavidhyapeeth.org"
REPO_DIR    = Path(__file__).parent

# ─── DEVANAGARI HELPERS ─────────────────────────────────────────────────────

def to_deva(n):
    d = "०१२३४५६७८९"
    return "".join(d[int(c)] for c in str(n))

def sec_to_ts(s):
    h, r = divmod(int(s), 3600)
    m, sec = divmod(r, 60)
    if h:
        return f"{to_deva(h)}:{to_deva(m):0>2}:{to_deva(sec):0>2}"
    return f"{to_deva(m):0>2}:{to_deva(sec):0>2}"

# ─── VTT PARSING ─────────────────────────────────────────────────────────────

def parse_vtt(path):
    """Parse YouTube auto-caption VTT. Returns list of (start_sec, text)."""
    txt = Path(path).read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n{2,}", txt.strip())
    segs, prev = [], None
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        ts = next((l for l in lines if "-->" in l), None)
        if not ts:
            continue
        start_str = ts.split("-->")[0].strip().split()[0]
        parts = start_str.replace(",", ".").split(":")
        try:
            if len(parts) == 3:
                sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            else:
                sec = int(parts[0]) * 60 + float(parts[1])
        except:
            continue
        texts = [re.sub(r"<[^>]+>", "", l).strip()
                 for l in lines if "-->" not in l and not l.isdigit()
                 and not l.upper().startswith("WEBVTT")]
        texts = [t for t in texts if t]
        if texts:
            last = texts[-1]
            if last != prev:
                segs.append((sec, last))
                prev = last
    return segs

def chunk_segments(segs, chunk_sec=900):
    """Group segments into chunks of chunk_sec seconds."""
    if not segs:
        return []
    chunks, start, buf = [], segs[0][0], []
    for sec, txt in segs:
        if sec - start >= chunk_sec and buf:
            chunks.append((start, " ".join(buf)))
            start, buf = sec, [txt]
        else:
            buf.append(txt)
    if buf:
        chunks.append((start, " ".join(buf)))
    return chunks

# ─── YT-DLP DOWNLOAD ─────────────────────────────────────────────────────────

def download_vtt(url, out_dir):
    """Download Hindi VTT captions for all videos in a playlist or single video."""
    import subprocess
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)
    cmd = [
        "yt-dlp",
        "--write-auto-sub", "--sub-lang", "hi",
        "--skip-download", "--sub-format", "vtt",
        "--output", str(out_dir / "%(playlist_index)02d-%(title)s [%(id)s].%(ext)s"),
        "--no-playlist" if "watch?v=" in url and "list=" not in url else "--yes-playlist",
        url
    ]
    print(f"Downloading captions from: {url}")
    subprocess.run(cmd, check=True)
    return sorted(out_dir.glob("*.hi.vtt"))

def get_playlist_info(url):
    """Get video metadata from playlist via yt-dlp."""
    import subprocess, json
    cmd = ["yt-dlp", "--flat-playlist", "--dump-json", url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    videos = []
    for line in result.stdout.splitlines():
        try:
            info = json.loads(line)
            videos.append({
                "id": info.get("id", ""),
                "title": info.get("title", ""),
                "duration": info.get("duration", 0),
            })
        except:
            pass
    return videos

# ─── SUMMARY GENERATION ──────────────────────────────────────────────────────

def _detect_api():
    """Auto-detect which API is available."""
    # Try Anthropic
    key = os.environ.get("ANTHROPIC_API_KEY") or _read_env_file("ANTHROPIC_API_KEY")
    if key:
        try:
            import anthropic
            c = anthropic.Anthropic(api_key=key)
            c.messages.create(model="claude-haiku-4-5-20251001", max_tokens=5,
                              messages=[{"role":"user","content":"hi"}])
            return "anthropic", key
        except Exception as e:
            if "credit" in str(e).lower() or "balance" in str(e).lower():
                print("⚠  Anthropic API: no credits")
            pass
    # Try Gemini
    key = os.environ.get("GEMINI_API_KEY") or _read_env_file("GEMINI_API_KEY")
    if key:
        try:
            import requests
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={key}",
                json={"contents":[{"parts":[{"text":"hi"}]}]}, timeout=15)
            if r.status_code == 200:
                return "gemini", key
        except:
            pass
    return "none", None

def _read_env_file(key):
    env_path = REPO_DIR.parent / "web" / ".env.local"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"')
    return None

PROMPT_RULES = """
नियम (अनिवार्य):
1. पहला sub-heading: transcript में जो श्लोक/करिका/सूत्र संख्या मिले वह लिखो, साथ में उस श्लोक का संक्षिप्त भाव (1-2 वाक्य)।
   यदि कोई संख्या नहीं मिली तो केवल विषय-शीर्षक लिखो (जैसे "उपक्रम:", "प्रश्नोत्तरी:", "समापन:" आदि)।
2. मुख्य विषय: वक्ता ने जो व्याख्या दी है उसी से — अपनी ओर से कुछ न जोड़ो।
3. विस्तृत विवेचन: transcript के आधार पर topic और sub-topic वार विस्तृत सारांश — न्यूनतम १० पंक्तियाँ।
   उप-विषय अलग-अलग sentence से शुरू करो ताकि पढ़ने में सुलभ हो।
4. सिद्धान्त-सार: केवल तब लिखो जब transcript में स्पष्ट निष्कर्ष या key takeaway हो।
   यदि transcript में नहीं है तो यह paragraph पूरी तरह छोड़ दो — कुछ भी मत बनाओ।
"""

def _make_prompt(vid_title, ts, transcript, is_qa):
    head = f"वीडियो: {vid_title} | समय: {ts}\n---\n{transcript[:4000]}\n---\n{PROMPT_RULES}"
    if is_qa:
        return head + """
HTML format में paragraph लिखो (केवल <p> tags):

<p><span class="sub-heading">प्रश्नोत्तरी:</span>कौन-सा प्रश्न, क्या पृष्ठभूमि — transcript से 2-3 वाक्य</p>
<p><span class="sub-heading">मुख्य प्रश्न एवं उत्तर:</span>वक्ता का उत्तर जैसा transcript में है — 4-5 वाक्य</p>
<p><span class="sub-heading">विस्तृत विवेचन:</span>topic/sub-topic वार विस्तृत — न्यूनतम १० पंक्तियाँ</p>
[यदि transcript में निष्कर्ष हो तभी:]
<p><span class="sub-heading">सिद्धान्त-सार:</span>transcript का वास्तविक key takeaway — 2 वाक्य</p>"""
    else:
        return head + """
HTML format में paragraph लिखो (केवल <p> tags):

<p><span class="sub-heading">[श्लोक/करिका X–Y या विषय-शीर्षक]:</span>उस श्लोक/करिका का संक्षिप्त भाव transcript से — 2-3 वाक्य</p>
<p><span class="sub-heading">मुख्य विषय:</span>वक्ता की व्याख्या से केन्द्रीय सिद्धान्त — 3-4 वाक्य</p>
<p><span class="sub-heading">विस्तृत विवेचन:</span>topic/sub-topic वार विस्तृत विवेचन transcript से — न्यूनतम १० पंक्तियाँ</p>
[यदि transcript में स्पष्ट निष्कर्ष हो तभी:]
<p><span class="sub-heading">सिद्धान्त-सार:</span>transcript का वास्तविक key takeaway — 2 वाक्य</p>"""

def summarize_with_anthropic(key, vid_title, start_sec, transcript, is_qa):
    import anthropic
    ts = sec_to_ts(start_sec)
    prompt = _make_prompt(vid_title, ts, transcript, is_qa)
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=1200,
        messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text.strip()

def summarize_with_gemini(key, vid_title, start_sec, transcript, is_qa):
    import requests
    ts = sec_to_ts(start_sec)
    prompt = _make_prompt(vid_title, ts, transcript, is_qa)
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={key}",
        json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

def summarize_no_api(vid_title, start_sec, transcript, is_qa, chunk_idx):
    """Fallback: structure raw transcript into the sub-heading format."""
    words = transcript.split()
    # First heading: detect shlok/karika number
    shlok_m = re.search(r'(श्लोक|करिका|सूत्र)\s*[\d०-९]+(?:\s*[–\-]\s*[\d०-९]+)?', transcript[:600])
    if shlok_m:
        label1 = shlok_m.group(0)
        # Brief shlok summary = next 30 words after match
        pos = transcript.find(shlok_m.group(0))
        shlok_ctx = " ".join(transcript[pos:pos+300].split()[:30])
    elif is_qa:
        label1 = "प्रश्नोत्तरी"
        shlok_ctx = " ".join(words[:30])
    else:
        label1 = "उपक्रम" if chunk_idx == 0 else "विवेचन"
        shlok_ctx = " ".join(words[:30])

    label2 = "मुख्य प्रश्न एवं उत्तर" if is_qa else "मुख्य विषय"
    # Distribute: ~10% heading ctx, ~20% main, rest for विस्तृत, last 15% for सार
    n = len(words)
    main_txt  = " ".join(words[max(0,n//10) : n//4])
    vistar_txt = " ".join(words[n//4 : int(n*0.85)])
    saar_txt   = " ".join(words[int(n*0.85):])

    saar_para = ""
    if saar_txt.strip():
        saar_para = f'\n<p><span class="sub-heading">सिद्धान्त-सार:</span>{saar_txt[:400]}</p>'

    return (f'<p><span class="sub-heading">{label1}:</span>{shlok_ctx}</p>\n'
            f'<p><span class="sub-heading">{label2}:</span>{main_txt[:500]}</p>\n'
            f'<p><span class="sub-heading">विस्तृत विवेचन:</span>{vistar_txt[:1200]}</p>'
            + saar_para)

def get_summary(api, api_key, cache, cache_file, vid_id, chunk_idx,
                vid_title, start_sec, transcript, is_qa, speaker):
    key = f"{vid_id}_{chunk_idx}"
    if key in cache:
        print(f"  [cache] chunk {chunk_idx}")
        return cache[key]

    print(f"  [API:{api}] chunk {chunk_idx} ({len(transcript)} chars)...")
    try:
        if api == "anthropic":
            result = summarize_with_anthropic(api_key, vid_title, start_sec, transcript, is_qa)
        elif api == "gemini":
            result = summarize_with_gemini(api_key, vid_title, start_sec, transcript, is_qa)
        else:
            result = summarize_no_api(vid_title, start_sec, transcript, is_qa, chunk_idx)
        # Replace generic आचार्यजी with speaker name
        result = result.replace("आचार्यजी", speaker)
    except Exception as e:
        print(f"  [ERROR] {e} — using transcript fallback")
        result = summarize_no_api(vid_title, start_sec, transcript, is_qa, chunk_idx)

    cache[key] = result
    Path(cache_file).write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    time.sleep(0.3)
    return result

# ─── CHUNK TITLE ─────────────────────────────────────────────────────────────

def chunk_title(transcript, chunk_idx):
    shlok = re.search(r'(श्लोक|करिका|सूत्र)\s*[\d०-९]+(?:\s*[–-]\s*[\d०-९]+)?', transcript[:600])
    if shlok:
        return shlok.group(0) + " — विवेचन"
    if chunk_idx == 0:
        return "मंगलाचरण एवं उपक्रम"
    fallback = ["विषय-प्रवेश","श्लोक-विवेचन","तत्त्व-निरूपण","उदाहरण एवं प्रमाण",
                "गहन व्याख्या","प्रश्नोत्तरी","विस्तृत विवेचन","सारांश","उपसंहार"]
    return fallback[chunk_idx % len(fallback)]

# ─── CSS ─────────────────────────────────────────────────────────────────────

CSS = """
  @import url('https://fonts.googleapis.com/css2?family=Tiro+Devanagari+Hindi:ital@0;1&family=Noto+Serif+Devanagari:wght@400;600;700&family=Noto+Sans+Devanagari:wght@400;500;700&display=swap');
  :root{--red:#c0141a;--dark-red:#8b0000;--orange:#e06010;--gold:#d4a017;--yellow:#f5c518;
        --cream:#fff9f0;--white:#ffffff;--light-bg:#fff3e0;--section-bg:#fff8f0;
        --border:#e06010;--text:#2a0a00;--muted:#7a4000;}
  *{margin:0;padding:0;box-sizing:border-box;}
  body{font-family:'Tiro Devanagari Hindi','Noto Serif Devanagari',serif;background:var(--cream);color:var(--text);line-height:1.9;}
  .banner-wrapper{background:linear-gradient(180deg,var(--dark-red),var(--red) 55%,var(--orange));border-bottom:6px solid var(--gold);}
  .banner-inner{max-width:960px;margin:0 auto;padding:22px 28px;text-align:center;color:var(--yellow);}
  .banner-institution{font-size:1.9em;font-weight:700;letter-spacing:.04em;text-shadow:2px 2px 5px rgba(0,0,0,.5);margin-bottom:6px;}
  .banner-address{font-size:.82em;color:#ffe8b0;margin-bottom:4px;}
  .banner-website{font-size:.8em;color:#ffd780;margin-bottom:14px;font-style:italic;}
  .banner-subtitle-row{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;}
  .banner-box{background:rgba(255,255,255,.13);border:1px solid rgba(255,220,80,.45);border-radius:8px;padding:8px 18px;font-size:.82em;color:#fff8e0;max-width:340px;line-height:1.55;}
  .banner-box strong{display:block;color:var(--yellow);font-size:.95em;margin-bottom:3px;}
  .title-block{max-width:900px;margin:28px auto 0;padding:22px 28px;text-align:center;}
  .main-title{font-size:1.85em;font-weight:700;color:var(--dark-red);margin-bottom:8px;line-height:1.35;}
  .subtitle-line{font-size:.98em;color:var(--muted);margin-bottom:14px;}
  .doc-desc{font-size:.9em;color:#4a2000;line-height:1.85;margin-bottom:10px;text-align:left;}
  .notice{font-size:.82em;background:#fff3cd;border-left:4px solid var(--gold);padding:8px 14px;border-radius:0 6px 6px 0;color:#6a4000;margin-top:8px;text-align:left;}
  .usage-box{max-width:900px;margin:16px auto;padding:18px 24px;background:var(--section-bg);border:1.5px solid var(--border);border-radius:10px;}
  .usage-box h3{font-size:1em;color:var(--dark-red);margin-bottom:10px;}
  .usage-box ul{padding-left:22px;}
  .usage-box li{font-size:.86em;color:var(--text);margin-bottom:5px;line-height:1.6;}
  .toc-section{max-width:900px;margin:24px auto;background:var(--white);border:2px solid var(--border);border-radius:12px;overflow:hidden;}
  .toc-section h2{background:linear-gradient(90deg,var(--dark-red),var(--red));color:var(--yellow);padding:13px 22px;font-size:1.05em;}
  .toc-list{list-style:none;padding:0;margin:0;}
  .toc-list li{border-bottom:1px solid #ffe4b0;}
  .toc-list li:last-child{border-bottom:none;}
  .toc-list a{display:flex;align-items:center;gap:10px;padding:10px 18px;text-decoration:none;color:var(--text);font-size:.88em;transition:background .15s;}
  .toc-list a:hover{background:var(--light-bg);}
  .toc-num{background:var(--red);color:var(--yellow);font-size:.72em;font-weight:700;padding:2px 8px;border-radius:12px;white-space:nowrap;flex-shrink:0;}
  .part-section{max-width:900px;margin:28px auto;background:var(--white);border:2px solid var(--border);border-radius:12px;overflow:hidden;}
  .part-header{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:14px 20px;background:linear-gradient(90deg,var(--dark-red),var(--red) 70%,var(--orange));flex-wrap:wrap;}
  .part-header h2{font-size:1.02em;color:var(--yellow);font-weight:700;line-height:1.4;}
  .full-video-btn{background:var(--yellow);color:var(--dark-red);text-decoration:none;font-size:.78em;font-weight:700;padding:5px 13px;border-radius:16px;white-space:nowrap;flex-shrink:0;transition:background .2s;}
  .full-video-btn:hover{background:#fff;}
  .part-body{padding:18px 22px;}
  .part-intro-text{font-size:.9em;color:var(--muted);margin-bottom:16px;font-style:italic;border-left:3px solid var(--gold);padding-left:12px;}
  .topic{margin-bottom:22px;border:1px solid #ffe0b0;border-radius:8px;overflow:hidden;}
  .topic-header{display:flex;align-items:center;gap:10px;padding:10px 14px;background:linear-gradient(90deg,var(--light-bg),#fff8f5);border-bottom:1px solid #ffe0b0;}
  .topic-marker{color:var(--orange);font-size:1.1em;flex-shrink:0;}
  .topic-header h3{flex:1;font-size:.95em;color:var(--dark-red);font-weight:700;}
  .topic-ts{background:var(--orange);color:#fff;font-size:.72em;font-weight:700;padding:2px 9px;border-radius:10px;flex-shrink:0;}
  .topic p{padding:8px 14px 2px;font-size:.88em;line-height:1.85;color:var(--text);}
  .topic p:last-of-type{padding-bottom:8px;}
  .sub-heading{font-weight:700;color:var(--orange);margin-right:4px;}
  .jump-link{display:inline-block;margin:6px 14px 12px;background:var(--red);color:#fff;text-decoration:none;font-size:.8em;padding:4px 14px;border-radius:14px;border:1.5px solid var(--gold);transition:background .2s;}
  .jump-link:hover{background:var(--orange);}
  .part-summary-box{background:linear-gradient(135deg,#fff8e7,#fff3d0);border:2px solid var(--gold);border-radius:8px;padding:14px 18px;margin-top:20px;font-size:.9em;color:var(--text);line-height:1.85;}
  .back-top{display:inline-block;margin:12px 0 4px;font-size:.82em;color:var(--muted);text-decoration:none;border-bottom:1px dotted var(--muted);}
  .back-top:hover{color:var(--red);}
  footer{background:var(--dark-red);color:var(--white);text-align:center;padding:22px;border-top:6px solid var(--gold);margin-top:20px;}
  footer p{color:var(--yellow);font-size:.9em;margin:4px 0;}
  footer .small{font-size:.76em;color:#FFAA00;}
  @media(max-width:600px){.banner-institution{font-size:1.3em;}.main-title{font-size:1.3em;}.banner-subtitle-row{flex-direction:column;}.part-header{flex-direction:column;align-items:flex-start;}}
"""

# ─── HTML BUILDER ─────────────────────────────────────────────────────────────

def build_html(args, videos_data):
    """Build complete HTML from video data list."""
    today = datetime.now().strftime("%B %Y")
    title = args.title
    speaker = args.speaker
    granth = args.granth or title
    session_info = args.session or today

    # TOC
    toc_rows = []
    for i, v in enumerate(videos_data, 1):
        toc_rows.append(
            f'<li><a href="#part{i}"><span class="toc-num">भाग {to_deva(i)}</span>'
            f'{v["title"]} ({v["dur"]})</a></li>'
        )

    # Parts
    parts_html = []
    for i, v in enumerate(videos_data, 1):
        topics_html = []
        for idx, (start_sec, t, summary) in enumerate(v["chunks"]):
            ts = sec_to_ts(start_sec)
            topics_html.append(f"""
  <div class="topic">
    <div class="topic-header">
      <span class="topic-marker">■</span>
      <h3>{t}</h3>
      <span class="topic-ts">{ts}</span>
    </div>
    {summary}
    <a href="https://youtu.be/{v['id']}?t={int(start_sec)}" target="_blank" class="jump-link">▶ सीधे इस समय पर जाएँ</a>
  </div>""")

        n = to_deva(len(v["chunks"]))
        parts_html.append(f"""
<div class="part-section" id="part{i}">
  <div class="part-header">
    <h2>भाग {to_deva(i)} : {v['title']}</h2>
    <a href="https://www.youtube.com/watch?v={v['id']}" target="_blank" class="full-video-btn">📹 पूरा वीडियो</a>
  </div>
  <div class="part-body">
    <p class="part-intro-text">अवधि: {v['dur']} · {n} खण्ड (प्रत्येक ~{args.chunk} मिनट)</p>
    {"".join(topics_html)}
    <div class="part-summary-box"><strong>📝 भाग-सार:</strong> इस भाग में {v['title']} पर {n} खण्डों में विस्तृत विवेचन हुआ।</div>
    <a href="#toc" class="back-top">↑ अनुक्रमणिका पर जाएँ</a>
  </div>
</div>""")

    return f"""<!DOCTYPE html>
<html lang="hi" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>॥ श्रीकृष्णाय नमः ॥ — {title}</title>
<style>{CSS}</style>
</head>
<body>

<div class="banner-wrapper">
  <div class="banner-inner">
    <div class="banner-institution">{INSTITUTION}</div>
    <div class="banner-address">{ADDRESS}</div>
    <div class="banner-website">{WEBSITE}</div>
    <div class="banner-subtitle-row">
      <div class="banner-box"><strong>ग्रंथ</strong>{granth}</div>
      <div class="banner-box"><strong>सत्र</strong>{session_info}</div>
    </div>
  </div>
</div>

<div class="title-block">
  <div class="main-title">{title}</div>
  <div class="subtitle-line">{speaker} · {INSTITUTION}, हालोल · {session_info}</div>
  <p class="doc-desc">यह दस्तावेज़ {granth} पर हुए अध्ययन सत्र का विस्तृत सारांश प्रस्तुत करता है।
प्रत्येक वीडियो को लगभग {args.chunk}-मिनट के खण्डों में विभाजित किया गया है।</p>
  <p class="notice">सूचना: यह सारांश AI-सहायता से वीडियो के स्वतः-उत्पन्न ट्रांसक्रिप्ट के आधार पर तैयार किया गया है।
किसी भी त्रुटि के लिए मूल वीडियो देखें।</p>
</div>

<div class="usage-box">
  <h3>📍 दस्तावेज़ का उपयोग:</h3>
  <ul>
    <li><strong>▶ सीधे इस समय पर जाएँ</strong> — YouTube वीडियो उस स्थान से चालू होगा।</li>
    <li><strong>↑ अनुक्रमणिका पर जाएँ</strong> — प्रत्येक भाग के अन्त में वापस जाएँ।</li>
  </ul>
</div>

<div class="toc-section" id="toc">
  <h2>📋 अनुक्रमणिका</h2>
  <ul class="toc-list">
    {"".join(toc_rows)}
  </ul>
</div>

{"".join(parts_html)}

<footer>
  <p>॥ श्रीकृष्णाय नमः ॥</p>
  <p>{granth} · {INSTITUTION}, हालोल</p>
  <p class="small">यह संकलन स्वाध्याय हेतु निर्मित है। सर्वाधिकार सुरक्षित।</p>
</footer>
</body>
</html>"""

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build Adhyayan Satra HTML from playlist")
    parser.add_argument("url", help="YouTube playlist or video URL")
    parser.add_argument("--title",   required=True, help="Full title for the document")
    parser.add_argument("--speaker", default="गोस्वामी श्रीशरदकुमारजी")
    parser.add_argument("--granth",  default=None, help="Granth name for banner")
    parser.add_argument("--session", default=None, help="Session info for banner")
    parser.add_argument("--out",     default=None, help="Output HTML filename")
    parser.add_argument("--chunk",   type=int, default=15, help="Chunk size in minutes")
    parser.add_argument("--captions",default=None, help="Folder with pre-downloaded .vtt files")
    parser.add_argument("--api",     default="auto", choices=["auto","anthropic","gemini","none"])
    args = parser.parse_args()

    chunk_sec = args.chunk * 60

    # Determine output path
    if args.out:
        out_path = REPO_DIR / args.out
    else:
        slug = re.sub(r'[^\w\-]', '-', args.title.lower())[:60].strip('-')
        slug = re.sub(r'-+', '-', slug)
        out_path = REPO_DIR / f"{slug}.html"

    # Cache file
    cache_file = REPO_DIR / f"_adhyayan_cache_{out_path.stem}.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}

    # API detection
    if args.api == "auto":
        api, api_key = _detect_api()
    elif args.api == "none":
        api, api_key = "none", None
    else:
        api = args.api
        api_key = _read_env_file(
            "ANTHROPIC_API_KEY" if api == "anthropic" else "GEMINI_API_KEY")
    print(f"API: {api}")

    # Get VTT files
    if args.captions:
        vtt_dir = Path(args.captions)
        vtt_files = sorted(vtt_dir.glob("*.hi.vtt"))
    else:
        vtt_dir = Path(f"/tmp/adhyayan_captions_{out_path.stem}")
        download_vtt(args.url, vtt_dir)
        vtt_files = sorted(vtt_dir.glob("*.hi.vtt"))

    if not vtt_files:
        print("❌ No .hi.vtt files found. Check yt-dlp output or --captions path.")
        sys.exit(1)

    print(f"Found {len(vtt_files)} VTT files")

    # Process each video
    videos_data = []
    for vtt_path in vtt_files:
        # Extract video ID from filename
        m = re.search(r'\[([A-Za-z0-9_\-]{8,12})\]', vtt_path.name)
        if not m:
            print(f"  Skipping {vtt_path.name} — can't find video ID")
            continue
        vid_id = m.group(1)

        # Clean title from filename
        vid_title = re.sub(r'^\d+[-.]?\s*', '', vtt_path.stem)
        vid_title = re.sub(r'\s*\[[A-Za-z0-9_\-]+\].*$', '', vid_title).strip()

        print(f"\n=== {vid_title} [{vid_id}] ===")

        segs = parse_vtt(vtt_path)
        if not segs:
            print("  No segments found, skipping")
            continue

        chunks = chunk_segments(segs, chunk_sec)
        dur_sec = segs[-1][0] if segs else 0
        h, r = divmod(int(dur_sec), 3600)
        m2, s = divmod(r, 60)
        dur_str = f"{h}:{m2:02d}:{s:02d}" if h else f"{m2}:{s:02d}"

        is_qa = bool(re.search(r'प्रश्न|Q&A|प्रश्नोत्तर', vid_title))

        processed_chunks = []
        for idx, (start_sec, txt) in enumerate(chunks):
            title = chunk_title(txt, idx)
            summary = get_summary(
                api, api_key, cache, cache_file,
                vid_id, idx, vid_title, start_sec, txt, is_qa, args.speaker)
            processed_chunks.append((start_sec, title, summary))

        videos_data.append({
            "id":     vid_id,
            "title":  vid_title,
            "dur":    dur_str,
            "chunks": processed_chunks,
        })

    if not videos_data:
        print("❌ No video data processed.")
        sys.exit(1)

    # Build and write HTML
    html = build_html(args, videos_data)
    out_path.write_text(html, encoding="utf-8")
    size_kb = len(html) // 1024
    print(f"\n✅ Written: {out_path} ({size_kb} KB, {len(videos_data)} videos)")
    print(f"   Add to index.html: {out_path.name}")

if __name__ == "__main__":
    main()
