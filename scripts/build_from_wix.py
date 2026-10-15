"""Génère le corps des pages projets (_projets/*.md) à partir du HTML Wix importé.

Lit import/raw/<slug>.html (voir import_wix.py) et réécrit le corps de _projets/<slug>.md
en conservant son en-tête (titre, catégorie, ordre...). Avec import/captures/boites/<slug>.json
(positions relevées par capture_wix.js), la mise en page Wix est reproduite : éléments côte
à côte, largeurs, cadrage des images et espacements. Sans ce fichier, textes et images sont
mis l'un sous l'autre dans l'ordre de lecture.

Usage : python3 scripts/build_from_wix.py [slug ...]
"""
import collections
import html
import json
import pathlib
import re
import sys

from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "import" / "raw"
PROJETS = ROOT / "_projets"
IMG_DIR = ROOT / "assets" / "img" / "wix"
BOITES = ROOT / "import" / "captures" / "boites"
MEDIA_RE = re.compile(r"static\.wixstatic\.com/media/([0-9a-zA-Z_]+~mv2\.[a-zA-Z]+|[0-9a-f]{32}\.[a-zA-Z]+)")
MESH = "inlineContent-gridContainer"
LARGEUR = 980  # largeur de la colonne de contenu Wix
BANDEAU = 38  # hauteur du bandeau de titre, en haut de chaque page projet
DEBUG = bool(__import__("os").environ.get("DEBUG_WIX"))


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


def rich_text(el):
    """Texte de el avec le gras et l'italique en <strong>/<em> ; <br> devient un saut de ligne."""
    def walk(node, bold, ital):
        if isinstance(node, NavigableString):
            t = html.escape(str(node).replace("​", "").replace("\xa0", " "), quote=False)
            if not t:
                return ""
            if ital:
                t = f"<em>{t}</em>" if t.strip() else t
            if bold:
                t = f"<strong>{t}</strong>" if t.strip() else t
            return t
        if node.name == "br":
            return "\n"
        style = node.get("style") or ""
        b = bold or bool(re.search(r"font-weight:\s*(bold|[6-9]00)", style))
        i = ital or bool(re.search(r"font-style:\s*italic", style))
        if re.search(r"font-weight:\s*normal", style):
            b = False
        if re.search(r"font-style:\s*normal", style):
            i = False
        return "".join(walk(c, b, i) for c in node.children)

    t = walk(el, False, False)
    t = re.sub(r"</(strong|em)>(\s*)<\1>", r"\2", t)  # fusionne les balises voisines
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
    for s in [el, *el.find_all(style=re.compile(r"font-size:\s*\d+px"))]:
        m = re.search(r"font-size:\s*(\d+)px", s.get("style") or "")
        if m and int(m.group(1)) >= 18:
            return True
    return False


def rich_text_items(block):
    """[(type, texte)] d'un bloc de texte Wix. Les paragraphes Wix n'ont pas de marge : les
    lignes qui se suivent sont réunies, un paragraphe vide marque un saut de paragraphe."""
    items, vide = [], True
    for el in block.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
        if el.find(["p", "li"]):
            continue
        t = text_of(el)
        if not t:
            vide = True
            continue
        brut = t
        if big_font(el):
            kind = "inter-caslon" if el.find(style=re.compile(r"font-family:\s*'?adobe-caslon")) else "inter"
            st = el.get("style") or ""
            fs, lh = re.search(r"font-size:\s*(\d+)px", st), re.search(r"line-height:\s*([\d.]+em)", st)
            t = (rich_text(el), f"{fs.group(1)}px/{lh.group(1)}" if fs and lh else None)
        elif covered_by(el, re.compile(r"font-style:\s*italic")) and len(t) < 200:
            kind = "legende"
        elif el.name == "li" or el.find_parent("li"):
            kind, t = "liste", rich_text(el)
        else:
            kind, t = "texte", rich_text(el)
        if el.name.startswith("h"):
            # le premier titre de la page est celui du bandeau ; les autres sont mis en page selon leur style
            kind, t = "titre", (brut, kind, t)
        if items and items[-1][0] == kind and kind in ("texte", "legende", "liste") and (not vide or kind == "liste"):
            items[-1] = (kind, items[-1][1] + "\n" + t)
        else:
            items.append((kind, t))
        vide = False
    return items


def alignement(block):
    """Alignement le plus courant des paragraphes d'un bloc de texte Wix."""
    c = collections.Counter()
    for p in block.find_all(["p", "li"]):
        m = re.search(r"text-align:\s*(\w+)", p.get("style") or "")
        c[m.group(1) if m else "left"] += len(p.get_text())
    return c.most_common(1)[0][0] if c else "left"


