import json, re, html, urllib.request, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

FEEDS = {
 "Markets": ["https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms","https://www.moneycontrol.com/rss/latestnews.xml","https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"],
 "India": ["https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en","https://www.thehindu.com/news/national/feeder/default.rss"],
 "World": ["https://feeds.bbci.co.uk/news/world/rss.xml","https://www.aljazeera.com/xml/rss/all.xml"],
 "Tech": ["https://techcrunch.com/feed/","https://www.theverge.com/rss/index.xml"],
 "Space": ["https://www.nasa.gov/feed/","https://spaceflightnow.com/feed/"],
}

def ln(e): return e.tag.split('}')[-1]
def txt(item, *names):
    for c in item.iter():
        if ln(c) in names and (c.text or "").strip(): return c.text.strip()
    return ""
def strip(h): return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",h or ""))).strip()
def words(t,n=55):
    w=t.split(" "); return " ".join(w[:n])+"…" if len(w)>n else t
def when(s):
    try:
        d=parsedate_to_datetime(s)
    except Exception:
        try: d=datetime.fromisoformat(s.replace("Z","+00:00"))
        except Exception: return 0
    if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
    return int(d.timestamp())

def parse(data):
    root=ET.fromstring(data)
    ft=""
    for c in root.iter():
        if ln(c)=="title": ft=(c.text or "").strip(); break
    src=re.split(r"[-|:]",ft)[0].strip()
    out=[]
    for it in root.iter():
        if ln(it) not in ("item","entry"): continue
        link=""
        for c in it:
            if ln(c)=="link":
                link=c.get("href") or (c.text or "").strip()
                if link: break
        desc=txt(it,"description","summary","encoded","content")
        im=""
        for c in it.iter():
            if ln(c) in ("content","thumbnail","enclosure") and c.get("url") and (ln(c)!="enclosure" or "image" in (c.get("type") or "image")):
                im=c.get("url"); break
        if not im:
            m=re.search(r'<img[^>]+src=["\']([^"\']+)',html.unescape(desc))
            if m: im=m.group(1)
        t=strip(txt(it,"title"))
        if not t or not link: continue
        out.append({"id":txt(it,"guid","id") or link,"title":t,"sum":words(strip(desc)),"img":im,"link":link,"ts":when(txt(it,"pubDate","published","updated","date")),"src":src})
    return out


from concurrent.futures import ThreadPoolExecutor

def meta(page, prop):
    for m in re.finditer(r"<meta[^>]+>", page):
        tag = m.group(0)
        if re.search(r'(property|name)=["\']%s["\']' % re.escape(prop), tag):
            c = re.search(r'content=(["\'])(.*?)\1', tag, re.S)
            if c: return html.unescape(c.group(2)).strip()
    return ""

JUNK = re.compile(r"trending|share price|also read|read more|follow us|subscribe|sign in|log in|cookie|advertis|click here|download the app|copyright|all rights|newsletter|whatsapp|telegram", re.I)

def clean_para(t):
    w = t.split()
    if len(w) < 12 or len(w) > 120: return False
    if JUNK.search(t): return False
    if t.count(" , ") >= 2 or t.count(" | ") >= 2: return False
    if not re.search(r'[.!?"\u201d\u2019]$', t): return False
    return True

def enrich(item):
    try:
        req = urllib.request.Request(item["link"], headers={"User-Agent": "Mozilla/5.0 (PulseNews)"})
        page = urllib.request.urlopen(req, timeout=15).read(600000).decode("utf-8", "ignore")
    except Exception:
        return item
    m = re.search(r"<article[^>]*>(.*?)</article>", page, re.S)
    scope = m.group(1) if m else ""
    og = strip(meta(page, "og:description") or meta(page, "description"))
    parts = []
    if og and not JUNK.search(og) and len(og.split()) >= 8: parts.append(og)
    for pm in re.finditer(r"<p[^>]*>(.*?)</p>", scope, re.S):
        t = strip(pm.group(1))
        if clean_para(t) and not any(t[:40] in x for x in parts):
            parts.append(t)
        if len(" ".join(parts).split()) >= 55: break
    cand = " ".join(parts)
    feed = item["sum"] if not JUNK.search(item["sum"]) else ""
    best = cand if len(cand.split()) > len(feed.split()) else feed
    item["sum"] = words(best, 70)
    if not item["img"]:
        item["img"] = meta(page, "og:image")
    return item

import urllib.parse

def to_hindi(text):
    if not text: return ""
    url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=hi&dt=t&q=" + urllib.parse.quote(text)
    for _ in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))
            return "".join(part[0] for part in data[0] if part and part[0])
        except Exception:
            pass
    return ""

def add_hindi(item):
    item["title_hi"] = to_hindi(item["title"])
    item["sum_hi"] = to_hindi(item["sum"])
    return item

result={}
for tab,urls in FEEDS.items():
    items=[]
    for u in urls:
        try:
            req=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0 (PulseNews)"})
            items+=parse(urllib.request.urlopen(req,timeout=25).read())
        except Exception as e:
            print("FAIL",u,e)
    seen=set(); uniq=[]
    for i in sorted(items,key=lambda x:-x["ts"]):
        k=i["title"][:40]
        if k in seen: continue
        seen.add(k); uniq.append(i)
    top = uniq[:25]
    with ThreadPoolExecutor(8) as ex:
        top = list(ex.map(enrich, top))
        top = list(ex.map(add_hindi, top))
    result[tab] = top
    print(tab,len(result[tab]),"translated:",sum(1 for i in result[tab] if i.get("title_hi")))
result["_updated"]=int(datetime.now(timezone.utc).timestamp())
json.dump(result,open("news.json","w"),ensure_ascii=False)
