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
    result[tab]=uniq[:40]
    print(tab,len(result[tab]))
result["_updated"]=int(datetime.now(timezone.utc).timestamp())
json.dump(result,open("news.json","w"),ensure_ascii=False)