def taille_texte(paras):
    """Taille et interligne les plus courants de ces paragraphes Wix, ex. "13px/2em"."""
    c = collections.Counter()
    for p in paras:
        st = p.get("style") or ""
        fs, lh = re.search(r"font-size:\s*(\d+)px", st), re.search(r"line-height:\s*([\d.]+em)", st)
        if fs and lh and int(fs.group(1)) < 18:
            c[f"{fs.group(1)}px/{lh.group(1)}"] += len(p.get_text())
    return c.most_common(1)[0][0] if c else None


def walk(tag, pos, out, comp=None):
    """Ajoute à out les éléments (type, valeur, composant Wix, extra) dans l'ordre de lecture."""
    if tag.get("id", "").startswith("comp-"):
        comp = tag["id"]
    if tag.get("data-testid") == "richTextElement":
        extra = (alignement(tag), taille_texte(tag.find_all("p")))
        out.extend((k, v, comp, extra) for k, v in rich_text_items(tag))
        return
    if "wixui-collapsible-text__text" in (tag.get("class") or []):
        t = text_of(tag)
        if t:
            out.append(("texte", t, comp, ("left", None)))
        return
    if tag.name == "img":
        m = MEDIA_RE.search(tag.get("src") or "")
        if m:
            fit = "contain" if "contain" in (tag.get("style") or "") or "/v1/fit/" in tag["src"] else "cover"
            crop = re.search(r"/v1/crop/x_(\d+),y_(\d+),w_(\d+),h_(\d+)/", tag["src"])
            out.append(("image", m.group(1), comp, (fit, crop.groups() if crop else None)))
        return
    grille = tag.find(id="pro-gallery-container-" + tag["id"]) if tag.get("id", "").startswith("comp-") else None
    if grille and not tag.select_one(".thumbnailItem"):  # galerie Wix en grille : images côte à côte
        cases = []
        for it in grille.select(".gallery-item-container"):
            st = it.get("style") or ""
            px = [float(m.group(1)) if (m := re.search(k + r":\s*(-?[\d.]+)px", st)) else 0
                  for k in ("left", "top", "width", "height")]
            m = MEDIA_RE.search(str(it))
            if m:
                cases.append((m.group(1), *px))
        out.append(("grille", cases, comp, None))
        return
    if tag.get("id", "").startswith("comp-") and tag.select_one(".thumbnailItem"):
        thumbs = [t for t in tag.select(".thumbnailItem")
                  if t.find_parent(id=re.compile("^comp-")) is tag]
        if thumbs:  # galerie Wix (diaporama avec vignettes)
            ids = list(dict.fromkeys(m.group(1) for t in thumbs
                                     if (m := MEDIA_RE.search(t.get("style") or ""))))
            out.append(("diaporama", ids, comp, None))
            return
    if "background-image" in (tag.get("style") or ""):
        m = MEDIA_RE.search(tag["style"])
        if m:
            out.append(("image", m.group(1), comp, ("cover", None)))
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
        walk(k, pos, out, comp)


def ordre_comps(html):
    soup = BeautifulSoup(html, "html.parser")
    return {t["id"]: i for i, t in enumerate(soup.find_all(id=re.compile("^comp-")))}


def page_items(html, decor):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    walk(soup.find(id="PAGES_CONTAINER"), mesh_positions(html), out)
    seen, items = set(), []
    for kind, val, cid, extra in out:
        if kind == "grille":
            val = [c for c in val if c[0] not in decor]
            if val:
                items.append((kind, val, cid, extra))
            continue
        if kind == "diaporama":
            val = list(dict.fromkeys(i for i in val if i not in decor))
            if val:
                items.append((kind, val, cid, extra))
            continue
        if kind == "image":
            # une même image peut revenir ailleurs sur la page (galerie puis image seule)
            if val in decor or (cid, val) in seen:
                continue
            seen.add((cid, val))
        items.append((kind, val, cid, extra))
    return items


def style_texte(html):
    """Taille et interligne les plus courants du texte de la page."""
    soup = BeautifulSoup(html, "html.parser")
    return taille_texte(soup.find(id="PAGES_CONTAINER").select("[data-testid=richTextElement] p"))


# Rendu Markdown

