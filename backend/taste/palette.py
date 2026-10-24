import base64
import io
from PIL import Image, ImageOps

MAX_EDGE = 1024


def load(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image)
    return image.convert('RGB')


def distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** .5


def background(image: Image.Image):
    """Median border color, if the border is mostly one color (studio/product shots); else None."""
    w, h = image.size
    border = [image.getpixel((x, y)) for x in range(w) for y in (0, h - 1)]
    border += [image.getpixel((x, y)) for y in range(h) for x in (0, w - 1)]
    median = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))
    close = sum(distance(c, median) < BACKGROUND_DISTANCE for c in border)
    return median if close >= .6 * len(border) else None


def skin(p):
    """Skin-tone pixel (a standard RGB + chroma rule that covers light to deep skin). Beige, camel and nude fabric
    can match too, so callers keep these when the garments themselves are in those colors."""
    r, g, b = p
    cr = 128 + .5 * r - .4187 * g - .0813 * b
    cb = 128 - .1687 * r - .3313 * g + .5 * b
    return (r > 95 and g > 40 and b > 20 and max(p) - min(p) > 15 and abs(r - g) > 15 and r > g and r > b
            and 135 <= cr <= 180 and 85 <= cb <= 135)


# Garment color words that look like skin in pixels; when Claude sees these, skin-range pixels count as clothing.
SKIN_LIKE = ('beige', 'tan', 'camel', 'nude', 'blush', 'peach', 'sand', 'taupe', 'caramel', 'cognac', 'brown',
             'mocha', 'latte', 'khaki', 'oatmeal', 'apricot', 'rose', 'terracotta', 'rust', 'copper', 'bronze')


def skin_like(colors):
    return any(word in c.lower() for c in colors for word in SKIN_LIKE)


BACKGROUND_DISTANCE = 40
MERGE_DISTANCE = 28
MIN_SHARE = .03  # drops anti-aliased edge blends and specks


def palette(image: Image.Image, count=5, keep_skin_tones=False) -> list[str]:
    """Dominant garment colors measured from pixels, so color claims don't rely on the model alone.
    Drops a uniform background and skin, and merges near-duplicate shades. keep_skin_tones keeps the skin range
    for photos whose garments are themselves beige, camel, nude and similar."""
    small = image.copy()
    # Nearest-neighbour sampling keeps real pixel colors instead of inventing edge blends.
    small.thumbnail((160, 160), Image.Resampling.NEAREST)
    pixels = list(small.getdata())
    bg = background(small)
    if bg is not None:
        foreground = [p for p in pixels if distance(p, bg) >= BACKGROUND_DISTANCE]
        # A nearly empty foreground means the photo really is one flat color.
        pixels = foreground if len(foreground) >= .03 * len(pixels) else pixels
    if not keep_skin_tones:
        clothes = [p for p in pixels if not skin(p)]
        pixels = clothes if len(clothes) >= .1 * len(pixels) else pixels  # e.g. a close-up of a hand: keep all
    sample = Image.new('RGB', (len(pixels), 1))
    sample.putdata(pixels)
    quantized = sample.quantize(colors=count * 3, method=Image.Quantize.MEDIANCUT)
    flat = quantized.getpalette()
    chosen = []
    for share, i in sorted(quantized.getcolors(), reverse=True):
        if share < MIN_SHARE * len(pixels):
            break
        color = tuple(flat[i * 3:i * 3 + 3])
        if all(distance(color, c) >= MERGE_DISTANCE for c in chosen):
            chosen.append(color)
        if len(chosen) == count:
            break
    return ['#%02x%02x%02x' % c for c in chosen]


def normalized_jpeg(image: Image.Image) -> bytes:
    image = image.copy()
    image.thumbnail((MAX_EDGE, MAX_EDGE))
    out = io.BytesIO()
    image.save(out, format='JPEG', quality=85)
    return out.getvalue()


def claude_block(jpeg: bytes) -> dict:
    return {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
        'data': base64.standard_b64encode(jpeg).decode()}}
