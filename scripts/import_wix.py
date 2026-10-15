"""Aspire le site Wix de Baptiste : HTML de chaque page et images.

Sorties :
  import/raw/<slug>.html          HTML brut de chaque page
  assets/img/wix/<media-id>.webp  images, redimensionnées (2400 px max) et compressées

Le texte des pages est ensuite extrait en local par scripts/build_from_wix.py.

Usage : python3 scripts/import_wix.py              tout réimporter
        python3 scripts/import_wix.py orientation  redresser les photos prises de travers
        python3 scripts/import_wix.py recadrages   images recadrées comme sur Wix
        python3 scripts/import_wix.py manquantes   images des pages pas encore téléchargées
        python3 scripts/import_wix.py videos       vidéos des galeries (et leur image d'aperçu)
"""
import io
import pathlib
import re
import shutil
import sys
import time
import urllib.parse

import requests
from PIL import Image, ImageOps

BASE = "https://baptistegmtc.wixsite.com/website"
ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "import" / "raw"
IMG = ROOT / "assets" / "img" / "wix"
VIDEO = ROOT / "assets" / "video" / "wix"
MAX_PX = 2400
MEDIA_RE = re.compile(r"static\.wixstatic\.com/media/([0-9a-zA-Z_]+~mv2\.[a-zA-Z]+|[0-9a-f]{32}\.[a-zA-Z]+)")
VIDEO_RE = re.compile(r'"type":"video".*?"posters":\[(.*?)\].*?"qualities":\[((?:[^\[\]]|\[[^\]]*\])*)\].*?"mediaUrl":"([0-9a-z]+_[0-9a-f]{32})"')
CROP_RE = re.compile(r"static\.wixstatic\.com/media/([^/\"]+)/v1/crop/x_(\d+),y_(\d+),w_(\d+),h_(\d+)/fill/w_(\d+),h_(\d+)")
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

Image.MAX_IMAGE_PIXELS = None
session = requests.Session()
session.headers.update(HEADERS)


def webp_name(media_id):
    return media_id.split(".")[0].replace("~", "-") + ".webp"


def crop_name(media_id, x, y, w, h):
    return media_id.split(".")[0].replace("~", "-") + f"-crop-{x}-{y}-{w}-{h}.webp"


def download(media_id, force=False):
    dest = IMG / webp_name(media_id)
    if dest.exists() and not force:
        return
    r = session.get(f"https://static.wixstatic.com/media/{media_id}", timeout=120)
    if not r.ok:
        print("échec image", media_id, r.status_code, file=sys.stderr)
        return
    try:
        im = Image.open(io.BytesIO(r.content))
        im.seek(0)
    except Exception as e:  # format non pris en charge (svg, etc.)
        print("image ignorée", media_id, e, file=sys.stderr)
        return
    im = ImageOps.exif_transpose(im)  # photos d'appareil : sens indiqué dans les données EXIF
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    im.save(dest, "WEBP", quality=80, method=6)


def main():
    shutil.rmtree(ROOT / "import" / "pages", ignore_errors=True)
    RAW.mkdir(parents=True, exist_ok=True)
    IMG.mkdir(parents=True, exist_ok=True)
    for f in IMG.iterdir():  # originaux d'un import précédent
        if f.suffix != ".webp":
            f.unlink()

    home = session.get(BASE, timeout=60).text
    slugs = sorted(set(re.findall(r'"pageUriSEO":"([^"]+)"', home)) - {"accueil"})
    pages = {"accueil": BASE} | {s: f"{BASE}/{urllib.parse.quote(s)}" for s in slugs}
    for slug, url in pages.items():
        r = session.get(url, timeout=60)
        print(r.status_code, url)
        if not r.ok:
            continue
        (RAW / f"{slug}.html").write_text(r.text, encoding="utf-8")
        for media_id in dict.fromkeys(MEDIA_RE.findall(r.text)):
            download(media_id)
        time.sleep(0.5)