def ligne(t):
    """Échappe un début de ligne que Markdown prendrait pour une liste ou un titre."""
    t = re.sub(r"^([-+*#>])(\s)", r"\\\1\2", t)
    return re.sub(r"^(\d+)\.(\s)", r"\1\\.\2", t)


def texte_md(kind, val):
    if kind in ("inter", "inter-caslon"):
        texte, taille = val
        titre = " ".join(l for l in texte.split("\n") if l.strip())
        if kind == "inter-caslon":
            return f"## {titre}\n{{: .caslon}}\n"
        if taille and taille != "22px/1.3em":  # taille par défaut des intertitres
            fs, lh = taille.split("/")
            return f'## {titre}\n{{: style="font-size:{fs};line-height:{lh}"}}\n'
        return f"## {titre}\n"
    lignes = [l for l in val.split("\n") if l.strip()]
    if kind == "legende":
        return '<p class="legende">' + "<br>".join(lignes) + "</p>\n"
    if kind == "liste" or all(l.startswith("-") for l in lignes):
        return "\n".join("- " + l.lstrip("-• ").strip() for l in lignes) + "\n"
    return "<br>\n".join(ligne(l) for l in lignes) + "\n"


def crop_name(media_id, x, y, w, h):
    return media_id.split(".")[0].replace("~", "-") + f"-crop-{x}-{y}-{w}-{h}.webp"


def image_md(media, extra, w=None, h=None):
    """Image Wix ; extra = (cadrage, recadrage fait dans l'éditeur Wix ou None)."""
    fit, crop = extra
    src = f"/assets/img/wix/{webp_name(media)}"
    if crop and (IMG_DIR / crop_name(media, *crop)).exists():  # voir import_wix.py recadrages
        src = f"/assets/img/wix/{crop_name(media, *crop)}"
    ratio = f' ratio="{w}/{h}"' if w and h else ""
    cadre = ' cadre="contain"' if fit == "contain" else ""
    return f'{{% include img.html src="{src}" lien=true{ratio}{cadre} %}}'


def style(dx, w, zw, mt, st=()):
    """Position d'un élément dans sa zone : décalage et largeur en %, marge haute en px.
    st : déclarations en plus."""
    st = list(st)
    if abs(dx) > 2:
        st.append(f"--x:{dx / zw * 100:.2f}%")
    if w < zw - 4:
        st.append(f"--w:{w / zw * 100:.2f}%")
    if mt > 0:
        st.append(f"--mt:{round(mt)}px")
    return f' style="{";".join(st)}"' if st else ""


def debug(b):
    return f' data-wix="{b["box"][1]}"' if DEBUG else ""


def bloc_md(b, zx, zw, mt, texte_page, hauteur):
    x, y, w, h = b["box"]
    st = style(x - zx, w, zw, mt)
    items = b["items"]
    if all(k == "image" for k, *_ in items):
        imgs = "".join(image_md(v, fit, w, h) for k, v, fit in items)
        if not b.get("dessus"):
            return f'<div class="bloc"{st}{debug(b)}>{imgs}</div>\n'
        etiquettes = []
        for t in b["dessus"]:
            tx, ty, tw, th = t["box"]
            pos = [f"--y:{(ty - y) / h * 100:.2f}%"]
            md = bloc_md({**t, "box": (tx - x, ty, tw, th)}, 0, w, 0, texte_page, th)
            etiquettes.append(md.replace('class="bloc', 'class="etiquette', 1).replace(' style="', f' style="{pos[0]};', 1))
        return (f'<div class="bloc superpose"{st}{debug(b)} markdown="1">\n<div>{imgs}</div>\n'
                + "".join(etiquettes) + "</div>\n")
    if items[0][0] == "grille":
        cases, droite = sorted(items[0][1], key=lambda c: (c[2], c[1])), 0
        gw = max(c[1] + c[3] for c in cases)
        parts = []
        for media, l, t, cw, ch in cases:
            parts.append(f'<div class="case"{style(l - droite, cw, gw, 0)}>{image_md(media, ("cover", None), round(cw), round(ch))}</div>')
            droite = l + cw
        return f'<div class="bloc grille"{st}{debug(b)}>' + "\n".join(parts) + "</div>\n"
    if items[0][0] == "diaporama":
        imgs = ",".join(f"/assets/img/wix/{webp_name(i)}" for i in items[0][1])
        return f'<div class="bloc"{st}{debug(b)}>\n{{% include diaporama.html images="{imgs}" hauteur={h - 82} %}}\n</div>\n'
    align, taille = items[0][2] if items[0][0] != "image" else ("left", None)
    # hauteur du bloc Wix (il compte les lignes vides en fin de texte) et taille de texte propre au bloc
    extra = [f"--h:{hauteur}px"]
    if taille and taille != texte_page:
        extra.insert(0, f"font:{taille} var(--raleway)")
    st = style(x - zx, w, zw, mt, extra)
    cls = "bloc" + {"center": " centre", "right": " droite", "left": " gauche"}.get(align, "")
    corps = "\n".join(image_md(v, x) + "\n" if k == "image" else texte_md(k, v) for k, v, x in items)
    return f'<div class="{cls}"{st}{debug(b)} markdown="1">\n\n{corps}\n</div>\n'


