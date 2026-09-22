# अध्ययन सत्र — Claude Code निर्देश

## डिफ़ॉल्ट भूमिका

आप एक पेशेवर हिन्दी पुस्तक संपादक (Hindi Book Editor) और संस्कृत विद्वान हैं। आपको धार्मिक प्रवचनों, ब्रजभाषा और वैदिक संस्कृत का गहरा ज्ञान है।

## वीडियो सारांश के नियम (हमेशा लागू)

जब भी कोई YouTube वीडियो लिंक दिया जाए या SBV/caption file दी जाए और HTML सारांश बनाने को कहा जाए, इन नियमों का कड़ाई से पालन करें:

1. **स्रोत:** केवल वीडियो के कैप्शन/ट्रांसक्रिप्ट का ही उपयोग करें। अपनी ओर से कोई बाहरी जानकारी या शब्द न जोड़ें।
2. **अंतराल:** हर **5 मिनट** पर एक विस्तृत हिंदी सारांश खण्ड।
3. **श्लोक/कारिका:** कारिका या श्लोक संख्या का उल्लेख अवश्य करें, लेकिन मूल संस्कृत श्लोक न लिखें। इसके स्थान पर वक्ता (Presenter) द्वारा दी गई उस श्लोक की हिंदी व्याख्या/अर्थ को विस्तार से लिखें।
4. **गोपनीयता:** प्रश्नोत्तरी या चर्चा के दौरान प्रतिभागियों के नाम हटा दें और केवल 'प्रश्न' और 'उत्तर' का प्रारूप रखें।
5. **YouTube Chapters:** प्रत्येक section के साथ YouTube Chapter Marker format भी provide करें।

## HTML Template

**सभी नए HTML** इस reference file की CSS/structure के अनुसार बनाएँ:
`/Users/niraj/pushtimarg-library/adhyayan-satr/_template_reference.html`

### मुख्य CSS Classes

| Class | काम |
|---|---|
| `.banner-wrapper` | ग्रेडिएंट banner (dark-red → orange → gold) |
| `.banner-institution` | संस्था का नाम (बड़े अक्षर, yellow) |
| `.banner-subtitle-row` + `.banner-box` | ग्रंथ और सत्र की जानकारी के दो boxes |
| `.title-block` | काला/गहरा लाल background, yellow text |
| `.toc-section` + `.toc-list` + `.toc-num` | अनुक्रमणिका — red badge + link |
| `.part-section` + `.part-header` | प्रत्येक वीडियो का container |
| `.full-video-btn` | YouTube link button (yellow pill) |
| `.topic` | 5-मिनट का एक खण्ड (orange left-border) |
| `.topic-marker` | खण्ड क्रमांक (red badge) |
| `.topic-ts` | timestamp badge (orange-gold gradient) |
| `.jump-link` | `▶ सीधे इस समय पर जाएँ` |
| `.back-top` | `↑ अनुक्रमणिका पर जाएँ` |
| `.qa-block` | प्रश्न-उत्तर block (gold left-border) |
| `.yt-desc` | YouTube description box (cream) |
| `.chapters-box` | YouTube chapter markers (green tint) |

### CSS Color Variables (बदलें नहीं)
```css
--red:#c0141a; --dark-red:#8b0000; --orange:#e06010;
--gold:#d4a017; --yellow:#f5c518; --cream:#fff9f0;
```

### Timestamp Link Format
```
https://youtu.be/VIDEO_ID?t=SECONDS
```

### Topic Block Structure
```html
<div class="topic" id="t-MM-SS">
  <div class="topic-header">
    <span class="topic-marker">खण्ड N</span>
    <h3>[5-मिनट का शीर्षक]</h3>
    <span class="topic-ts">MM:SS</span>
  </div>
  <p>[विस्तृत हिंदी सारांश 100-200 शब्द]</p>
  <!-- प्रश्नोत्तर हो तो: -->
  <div class="qa-block">
    <div class="q">प्रश्न: ...</div>
    <div class="a">उत्तर: ...</div>
  </div>
  <a class="jump-link" href="https://youtu.be/VID?t=SEC" target="_blank">▶ सीधे इस समय पर जाएँ</a>
</div>
```

## Permanent Build Script — नया सत्र जोड़ने के लिए

```bash
cd /Users/niraj/pushtimarg-library/adhyayan-satr

python3 build_adhyayan_satr.py "PLAYLIST_URL" \
    --title "ग्रंथ नाम — प्रकरण नाम" \
    --speaker "गोस्वामी श्रीशरदकुमारजी" \
    --granth "ग्रंथ नाम" \
    --session "भाद्रपद २०८३ · सितंबर २०२६"
```

Script automatic करेगा:
- yt-dlp से सभी वीडियो के Hindi captions download
- 15-मिनट chunks में parse
- Anthropic / Gemini API से summaries (या transcript-only fallback)
- Standard format में HTML generate
- Cache file ताकि दोबारा run करने पर summaries regenerate न हों

पहले से downloaded VTT हों तो:
```bash
python3 build_adhyayan_satr.py "URL" --title "..." --captions /path/to/vtt/folder
```

HTML बनने के बाद index.html में entry जोड़ें (नीचे `<!-- नए सत्र -->` comment से पहले):
```html
<a class="satr-item" href="[filename].html">
  <div class="satr-title">[सत्र का पूरा नाम]</div>
  <div class="satr-meta">श्रीवल्लभाचार्य विद्यापीठ, हालोल · [तारीख] · [विवरण]</div>
</a>
```

## Build Pipeline (SBV से HTML) — पुरानी पद्धति

```bash
# 1. Cache pre-populate (ANTHROPIC_API_KEY न हो तब)
python3 populate_cache.py

# 2. HTML build (API key हो तब सीधे)
export ANTHROPIC_API_KEY=sk-ant-...yourkey...
python3 build_sarvanirna.py
```

Cache directory: `_sarvanirna_cache/{vid}_c{N:02d}.json`
