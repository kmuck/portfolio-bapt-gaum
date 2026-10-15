"""Génère le corps des pages projets (_projets/*.md) à partir du HTML Wix importé.

Lit import/raw/<slug>.html (voir import_wix.py), remet textes et images dans l'ordre
de lecture de la mise en page Wix, et réécrit le corps de _projets/<slug>.md en
conservant son en-tête (titre, catégorie, ordre...).

Usage : python3 scripts/build_from_wix.py [slug ...]
"""
import collections
import pathlib
import re
import sys

from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "import" / "raw"
PROJETS = ROOT / "_projets"
IMG_DIR = ROOT / "assets" / "img" / "wix"
MEDIA_RE = re.compile(r"static\.wixstatic\.com/media/([0-9a-zA-Z_]+~mv2\.[a-zA-Z]+|[0-9a-f]{32}\.[a-zA-Z]+)")
MESH = "inlineContent-gridContainer"


def webp_name(media_id):
    return media_id.split(".")[0].replace("~", "-") + ".webp"


def mesh_positions(html):
    """{(conteneur, composant): (ligne, marge haute, gauche)} d'après le CSS de la grille Wix."""
    pos = {}
    pat = r'\[data-mesh-id=([\w-]+?)' + MESH + r'\] > \[id="([\w-]+)"\][^{]*\{([^}]*)\}'
    for mesh, cid, rule in re.findall(pat, html):
        row = re.search(r"grid-area:\s*(\d+)", rule)
        top = re.search(r"margin:\s*(-?[\d.]+)px", rule)
        left = re.search(r"left:\s*(-?[\d.]+)px", rule)
        pos.setdefault((mesh, cid), (int(row.group(1)) if row else 0,
                                     float(top.group(1)) if top else 0,
                                     float(left.group(1)) if left else 0))
    return pos


def text_of(el):
    for br in el.find_all("br"):
        br.replace_with("\n")
    t = el.get_text("")
    t = t.replace("​", "").replace("\xa0", " ")
    return "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in t.split("\n")).strip()


def covered_by(el, style_re):
    """Vrai si tout le texte de el est dans des spans dont le style correspond."""
    full = re.sub(r"\s+", "", el.get_text(""))
    if not full:
        return False
    inside = "".join(s.get_text("") for s in el.find_all("span", style=style_re)
                     if not s.find_parent("span", style=style_re))
    return re.sub(r"\s+", "", inside) == full


def big_font(el):
    for s in el.find_all(style=re.compile(r"font-size:\s*\d+px")):
        if int(re.search(r"font-size:\s*(\d+)px", s["style"]).group(1)) >= 18:
            return True
    return False


def rich_text_items(block):
    items = []
    for el in block.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
        if el.find(["p", "li"]):
            continue
        t = text_of(el)
        if not t:
            continue
        if el.name.startswith("h"):
            kind = "titre"
        elif big_font(el):
            kind = "inter"
        elif covered_by(el, re.compile(r"font-style:\s*italic")):
            kind = "legende" if len(t) < 200 else "italique"
        else:
            kind = "texte"
        items.append((kind, t))
    return items


def walk(tag, pos, out):
    if tag.get("data-testid") == "richTextElement":
        out.extend(rich_text_items(tag))
        return
    if "wixui-collapsible-text__text" in (tag.get("class") or []):
        t = text_of(tag)
        if t:
            out.append(("texte", t))
        return
    if tag.name == "img":
        m = MEDIA_RE.search(tag.get("src") or "")
        if m:
            out.append(("image", m.group(1)))
        return
    if "background-image" in (tag.get("style") or ""):  # vignettes des galeries Wix
        m = MEDIA_RE.search(tag["style"])
        if m:
            out.append(("image", m.group(1)))
    kids = [c for c in tag.children if isinstance(c, Tag)]
    mesh = tag.get("data-mesh-id", "")
    if mesh.endswith(MESH):
        mesh = mesh[: -len(MESH)]

        def key(ik):
            i, k = ik
            cid = k.get("id") or (k.find(id=True) or {}).get("id")
            return pos.get((mesh, cid), (10**6, 0, i))
        kids = [k for _, k in sorted(enumerate(kids), key=key)]
    for k in kids:
        walk(k, pos, out)


