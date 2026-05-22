"""Génère les icônes PWA : carré arrondi orange dégradé + grue blanche stylisée."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "static" / "icons"
OUT.mkdir(parents=True, exist_ok=True)


def make_icon(size: int, out: Path, with_padding: bool = True):
    """Dessine une icône carrée à la taille demandée.

    with_padding : si True (192/512), garde des marges pour fit le contenu.
                   Si False, occupe tout le canvas (apple-touch-icon).
    """
    # Couche dégradée ambre → orange
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Dégradé vertical (haut = ambre clair, bas = orange foncé)
    top = (251, 191, 36, 255)    # #fbbf24
    bot = (217, 119, 6, 255)     # #d97706
    for y in range(size):
        r = y / max(1, size - 1)
        c = (
            int(top[0] + (bot[0] - top[0]) * r),
            int(top[1] + (bot[1] - top[1]) * r),
            int(top[2] + (bot[2] - top[2]) * r),
            255,
        )
        d.line([(0, y), (size, y)], fill=c)

    # Masque rond (rectangle arrondi)
    radius = int(size * 0.22)
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    img.putalpha(mask)

    # Crane blanche par-dessus
    s = size
    sw = max(2, s // 24)             # épaisseur du trait
    white = (255, 255, 255, 255)

    cx = int(s * 0.42)               # mât décalé à gauche pour laisser plus de jib à droite
    top_y = int(s * 0.26)
    base_y = int(s * 0.84)
    jib_right = int(s * 0.92)
    jib_left = int(s * 0.12)
    cable_x = int(s * 0.78)
    cable_y = int(s * 0.62)          # câble qui descend bien bas

    sd = ImageDraw.Draw(img)

    def stroke(p1, p2, w=sw):
        sd.line([p1, p2], fill=white, width=w)

    # mât (vertical)
    stroke((cx, top_y), (cx, base_y))
    # base trapèze (deux barres horizontales)
    stroke((cx - int(s * 0.13), base_y), (cx + int(s * 0.13), base_y))
    stroke((cx - int(s * 0.10), int(base_y - s * 0.06)), (cx + int(s * 0.10), int(base_y - s * 0.06)))
    # contreventement bas
    stroke((cx - int(s * 0.10), int(base_y - s * 0.06)), (cx - int(s * 0.13), base_y))
    stroke((cx + int(s * 0.10), int(base_y - s * 0.06)), (cx + int(s * 0.13), base_y))

    # flèche horizontale (du contre-jib à l'extrémité droite)
    stroke((jib_left, top_y), (jib_right, top_y))
    # diagonale support droite (du mât vers extrémité)
    stroke((cx, top_y), (jib_right - int(s * 0.05), top_y + int(s * 0.10)))
    # diagonale support gauche
    stroke((cx, top_y), (jib_left + int(s * 0.02), top_y + int(s * 0.08)))
    # contrepoids (rectangle plein à gauche)
    cw_x1, cw_y1 = jib_left - int(s * 0.005), top_y - int(s * 0.04)
    cw_x2, cw_y2 = jib_left + int(s * 0.08), top_y + int(s * 0.04)
    sd.rectangle([cw_x1, cw_y1, cw_x2, cw_y2], fill=white)

    # câble vertical bien visible
    stroke((cable_x, top_y), (cable_x, cable_y), w=max(2, sw - 2))
    # crochet (petit U)
    hk_w = int(s * 0.05)
    stroke((cable_x - hk_w, cable_y), (cable_x + hk_w, cable_y))
    stroke((cable_x - hk_w, cable_y), (cable_x - hk_w, cable_y + int(s * 0.03)))
    stroke((cable_x + hk_w, cable_y), (cable_x + hk_w, cable_y + int(s * 0.03)))

    img.save(out, "PNG")
    print(f"OK {out.name}  ({size}x{size})")


def main():
    make_icon(192, OUT / "icon-192.png")
    make_icon(512, OUT / "icon-512.png")
    make_icon(180, OUT / "apple-touch-icon.png", with_padding=False)
    # Favicon
    make_icon(64, OUT / "favicon-64.png")
    print(f"Icônes générées dans {OUT}")


if __name__ == "__main__":
    main()
