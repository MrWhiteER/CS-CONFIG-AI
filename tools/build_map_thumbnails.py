"""Draw original Stats illustrations. Pillow is only needed to regenerate them."""

from hashlib import sha256
from pathlib import Path
from random import Random
import sys

from PIL import Image, ImageColor, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cs2cfg.maps import MAPS

ART = ROOT / "cs2cfg/web/assets/maps"
WIDTH, HEIGHT = 480, 270
THEMES = {
    "desert": ("#6fa9b5", "#efba7c", "#a96443", "#332e34"),
    "coast": ("#79b0bc", "#eee1ba", "#589eab", "#234e62"),
    "town": ("#899cb3", "#efd1a6", "#995f56", "#3a3244"),
    "forest": ("#789da2", "#cdbb81", "#5f805f", "#29463a"),
    "industrial": ("#8095a6", "#d8c3a5", "#798591", "#313c4b"),
    "rail": ("#8d9eac", "#e4bf8c", "#a2685b", "#3c4150"),
    "city": ("#808fae", "#e3bb9d", "#65778e", "#333954"),
    "castle": ("#8398ad", "#d6ba96", "#818077", "#3f3947"),
    "snow": ("#8294b2", "#e5edf0", "#a0afc2", "#3c495e"),
    "night": ("#202645", "#e9ac7b", "#495374", "#23273e"),
    "lunar": ("#42466b", "#e2c8ac", "#8885ad", "#37324e"),
}
GROUPS = {
    "desert": "dust2 mirage anubis shortdust",
    "coast": "thera memento lake pool_day poseidon",
    "forest": "ancient shoots vineyard basalt militia safehouse",
    "industrial": "nuke cache assembly brewery baggage assault",
    "rail": "train whistle",
    "city": "vertigo overpass dogtown rooftop agency bank",
    "castle": "cbble grail sanctum stronghold monastery jura",
    "snow": "office",
    "night": "ancient_night shoots_night overpass_night",
    "lunar": "lunacy",
}
SCENE = {stem: theme for theme, stems in GROUPS.items() for stem in stems.split()}
PALETTE = {
    "mirage": ("#6ca4be", "#f1d388", "#b36e68", "#3d354e"),
    "dust2": ("#9db5ba", "#f5d497", "#c48e5d", "#5a3a34"),
    "anubis": ("#61a2b0", "#ffce82", "#b27c47", "#594136"),
    "inferno": ("#8b9fb0", "#f5c58c", "#985952", "#433849"),
    "nuke": ("#859ba9", "#d4eee6", "#849298", "#2c4956"),
}