def page_items(html, decor):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    walk(soup.find(id="PAGES_CONTAINER"), mesh_positions(html), out)
    seen, items = set(), []
    for kind, val in out:
        if kind == "image":
            if val in decor or val in seen:
                continue
            seen.add(val)
        items.append((kind, val))
    return items


def to_markdown(items):
    lines, galerie = [], []

    def flush():
        if not galerie:
            return
        imgs = "\n".join(f'  {{% include img.html src="/assets/img/wix/{webp_name(i)}" lien=true %}}' for i in galerie)
        cls = "galerie" if len(galerie) > 1 else "planche"
        lines.append(f'<div class="{cls}">\n{imgs}\n</div>\n')
        galerie.clear()

    for kind, val in items:
        if kind == "image":
            galerie.append(val)
            continue
        flush()
        if kind == "inter":
            lines.append(f"## {val}\n")
        elif kind == "italique":
            lines.append("\n\n".join(f"*{p}*" for p in val.split("\n") if p) + "\n")
        elif kind == "legende":
            lines.append(f'<p class="legende">{val}</p>\n')
        else:
            pts = val.split("\n")
            if all(p.lstrip().startswith("-") for p in pts if p):
                lines.append("\n".join("- " + p.lstrip("- ").strip() for p in pts if p) + "\n")
            else:
                lines.append("\n\n".join(p for p in pts if p) + "\n")
    flush()
    return "\n".join(lines)


def decor_images():
    """Images présentes sur au moins trois pages : fonds, icônes."""
    count = collections.Counter()
    for f in RAW.glob("*.html"):
        count.update(set(MEDIA_RE.findall(f.read_text(encoding="utf-8"))))
    return {m for m, n in count.items() if n >= 3}


def localize_links():
    """Remplace les liens vers les images Wix par les copies locales, quand elles existent."""
    files = [*PROJETS.glob("*.md"), *(ROOT / "_ecrits").glob("*.md"), ROOT / "index.html", ROOT / "a-propos.md"]
    url_re = re.compile(r"https://" + MEDIA_RE.pattern + r"[^\"')\s]*")
    for f in files:
        txt = f.read_text(encoding="utf-8")
        new = url_re.sub(lambda m: f"/assets/img/wix/{webp_name(m.group(1))}"
                         if (IMG_DIR / webp_name(m.group(1))).exists() else m.group(0), txt)
        if new != txt:
            f.write_text(new, encoding="utf-8")


def main(slugs):
    decor = decor_images()
    for md in sorted(PROJETS.glob("*.md")):
        slug = md.stem
        raw = RAW / f"{slug}.html"
        if slugs and slug not in slugs or not raw.exists():
            continue
        items = page_items(raw.read_text(encoding="utf-8"), decor)
        titre = next((v for k, v in items if k == "titre"), "")
        items = [(k, v) for k, v in items if k != "titre"]
        missing = [i for k, i in items if k == "image" and not (IMG_DIR / webp_name(i)).exists()]
        front = md.read_text(encoding="utf-8").split("---", 2)[1]
        front = re.sub(r"\nimages:\n(  - .*\n)+", "\n", front)
        front = re.sub(r'\nsous_titre: .*', "", front)
        if "|" in titre:
            front = front.rstrip("\n") + f'\nsous_titre: "{titre.split("|", 1)[1].strip()}"\n'
        md.write_text(f"---{front}---\n\n{to_markdown(items)}", encoding="utf-8")
        n_img = sum(k == "image" for k, _ in items)
        print(f"{slug}: {len(items) - n_img} blocs de texte, {n_img} images"
              + (f", {len(missing)} images manquantes" if missing else ""))
    localize_links()


if __name__ == "__main__":
    main(set(sys.argv[1:]))
