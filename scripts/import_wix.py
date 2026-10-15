"""Aspire le site Wix de Baptiste : texte, liens et images de chaque page.

Sorties :
  import/pages/<slug>.json   texte (dans l'ordre) + images de la page
  import/raw/<slug>.html     HTML brut, pour vérification
  assets/img/wix/<media-id>  images en résolution originale
"""
import json
import pathlib
import re
import sys
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

BASE = "https://baptistegmtc.wixsite.com/website"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "import"
IMG = ROOT / "assets" / "img" / "wix"
MEDIA_RE = re.compile(r"static\.wixstatic\.com/media/([0-9a-zA-Z_]+~mv2\.[a-zA-Z]+|[0-9a-f]{32}\.[a-zA-Z]+)")
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

session = requests.Session()
session.headers.update(HEADERS)


def slug_of(url):
    path = urllib.parse.urlparse(url).path
    rest = path.split("/website", 1)[1].strip("/")
    return rest or "accueil"


def page_data(url, html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    texts = []
    for block in soup.select('[data-testid="richTextElement"]'):
        comp = block.find_parent(attrs={"id": True})
        for el in block.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
            if el.find(["p", "li"]):
                continue
            t = el.get_text(" ", strip=True)
            if t:
                texts.append({"tag": el.name, "text": t, "comp": comp.get("id") if comp else None})
    images = []
    seen = set()
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        m = MEDIA_RE.search(src)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            images.append({"id": m.group(1), "alt": img.get("alt", ""),
                           "w": img.get("width"), "h": img.get("height")})
    # Images présentes seulement dans le JSON embarqué (galeries, fonds)
    extra = [i for i in dict.fromkeys(MEDIA_RE.findall(html)) if i not in seen]
    links = sorted({a["href"].split("?")[0].split("#")[0] for a in soup.find_all("a", href=True)
                    if a["href"].startswith(BASE)})
    return {"url": url, "title": title, "texts": texts, "images": images,
            "images_extra": extra, "links": links}


def download(media_id):
    dest = IMG / media_id
    if dest.exists():
        return
    r = session.get(f"https://static.wixstatic.com/media/{media_id}", timeout=60)
    if r.ok:
        dest.write_bytes(r.content)
    else:
        print("échec image", media_id, r.status_code, file=sys.stderr)


def main():
    (OUT / "pages").mkdir(parents=True, exist_ok=True)
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    IMG.mkdir(parents=True, exist_ok=True)
    todo = [BASE, BASE + "/projets", BASE + "/ecrits-recherches", BASE + "/a-propos-de-moi"]
    done = set()
    while todo:
        url = todo.pop(0).rstrip("/")
        if url in done:
            continue
        done.add(url)
        r = session.get(url, timeout=60)
        print(r.status_code, url)
        if not r.ok:
            continue
        slug = slug_of(url)
        (OUT / "raw" / f"{slug}.html").write_text(r.text, encoding="utf-8")
        data = page_data(url, r.text)
        (OUT / "pages" / f"{slug}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        for img in data["images"]:
            download(img["id"])
        for extra in data["images_extra"]:
            download(extra)
        todo += [l for l in data["links"] if l.rstrip("/") not in done]
        time.sleep(0.5)


if __name__ == "__main__":
    main()