def blend(a, b, amount):
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def draw_map(key):
    name = key.split("_", 1)[1]
    theme = SCENE.get(name, "town")
    random = Random(sha256(key.encode()).digest())
    sky, sun, walls, shadow = map(ImageColor.getrgb, PALETTE.get(name, THEMES[theme]))
    image = Image.new("RGB", (WIDTH, HEIGHT))
    d = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        d.line((0, y, WIDTH, y), fill=blend(sky, sun, min(1, y / 188) * .62))
    x = random.randint(280, 427)
    d.ellipse((x - 34, 27, x + 34, 95), fill=blend(sun, (255, 251, 220), .42))
    for layer, ground in enumerate((155, 192, 226)):
        ridge = [(0, ground - random.randint(13, 55))]
        ridge += [(x, ground - random.randint(12, 65)) for x in range(48, WIDTH, 48)]
        ridge += [(WIDTH, ground - 22), (WIDTH, HEIGHT), (0, HEIGHT)]
        d.polygon(ridge, fill=blend(sky, walls, .32 + layer * .26))
    d.polygon([(0, 226), (WIDTH, 193), (WIDTH, HEIGHT), (0, HEIGHT)],
              fill=blend(walls, shadow, .6))

    def building(x, base, width, height, style):
        top = base - height
        front = blend(walls, sun, random.uniform(.18, .5))
        side = blend(front, shadow, .46)
        d.rectangle((x, top, x + width, base), fill=front)
        d.polygon([(x + width, top), (x + width + 16, top + 11),
                   (x + width + 16, base + 5), (x + width, base)], fill=side)
        if style == "roof":
            d.polygon([(x - 5, top + 3), (x + width // 2, top - 19),
                       (x + width + 6, top + 3)], fill=side)
        elif style == "castle":
            for i in range(x, x + width, 17):
                d.rectangle((i, top - 9, min(i + 10, x + width), top), fill=front)
        else:
            d.rectangle((x - 2, top - 4, x + width + 2, top + 2), fill=blend(front, sun, .38))
        for y in range(top + 13, base - 11, 20):
            for i in range(x + 9, x + width - 7, 16):
                if random.random() < .8:
                    d.rectangle((i, y, i + 5, y + 8), fill=blend(side, shadow, .62))
        if style in ("arch", "castle"):
            door_x = x + width // 2
            d.rounded_rectangle((door_x - 11, base - 33, door_x + 11, base + 4),
                                radius=10, fill=shadow)

    if theme in ("rail", "industrial"):
        for x in (46, 90, 370):
            d.rectangle((x, 89, x + 10, 191), fill=blend(walls, shadow, .32))
            d.rectangle((x - 3, 86, x + 13, 92), fill=shadow)
    if theme == "coast" or name == "anubis" or name.startswith("overpass"):
        d.polygon([(0, 228), (480, 203), (480, 270), (0, 270)], fill=blend(sky, walls, .42))
        for y in range(225, 268, 5):
            x = random.randint(0, 410)
            d.line((x, y, x + random.randint(22, 70), y), fill=blend(sky, sun, .31))
    styles = {"desert": "arch", "coast": "arch", "town": "roof", "castle": "castle", "snow": "roof"}
    for x in range(-16, WIDTH, 59):
        width = random.randrange(40, 69)
        high = random.randrange(29, 86) + (random.randrange(12, 54) if theme == "city" else 0)
        building(x + random.randint(-8, 5), random.randint(183, 211), width, high, styles.get(theme, "flat"))
    if name.startswith("ancient"):
        for level in range(5):
            inset = 18 * level
            y = 190 - 16 * level
            d.polygon([(148 + inset, y), (339 - inset, y), (350 - inset, y + 17),
                       (137 + inset, y + 17)], fill=blend(walls, sun, .24 + level * .07))
        d.polygon([(212, 207), (237, 123), (254, 123), (274, 207)], fill=shadow)
    elif name == "anubis":
        for x in (173, 287):
            d.polygon([(x, 116), (x + 8, 100), (x + 16, 116), (x + 22, 212),
                       (x - 6, 212)], fill=blend(walls, sun, .42))
            d.rectangle((x - 11, 208, x + 26, 216), fill=shadow)
        d.polygon([(0, 242), (480, 227), (480, 270), (0, 270)], fill=blend(sky, shadow, .25))
    elif name == "mirage":
        building(184, 220, 38, 139, "flat")
        for x in (154, 327):
            d.line((x - 10, 220, x, 148), fill=shadow, width=5)
            for dx, dy in ((-30, -10), (-23, 14), (2, -27), (28, -9), (26, 11)):
                d.line((x, 148, x + dx, 148 + dy), fill=shadow, width=4)
    elif name == "dust2":
        d.polygon([(0, 255), (182, 202), (234, 194), (480, 253), (480, 270), (0, 270)],
                  fill=blend(walls, sun, .28))
    elif name == "nuke":
        for x in (171, 264):
            d.polygon([(x, 109), (x + 66, 109), (x + 54, 153), (x + 70, 220),
                       (x - 6, 220), (x + 9, 155)], fill=blend(walls, sun, .46))
            d.ellipse((x, 103, x + 66, 115), fill=shadow)
    elif name == "inferno":
        building(213, 221, 46, 137, "roof")
        d.ellipse((227, 104, 246, 123), fill=sun, outline=shadow, width=2)
        d.line((236, 108, 236, 116, 241, 118), fill=shadow, width=1)
    elif name.startswith("overpass"):
        bridge = blend(walls, shadow, .38)
        d.polygon([(0, 176), (480, 139), (480, 156), (0, 194)], fill=bridge)
        for x in (137, 324):
            d.rectangle((x, 164, x + 19, 234), fill=bridge)
    if theme == "rail":
        for y in (228, 241, 254):
            d.line((0, y, 480, y - 19), fill=blend(shadow, sun, .36), width=2)
        for x in (43, 143, 243, 343):
            d.rounded_rectangle((x, 200, x + 91, 224), radius=3, fill=walls)
            for wheel in (x + 14, x + 76):
                d.ellipse((wheel, 220, wheel + 9, 229), fill=shadow)
    if theme in ("forest", "night", "desert", "town", "castle"):
        for x in (10, 65, 399, 451):
            y = random.randrange(172, 229)
            d.line((x, y - 39, x, y + 23), fill=shadow, width=5)
            for _ in range(9):
                cx, cy = x + random.randrange(-22, 23), y + random.randrange(-56, -19)
                d.ellipse((cx - 12, cy - 9, cx + 12, cy + 9), fill=blend(walls, shadow, random.uniform(.45, .9)))
    for _ in range(1400):
        x, y = random.randrange(WIDTH), random.randrange(HEIGHT)
        image.putpixel((x, y), blend(image.getpixel((x, y)), sun if y < 150 else shadow, .14))
    return image


if __name__ == "__main__":
    for key in sorted(MAPS):
        draw_map(key).save(ART / f"{key}.webp", "WEBP", quality=86, method=6)
