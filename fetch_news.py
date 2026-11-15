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
            c = re.search(r'content=["\']([^"\']*)', tag)
            if c: return html.unescape(c.group(1)).strip()
    return ""

def enrich(item):
    try:
        req = urllib.request.Request(item["link"], headers={"User-Agent": "Mozilla/5.0 (PulseNews)"})
        page = urllib.request.urlopen(req, timeout=15).read(600000).decode("utf-8", "ignore")
    except Exception:
        return item
    paras = []
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", page, re.S):
        t = strip(m.group(1))
        if len(t) > 70 and "cookie" not in t.lower() and "subscribe" not in t.lower():
            paras.append(t)
        if len(" ".join(paras).split()) > 90: break
    body = " ".join(paras)
    og = strip(meta(page, "og:description") or meta(page, "description"))
    best = body if len(body.split()) >= 30 else (og if len(og.split()) > len(item["sum"].split()) else item["sum"])
    item["sum"] = words(best, 70)
    if not item["img"]:
        item["img"] = meta(page, "og:image")
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
    result[tab] = top
    print(tab,len(result[tab]))
result["_updated"]=int(datetime.now(timezone.utc).timestamp())
json.dump(result,open("news.json","w"),ensure_ascii=False)