def bandes(blocs):
    """Regroupe les blocs qui se chevauchent verticalement (une rangée de la page). Deux rangées
    successives aux colonnes alignées (images puis leurs légendes) n'en font qu'une."""
    out = []
    for b in sorted(blocs, key=lambda b: (b["box"][1], b["box"][0])):
        x, y, w, h = b["box"]
        if out and y < out[-1][1] - 5:
            out[-1][0].append(b)
            out[-1][1] = max(out[-1][1], y + h)
        else:
            out.append([[b], y + h])
    fusion = []
    for bande, _ in out:
        if fusion and alignees(colonnes(fusion[-1]), colonnes(bande)) \
                and len(colonnes(fusion[-1] + bande)) == len(colonnes(bande)):
            fusion[-1] = fusion[-1] + bande
        else:
            fusion.append(bande)
    return fusion


def alignees(a, b):
    if len(a) < 2 or len(a) != len(b):
        return False
    span = lambda col: (min(x["box"][0] for x in col), max(x["box"][0] + x["box"][2] for x in col))
    return all(sa[0] < sb[1] and sb[0] < sa[1] for sa, sb in zip(map(span, a), map(span, b)))


def colonnes(blocs):
    """Regroupe les blocs d'une rangée qui se chevauchent horizontalement (de plus d'un quart
    de leur largeur : sur Wix des images voisines empiètent parfois de quelques pixels)."""
    out = []
    for b in sorted(blocs, key=lambda b: b["box"][0]):
        x, y, w, h = b["box"]
        if out and out[-1][2] - x > max(5, min(w, out[-1][2] - out[-1][1]) / 4):
            out[-1][0].append(b)
            out[-1][2] = max(out[-1][2], x + w)
        else:
            out.append([[b], x, x + w])
    return [blocs for blocs, *_ in out]


def zone_md(blocs, zx, zw, haut, texte_page):
    """Markdown des blocs d'une zone (la page ou une colonne), de haut en bas."""
    out, bas, restants = [], haut, list(blocs)
    while restants:
        bande = bandes(restants)[0]
        cols = colonnes(bande)
        if len(cols) == 1:
            # un seul bloc à la fois : ceux du dessous peuvent former une rangée
            b = min(bande, key=lambda b: (b["box"][1], b["box"][0]))
            restants.remove(b)
            x, y, w, h = b["box"]
            # un bloc de texte Wix compte ses lignes vides : il peut chevaucher ce qui suit
            fin = min([y + h] + [o["box"][1] for o in bande if o is not b and o["box"][1] >= y])
            out.append(bloc_md(b, zx, zw, y - bas, texte_page, fin - y))
            bas = max(bas, fin)
            continue
        for b in bande:
            restants.remove(b)
        top = min(b["box"][1] for b in bande)
        parts, droite = [], zx
        for col in cols:
            cx = min(b["box"][0] for b in col)
            cr = max(b["box"][0] + b["box"][2] for b in col)
            cy = min(b["box"][1] for b in col)
            cls = "col etroite" if (cr - cx) / zw < 0.35 else "col"  # deux par ligne sur mobile
            parts.append(f'<div class="{cls}"{style(cx - droite, cr - cx, zw, cy - top)} markdown="1">\n\n'
                         f'{zone_md(col, cx, cr - cx, cy, texte_page)}\n</div>\n')
            droite = cr
        out.append(f'<div class="rangee"{style(0, zw, zw, top - bas)} markdown="1">\n\n' + "\n".join(parts) + "\n</div>\n")
        bas = max(bas, max(b["box"][1] + b["box"][3] for b in bande))
    return "\n".join(out)