def orientation():
    """Reconvertit les images dont l'original porte une rotation EXIF (oubliée lors du premier import)."""
    ids = {m for f in RAW.glob("*.html") for m in MEDIA_RE.findall(f.read_text(encoding="utf-8"))}
    for media_id in sorted(ids):
        if not (IMG / webp_name(media_id)).exists() or not media_id.lower().endswith((".jpg", ".jpeg")):
            continue
        r = session.get(f"https://static.wixstatic.com/media/{media_id}", headers={"Range": "bytes=0-131071"}, timeout=60)
        try:
            sens = Image.open(io.BytesIO(r.content)).getexif().get(0x0112, 1)
        except Exception:
            continue
        if sens not in (1, None):
            print("redressée", media_id, sens)
            download(media_id, force=True)


def manquantes():
    """Télécharge les images des pages qui manquent, sauf le décor commun à toutes les pages (icônes)."""
    pages = [set(MEDIA_RE.findall(f.read_text(encoding="utf-8"))) for f in RAW.glob("*.html")]
    for media_id in sorted(set().union(*pages)):
        if sum(media_id in p for p in pages) < len(pages) / 2 and not (IMG / webp_name(media_id)).exists():
            print("téléchargée", media_id)
            download(media_id)


def videos():
    """Vidéos des galeries Wix, en 720p (ou moins), avec leurs images d'aperçu."""
    VIDEO.mkdir(parents=True, exist_ok=True)
    for f in RAW.glob("*.html"):
        for posters, qualities, media in set(VIDEO_RE.findall(f.read_text(encoding="utf-8"))):
            for poster in re.findall(r'"url":"([^"]+)"', posters):
                download(poster)
            dest = VIDEO / f"{media}.mp4"
            if dest.exists():
                continue
            dispo = re.findall(r'"quality":"(\d+p)"', qualities)
            q = next((q for q in ("720p", "480p", "1080p") if q in dispo), None)
            r = session.get(f"https://video.wixstatic.com/video/{media}/{q}/mp4/file.mp4", timeout=300)
            if r.ok and q:
                dest.write_bytes(r.content)
                print("vidéo", dest.name, q, len(r.content) // 1024, "Ko")
            else:
                print("échec vidéo", media, q, r.status_code, file=sys.stderr)


def recadrages():
    """Télécharge, tels que Wix les affiche, les recadrages faits dans l'éditeur Wix (dans la plus grande
    taille proposée par la page, en général le double de la taille affichée)."""
    crops = {}
    for f in RAW.glob("*.html"):
        for media, x, y, w, h, fw, fh in CROP_RE.findall(f.read_text(encoding="utf-8")):
            key = (media, x, y, w, h)
            if int(fw) > crops.get(key, (0, 0))[0]:
                crops[key] = (int(fw), int(fh))
    for (media, x, y, w, h), (fw, fh) in sorted(crops.items()):
        dest = IMG / crop_name(media, x, y, w, h)
        if dest.exists():
            continue
        k = min(1, MAX_PX / max(fw, fh))
        url = (f"https://static.wixstatic.com/media/{media}/v1/crop/x_{x},y_{y},w_{w},h_{h}"
               f"/fill/w_{round(fw * k)},h_{round(fh * k)},al_c,q_90/{media}")
        r = session.get(url, headers={"Accept": "image/jpeg,image/png"}, timeout=60)
        try:
            im = Image.open(io.BytesIO(r.content))
        except Exception as e:
            print("recadrage ignoré", media, e, file=sys.stderr)
            continue
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
        im.save(dest, "WEBP", quality=80, method=6)
        print("recadrée", dest.name)


if __name__ == "__main__":
    taches = {"main": main, "orientation": orientation, "recadrages": recadrages, "manquantes": manquantes,
              "videos": videos}
    for t in sys.argv[1:] or ["main"]:
        taches[t]()
