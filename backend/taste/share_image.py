"""A shareable picture of the owner's moodboard, for posting on Instagram / TikTok (story, 9:16) or X (square).

Drawn with PIL from the lookbook photos already on disk: paper background, "My taste", the top photos of each style
cluster as taped prints, cluster names, the measured colour swatches and a small "made with Niche" mark.
"""
import io
import random
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from .models import Profile, TasteImage

FONTS = Path(__file__).parent / 'fonts'  # OFL fonts, the same ones the site uses
SIZES = {'story': (1080, 1920), 'square': (1080, 1080)}
PAPER = (243, 241, 235)
INK = (29, 28, 26)


def font(name, size):
    files = {'script': 'cedarville-cursive-latin-400-normal.woff', 'display': 'playfair-display-latin-400-italic.woff',
             'sans': 'inter-tight-latin-400-normal.woff'}
    try:
        return ImageFont.truetype(str(FONTS / files[name]), size)
    except OSError:
        return ImageFont.load_default(size)


def paper(size, seed):
    """Warm page stock with fine grain, like the moodboard."""
    rand = random.Random(seed)
    w, h = size
    noise = Image.effect_noise((w // 2, h // 2), 18).resize(size).filter(ImageFilter.GaussianBlur(.6))
    base = Image.new('RGB', size, PAPER)
    grain = Image.merge('RGB', [noise.point(lambda v: v - 128 + c) for c in PAPER])
    page = Image.blend(base, grain, .35)
    draw = ImageDraw.Draw(page)
    for _ in range(int(w * h / 9000)):  # sparse darker fibres
        x, y = rand.randrange(w), rand.randrange(h)
        draw.point((x, y), fill=tuple(c - rand.randint(18, 40) for c in PAPER))
    return page


def print_tile(photo: Image.Image, size, angle):
    """A cropped photo with a white border, a soft shadow and a strip of tape, slightly rotated."""
    w, h = size
    border = max(8, w // 28)
    framed = Image.new('RGB', (w + 2 * border, h + 2 * border), (252, 251, 248))
    framed.paste(ImageOps.fit(photo, (w, h), Image.Resampling.LANCZOS, centering=(.5, .35)), (border, border))
    tape = Image.new('RGBA', (int(w * .42), max(18, h // 14)), (233, 223, 199, 205))
    layer = Image.new('RGBA', (framed.width + 40, framed.height + 60), (0, 0, 0, 0))
    shadow = Image.new('RGBA', framed.size, (0, 0, 0, 70)).filter(ImageFilter.GaussianBlur(1))
    layer.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(8)), (24, 34))
    layer.paste(framed, (20, 28))
    layer.alpha_composite(tape.rotate(-3, expand=True), ((layer.width - tape.width) // 2, 14))
    return layer.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)


def label(draw, xy, text, width, size, smallest=30, lines=2):
    """Cluster name in the script font: shrinks to fit the width, then wraps (never cut mid-word)."""
    words = text.split()
    for px in range(size, smallest - 1, -2):
        f = font('script', px)
        if draw.textlength(text, font=f) <= width:
            draw.text(xy, text, font=f, fill=INK)
            return px
    f, rows, row = font('script', smallest), [], ''
    for word in words:
        trial = f'{row} {word}'.strip()
        if row and draw.textlength(trial, font=f) > width:
            rows.append(row)
            row = word
        else:
            row = trial
    rows.append(row)
    draw.multiline_text(xy, '\n'.join(rows[:lines]), font=f, fill=INK, spacing=2)
    return smallest * len(rows[:lines])


def first_hexes(images: list[TasteImage], count=6):
    seen = []
    for image in images:
        for c in image.palette[:2]:
            if re.fullmatch(r'#[0-9a-fA-F]{6}', c) and c.lower() not in seen:
                seen.append(c.lower())
    return seen[:count]


def groups(profile: Profile, images: list[TasteImage], per=3, most=3):
    by_id = {x.id: x for x in images}
    out = []
    for cluster in profile.clusters:
        members = [by_id[i] for i in cluster.image_ids if i in by_id][:per]
        if members:
            out.append((cluster.name, members))
    if not out and images:
        out.append(('', images[:per]))
    return out[:most]


def render(profile: Profile, images: list[TasteImage], load, fmt='story') -> bytes:
    """load(image) -> PIL image of that lookbook photo."""
    w, h = SIZES[fmt]
    page = paper((w, h), profile.id).convert('RGBA')
    draw = ImageDraw.Draw(page)
    rand = random.Random(f'{profile.id}:{profile.version}')
    story = fmt == 'story'
    margin = 72
    draw.text((margin, 60 if story else 30), 'My taste', font=font('script', 150 if story else 100), fill=INK)

    clusters = groups(profile, images, per=3 if story else 2, most=3)
    if story:
        # One band per cluster: its name, then up to three prints across.
        top, band = 300, 455
        for row, (name, members) in enumerate(clusters):
            y = top + row * band
            if name:
                label(draw, (margin, y), name, w - 2 * margin, 54, smallest=36)
            tile = (270, 340)
            gap = (w - 2 * margin - len(members) * (tile[0] + 16)) // max(1, len(members) - 1) if len(members) > 1 else 0
            for i, image in enumerate(members):
                x = margin - 20 + i * (tile[0] + 16 + gap)
                page.alpha_composite(print_tile(load(image), tile, rand.uniform(-3, 3)), (x, y + 64))
    else:
        # Square: one column per cluster, its name above two prints.
        cols = max(1, len(clusters))
        col_w = (w - 2 * margin) // cols
        tile = (col_w - 64, 268)
        for c, (name, members) in enumerate(clusters):
            x0 = margin + c * col_w
            if name:
                label(draw, (x0, 186), name, col_w - 20, 36, smallest=26)
            for r, image in enumerate(members[:2]):
                page.alpha_composite(print_tile(load(image), tile, rand.uniform(-3, 3)),
                                     (x0 - 18 + (r % 2) * 14, 266 + r * 316))

    # Colour swatches and the mark along the bottom.
    y = h - (150 if story else 96)
    for i, hex_ in enumerate(first_hexes(images)):
        cx = margin + 30 + i * 74
        draw.ellipse((cx - 28, y - 28, cx + 28, y + 28), fill=hex_, outline=(0, 0, 0, 30))
    mark, made = font('display', 64 if story else 48), font('sans', 26 if story else 22)
    niche_w = draw.textlength('Niche', font=mark)
    made_w = draw.textlength('made with ', font=made)
    x = w - margin - niche_w
    draw.text((x - made_w, y - 4), 'made with ', font=made, fill=(110, 108, 104), anchor='lm')
    draw.text((x, y), 'Niche', font=mark, fill=INK, anchor='lm')

    out = io.BytesIO()
    page.convert('RGB').save(out, format='PNG', optimize=True)
    return out.getvalue()