def superpositions(blocs, ordre):
    """Un texte posé sur une image devient une étiquette de l'image s'il est au-dessus d'elle
    dans l'ordre d'affichage Wix ; s'il est en dessous, il est caché par l'image et retiré."""
    images = [b for b in blocs if b["box"] and [k for k, *_ in b["items"]] == ["image"]]
    for t in blocs:
        if not t["box"] or t["items"][0][0] in ("image", "diaporama", "grille"):
            continue
        x, y, w, h = t["box"]
        for i in images:
            ix, iy, iw, ih = i["box"]
            dx = min(x + w, ix + iw) - max(x, ix)
            dy = min(y + h, iy + ih) - max(y, iy)
            if dx > 0 and dy > 0 and dx * dy > 0.3 * w * h:
                if ordre.get(t["cid"], 0) > ordre.get(i["cid"], 0):
                    i.setdefault("dessus", []).append({**t})
                else:
                    print(f"  texte caché sous une image : {str(t['items'][0][1])[:40]!r}")
                t["box"] = None
                break


def to_markdown(items, boxes, texte_page, ordre):
    """Corps Markdown de la page. boxes : {composant: (x, y, largeur, hauteur)} ou None ;
    ordre : {composant: rang dans le HTML}, qui est l'ordre d'empilement Wix."""
    blocs = []
    for kind, val, cid, extra in items:
        seul = ("diaporama", "grille")
        if blocs and blocs[-1]["cid"] == cid and kind not in seul and blocs[-1]["items"][0][0] not in seul:
            blocs[-1]["items"].append((kind, val, extra))
        else:
            blocs.append({"cid": cid, "items": [(kind, val, extra)]})
    bas, perdus = BANDEAU, []
    for b in blocs:
        box = boxes.get(b["cid"]) if boxes else None
        if box and (box[2] <= 0 or box[3] <= 0):
            b["box"] = None  # masqué sur ordinateur
            continue
        if not box:
            perdus.append(b["cid"])
            box = (0, bas + 1, LARGEUR, 1)  # pas de position : à la suite
        x, y, w, h = box
        x, r = max(round(x), 0), min(round(x + w), LARGEUR)
        b["box"] = (x, round(y), r - x, round(h))
        bas = max(bas, y + h)
    if boxes and perdus:
        print(f"  sans position : {len(perdus)} blocs")
    superpositions(blocs, ordre)
    return zone_md([b for b in blocs if b["box"]], 0, LARGEUR, BANDEAU, texte_page)


def page_boxes(slug):
    f = BOITES / f"{slug}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    px, py, pw, _ = d["page"]
    x0 = px + (pw - LARGEUR) / 2
    boxes = {cid: (x - x0, y - py, w, h) for cid, (x, y, w, h) in d["comps"].items()}
    # Pour les textes, seule la partie écrite compte : Wix ajoute souvent des lignes vides en bas
    for cid, (y, h) in d.get("textes", {}).items():
        if cid in boxes:
            boxes[cid] = (boxes[cid][0], y - py, boxes[cid][2], h)
    return boxes


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
        page = raw.read_text(encoding="utf-8")
        items = page_items(page, decor)
        titre = next((v[0] for k, v, *_ in items if k == "titre"), "")
        if titre:  # le premier titre est celui du bandeau
            i = next(i for i, it in enumerate(items) if it[0] == "titre")
            items = items[:i] + items[i + 1:]
        items = [(v[1], v[2], cid, extra) if k == "titre" else (k, v, cid, extra) for k, v, cid, extra in items]
        ids = [i for k, v, *_ in items if k in ("image", "diaporama", "grille")
               for i in ([v] if k == "image" else v if k == "diaporama" else [c[0] for c in v])]
        missing = [i for i in ids if not (IMG_DIR / webp_name(i)).exists()]
        front = md.read_text(encoding="utf-8").split("---", 2)[1]
        front = re.sub(r"\nimages:\n(  - .*\n)+", "\n", front)
        front = re.sub(r'\n(sous_titre|texte): .*', "", front).rstrip("\n") + "\n"
        if "|" in titre:
            front += f'sous_titre: "{titre.split("|", 1)[1].strip()}"\n'
        texte = style_texte(page)
        if texte:
            front += f'texte: "{texte}"\n'
        print(f"{slug}: {sum(k not in ('image', 'diaporama', 'grille') for k, *_ in items)} blocs de texte, {len(ids)} images"
              + (f", {len(missing)} images manquantes" if missing else ""))
        md.write_text(f"---{front}---\n\n{to_markdown(items, page_boxes(slug), texte, ordre_comps(page))}", encoding="utf-8")
    localize_links()


if __name__ == "__main__":
    main(set(sys.argv[1:]))
