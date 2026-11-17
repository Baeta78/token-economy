"""Turns the raw images in assets-src/ into the sprite strips the live office uses.

    python tools/build_sprites.py

For each PNG it finds the frames (pieces separated by empty columns), crops them,
scales them to a common size, lines them up by the feet (bottom center) and writes one
horizontal strip with equal cells to static/office/sprites/, plus manifest.json.

Raw images come from an image model, so each pose arrives at its own scale. Character
poses are normalized by height: the frame's visible height becomes POSE_HEIGHT[pose]
times the standing height, so every pose of every character ends up at the same size.
Needs Pillow (already required by the tray app).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets-src"
OUT = ROOT / "static" / "office" / "sprites"

STAND = 360  # standing character height in the strip, px (shown at about half that)

# visible height of each pose, relative to standing (hair top to the lowest point)
POSE_HEIGHT = {
    "idle": 1.0, "idle_b": 1.0, "walk_front": 0.97, "walk_back": 0.97, "coffee": 1.0,
    "sleep": 0.97, "machine": 0.97, "celebrate": 0.98, "type": 0.86, "think": 0.8, "ref": 1.0,
}
# which way the pose looks, so the scene knows when to mirror it
POSE_FACES = {"walk_front": "right", "walk_back": "left", "type": "right", "think": "right",
              "machine": "left", "idle": "left", "idle_b": "left", "coffee": "left",
              "celebrate": "left", "sleep": "right"}
# per-image exceptions, when a character's drawing looks the other way from POSE_FACES
FACES_OVERRIDE = {"theo_walk_back": "right", "theo_idle": "right", "theo_idle_b": "right",
                  "theo_coffee": "right", "theo_celebrate": "right",
                  "kai_idle": "right", "kai_idle_b": "right", "kai_coffee": "right", "kai_celebrate": "right",
                  "lia_idle": "right", "lia_idle_b": "right", "lia_coffee": "right", "lia_celebrate": "right",
                  "bruno_idle": "right", "bruno_idle_b": "right", "bruno_coffee": "right", "bruno_celebrate": "right",
                  "maya_idle": "right", "maya_idle_b": "right", "maya_coffee": "right", "maya_celebrate": "right"}
# per-image height exceptions (seated naps, poses drawn at another scale); tuned by eye
HEIGHT_OVERRIDE = {"theo_sleep": 0.73, "theo_think": 0.88, "kai_sleep": 0.73, "kai_think": 0.88,
                   "kai_coffee": 0.93, "kai_celebrate": 0.92, "lia_type": 0.95,
                   "lia_sleep": 0.85, "lia_think": 0.9, "lia_celebrate": 0.93,
                   "bruno_type": 0.8, "bruno_sleep": 0.72, "bruno_think": 0.82,
                   "bruno_coffee": 0.92, "bruno_celebrate": 0.92,
                   "maya_idle": 1.05, "maya_idle_b": 1.05, "maya_sleep": 0.8, "maya_think": 0.88}
# naps drawn seated (head on folded arms) happen in the desk chair; standing ones by the sofa
SEATED = {"theo_sleep", "kai_sleep", "lia_sleep", "bruno_sleep", "maya_sleep"}
# characters drawn taller or shorter than the rest (Bruno is described as tall)
CHAR_SCALE = {"bruno": 1.06}
CHARACTERS = {"nina", "theo", "kai", "lia", "bruno", "maya"}
OTHER_HEIGHT = {"bot": 150, "cat": 120, "machine": 330, "tokens": 64, "fx": 160, "icons": 72, "vault": 200}
SKIP = {"ref", "keyart"}  # reference sheets only guide the image model
# room backgrounds keep their own size (they fill the whole scene)
KEEP_SIZE = ("bg_",)
# theme props, scaled to this height in the strip
PROP_HEIGHT = {"desk": 300, "desk_b": 300, "door_closed": 300, "door_open": 300, "whiteboard": 300,
               "rug": 300, "plant_small": 160, "plant_tall": 360, "alarm_off": 130, "alarm_on": 130}
# per-image heights for poses much lower than the group's tallest one (a curled-up cat)
NAME_HEIGHT = {"cat_sit": 120, "cat_walk": 100, "cat_stretch": 92, "cat_sleep": 70}
# frames each strip should have: effects and scattered particles leave empty columns
# inside one frame, so the closest pieces are merged back until the count matches
EXPECT = {"fx_sparkle": 4, "fx_puff": 4, "cat_walk": 4, "vault": 3, "tokens": 4,
          "bot_float": 2, "bot_work": 2, "loft_alarm_off": 1, "loft_alarm_on": 1,
          "cat_sit": 1, "cat_sleep": 1, "cat_stretch": 1}
MACHINE_MAX_W = 300
GRID = {"icons"}  # icon sheets in rows: cut into rows first, then into icons, left to right
ALPHA_MIN = 24


def _runs(filled: list[bool], min_len: float) -> list[tuple[int, int]]:
    segs, start = [], None
    for x, f in enumerate(filled + [False]):
        if f and start is None:
            start = x
        elif not f and start is not None:
            if x - start > min_len:
                segs.append((start, x))
            start = None
    return segs


def frames(im: Image.Image, expect: int | None = None) -> list[Image.Image]:
    """Splits a strip into frames by fully empty columns; drops tiny specks.
    With `expect`, pieces are merged across the narrowest gaps until there are that many."""
    a = im.getchannel("A").point(lambda v: 255 if v > ALPHA_MIN else 0)
    w, h = im.size
    filled = [a.crop((x, 0, x + 1, h)).getbbox() is not None for x in range(w)]
    if expect:
        segs = _runs(filled, 2)  # keep small particles: they belong to a frame
        while len(segs) > expect:
            i = min(range(len(segs) - 1), key=lambda j: segs[j + 1][0] - segs[j][1])
            segs[i:i + 2] = [(segs[i][0], segs[i + 1][1])]
    else:
        segs = _runs(filled, max(12, w * 0.02))
    out = []
    for x0, x1 in segs:
        bb = a.crop((x0, 0, x1, h)).getbbox()
        if bb:
            out.append(im.crop((x0 + bb[0], bb[1], x0 + bb[2], bb[3])))
    return out


def grid_frames(im: Image.Image) -> list[Image.Image]:
    """Icon sheets: rows split by empty rows, then each row into icons."""
    a = im.getchannel("A").point(lambda v: 255 if v > ALPHA_MIN else 0)
    w, h = im.size
    filled = [a.crop((0, y, w, y + 1)).getbbox() is not None for y in range(h)]
    out = []
    for y0, y1 in _runs(filled, max(12, h * 0.02)):
        out += frames(im.crop((0, y0, w, y1)))
    return out


def strip(parts: list[Image.Image], height: int) -> tuple[Image.Image, int, int]:
    tallest = max(p.height for p in parts)
    k = height / tallest
    parts = [p.resize((max(1, round(p.width * k)), max(1, round(p.height * k))), Image.LANCZOS) for p in parts]
    cw = max(p.width for p in parts) + 4
    ch = max(p.height for p in parts) + 4
    sheet = Image.new("RGBA", (cw * len(parts), ch), (0, 0, 0, 0))
    for i, p in enumerate(parts):
        sheet.alpha_composite(p, (i * cw + (cw - p.width) // 2, ch - 2 - p.height))
    return sheet, cw, ch


def main() -> int:
    if not SRC.exists():
        print("assets-src/ not found")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict = {}
    idle_widths: dict[str, int] = {}  # "<x>_idle" sorts before "<x>_on"
    for path in sorted(SRC.rglob("*.png")):
        name = path.stem
        m = re.match(r"([a-z]+)_(.+)", name)
        if m:
            group, pose = m.groups()
        elif re.fullmatch(r"[a-z]+", name):  # one-image sets (tokens, vault, icons)
            group, pose = name, "items"
        else:
            continue
        if pose in SKIP:
            continue
        im = Image.open(path).convert("RGBA")
        expect = EXPECT.get(name) or (3 if group == "machine" and pose.endswith("_on") else
                                      1 if group == "machine" else None)
        parts = grid_frames(im) if group in GRID else frames(im, expect)
        if not parts:
            print(f"skip {name}: nothing visible")
            continue
        if pose.startswith(KEEP_SIZE):
            im.save(OUT / f"{name}.png", optimize=True)
            manifest.setdefault(group, {})[pose] = {"file": f"{name}.png", "frames": 1, "w": im.width, "h": im.height}
            print(f"{name}: background {im.width}x{im.height}")
            continue
        if group in CHARACTERS:
            height = round(STAND * CHAR_SCALE.get(group, 1.0) * HEIGHT_OVERRIDE.get(name, POSE_HEIGHT.get(pose, 1.0)))
        else:
            height = NAME_HEIGHT.get(name) or PROP_HEIGHT.get(pose, OTHER_HEIGHT.get(group, 300))
        # a running machine has extras on top (hologram, paper): keep the body as wide as when idle
        idle_w = idle_widths.get(name[:-3] + "_idle") if group == "machine" and name.endswith("_on") else None
        if group == "machine" and name.endswith("_idle"):
            p = parts[0]  # wide, low machines (the map table) would dwarf the others at full height
            height = min(height, round(MACHINE_MAX_W * p.height / p.width))
        if idle_w:
            k = idle_w / max(p.width for p in parts)
            height = round(max(p.height for p in parts) * k)
        sheet, cw, ch = strip(parts, height)
        if group == "machine" and name.endswith("_idle"):
            idle_widths[name] = cw - 4
        sheet.save(OUT / f"{name}.png", optimize=True)
        entry = {"file": f"{name}.png", "frames": len(parts), "w": cw, "h": ch}
        if group in CHARACTERS and pose in POSE_FACES:
            entry["faces"] = FACES_OVERRIDE.get(name, POSE_FACES[pose])
        if name in SEATED:
            entry["seated"] = True
        manifest.setdefault(group, {})[pose] = entry
        print(f"{name}: {len(parts)} frame(s), cell {cw}x{ch}")
    (OUT / "manifest.json").write_text(json.dumps({"stand": STAND, "sprites": manifest}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
