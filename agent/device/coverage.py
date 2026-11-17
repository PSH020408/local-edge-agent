"""Indoor coverage (Stage 8): walls from a floor plan, a multi-wall path-loss model fitted to measured points,
and coverage maps with contour lines and use zones.

Model (log-distance with wall and door losses, the multi-wall model of indoor propagation):

    RSSI(d, w, k) = A - 10·n·log10(d / 1 m) - L·w - D·k + X

A: signal at 1 m; n: path-loss exponent (2 in free space, about 2.5-3.5 indoors); w: walls crossed by the
straight line from the router; L: loss per wall; k: closed doors crossed; D: loss per door; X: the rest
(shadowing), whose spread is the model's error. Linear in (A, n, L, D), so it is fitted by least squares.

The floor plan of the home stays in logs/ (it is not published); tests and the example use a synthetic plan.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

# Signal needed per use, before the walk: design values from enterprise Wi-Fi guides (real-time voice and
# video at -67 dBm with SNR 25 dB; data at about -72; basic connectivity near -80). Replaced by the
# thresholds measured on the walk (SNR, MCS and latency at each point) once they exist.
PRIOR_ZONES = [(-67.0, "games and video calls", (46, 160, 67)), (-72.0, "streaming and browsing", (120, 190, 60)),
               (-80.0, "messaging only", (240, 180, 40)), (-200.0, "unreliable", (215, 60, 50))]
LEVELS = [-50, -60, -67, -72, -80]


# ---------------------------------------------------------------- the plan

def extract_walls(image: Path | str | Image.Image, dark: int = 90, min_pixels: int = 120) -> np.ndarray:
    """Walls as a boolean mask: dark pixels, thin marks removed by an opening, small specks dropped.

    Tested on the home plan: a 5x5 opening kept straight walls but lost the diagonal ones (anti-aliased, thinner);
    3x3 with a size filter keeps both and drops door arcs and furniture lines."""
    img = image if isinstance(image, Image.Image) else Image.open(image)
    rgb = np.asarray(img.convert("RGB")).astype(int)
    mask = ndimage.binary_opening(rgb.max(axis=2) < dark, structure=np.ones((3, 3)))
    labels, count = ndimage.label(mask)
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    return np.isin(labels, [i + 1 for i, s in enumerate(sizes) if s >= min_pixels])


def interior(image: Path | str | Image.Image, walls: np.ndarray, white: int = 235) -> np.ndarray:
    """Floor area: the coloured (non-white) footprint with holes filled, without the walls."""
    img = image if isinstance(image, Image.Image) else Image.open(image)
    rgb = np.asarray(img.convert("RGB")).astype(int)
    footprint = ndimage.binary_fill_holes(ndimage.binary_closing(rgb.min(axis=2) < white, np.ones((7, 7))))
    labels, count = ndimage.label(footprint)
    if count > 1:
        sizes = ndimage.sum(footprint, labels, range(1, count + 1))
        footprint = labels == (int(np.argmax(sizes)) + 1)
    return footprint & ~walls


def walls_crossed(walls: np.ndarray, a: tuple[float, float], b: tuple[float, float]) -> int:
    """Separate wall runs met along the straight line from a to b (a wall is counted once however thick)."""
    steps = max(1, int(math.dist(a, b)))
    xs = np.clip(np.rint(np.linspace(a[0], b[0], steps + 1)).astype(int), 0, walls.shape[1] - 1)
    ys = np.clip(np.rint(np.linspace(a[1], b[1], steps + 1)).astype(int), 0, walls.shape[0] - 1)
    on = walls[ys, xs]
    return int(on[0]) + int(np.count_nonzero(on[1:] & ~on[:-1]))


def segments_cross(a, b, p, q) -> bool:
    def side(o, s, t):
        return (s[0] - o[0]) * (t[1] - o[1]) - (s[1] - o[1]) * (t[0] - o[0])
    return side(a, b, p) * side(a, b, q) < 0 and side(p, q, a) * side(p, q, b) < 0


@dataclass
class Plan:
    image: Path
    m_per_px: float
    router: tuple[float, float]
    router_height_m: float = 0.1
    device_height_m: float = 0.45
    points: dict[str, dict] = field(default_factory=dict)   # id -> {"xy": [x, y], "label": "..."}
    holdout: list[str] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    doors: dict[str, list] = field(default_factory=dict)     # name -> [[x1, y1], [x2, y2]] across the opening
    _walls: np.ndarray | None = None
    _floor: np.ndarray | None = None

    @classmethod
    def load(cls, path: Path | str) -> "Plan":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["image"] = (path.parent / data["image"]).resolve()
        data["router"] = tuple(data["router"])
        return cls(**data)

    @property
    def walls(self) -> np.ndarray:
        if self._walls is None:
            self._walls = extract_walls(self.image)
        return self._walls

    @property
    def floor(self) -> np.ndarray:
        if self._floor is None:
            self._floor = interior(self.image, self.walls)
        return self._floor

    def distance_m(self, xy) -> float:
        flat = math.dist(self.router, xy) * self.m_per_px
        return max(0.3, math.hypot(flat, self.device_height_m - self.router_height_m))

    def geometry(self, xy) -> dict:
        return {"distance_m": round(self.distance_m(xy), 2), "walls": walls_crossed(self.walls, self.router, xy),
                "doors": [name for name, (p, q) in self.doors.items() if segments_cross(self.router, xy, p, q)]}


# ---------------------------------------------------------------- the model

@dataclass
class Model:
    a: float            # dBm at 1 m
    n: float            # path-loss exponent
    wall_db: float      # loss per wall
    door_db: float = 0.0
    rmse_fit: float | None = None
    terms: tuple[str, ...] = ("a", "n", "walls")

    def predict(self, distance_m, walls=0, doors_closed=0):
        d = np.maximum(np.asarray(distance_m, dtype=float), 0.3)
        return self.a - 10 * self.n * np.log10(d) - self.wall_db * np.asarray(walls) - self.door_db * np.asarray(doors_closed)


def fit(rows: list[dict], key: str = "rssi", walls: bool = True, doors: bool = False, fixed_n: float | None = None) -> Model:
    """Least squares for A, n (unless fixed), the wall loss (if walls) and the door loss (if doors)."""
    rows = [r for r in rows if r.get(key) is not None]
    y = np.array([r[key] for r in rows], dtype=float)
    logd = np.array([math.log10(max(r["distance_m"], 0.3)) for r in rows])
    columns, terms = [np.ones(len(rows))], ["a"]
    if fixed_n is None:
        columns.append(-10 * logd)
        terms.append("n")
    else:
        y = y + 10 * fixed_n * logd
    if walls:
        columns.append(-np.array([r["walls"] for r in rows], dtype=float))
        terms.append("walls")
    if doors:
        columns.append(-np.array([r.get("doors_closed", 0) for r in rows], dtype=float))
        terms.append("doors")
    x = np.column_stack(columns)
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    values = dict(zip(terms, coef))
    model = Model(a=float(values["a"]), n=float(values.get("n", fixed_n or 0.0)), wall_db=float(values.get("walls", 0.0)),
                  door_db=float(values.get("doors", 0.0)), terms=tuple(terms))
    model.rmse_fit = float(np.sqrt(np.mean((x @ coef - y) ** 2)))
    return model


def errors(predicted, measured) -> dict:
    e = np.asarray(predicted, dtype=float) - np.asarray(measured, dtype=float)
    if e.size == 0:
        return {}
    return {"rmse_db": round(float(np.sqrt(np.mean(e ** 2))), 2), "mean_db": round(float(np.mean(e)), 2),
            "max_abs_db": round(float(np.max(np.abs(e))), 2), "points": int(e.size)}


def idw(train: list[dict], xy, key: str = "rssi", power: float = 2.0) -> float:
    """Inverse-distance interpolation of the measured values: the baseline that knows nothing about walls."""
    weights, total = 0.0, 0.0
    for r in train:
        d = math.dist(r["xy"], xy)
        if d < 1e-6:
            return r[key]
        w = 1 / d ** power
        weights += w
        total += w * r[key]
    return total / weights


def compare(plan: Plan, rows: list[dict], key: str = "rssi") -> dict:
    """The multi-wall model against two baselines, all scored on the held-out points only."""
    train = [r for r in rows if r["id"] not in plan.holdout and r.get(key) is not None]
    test = [r for r in rows if r["id"] in plan.holdout and r.get(key) is not None]
    out = {"train_points": len(train), "test_points": len(test)}
    if len(train) < 4:
        return out
    models = {"multi-wall": fit(train, key), "distance only": fit(train, key, walls=False),
              "free space (n = 2)": fit(train, key, walls=False, fixed_n=2.0)}
    for name, m in models.items():
        out[name] = {"a_dbm": round(m.a, 1), "n": round(m.n, 2), "wall_db": round(m.wall_db, 1),
                     "fit_rmse_db": round(m.rmse_fit, 2),
                     "holdout": errors([float(m.predict(r["distance_m"], r["walls"])) for r in test], [r[key] for r in test])}
    out["interpolation (IDW)"] = {"holdout": errors([idw(train, r["xy"], key) for r in test], [r[key] for r in test])}
    out["_model"] = models["multi-wall"]
    return out


# ---------------------------------------------------------------- maps

def predict_map(plan: Plan, model: Model, step: int = 3) -> np.ndarray:
    """Predicted signal for every floor pixel (computed every `step` pixels and filled in), NaN elsewhere."""
    h, w = plan.walls.shape
    out = np.full((h, w), np.nan)
    for y in range(0, h, step):
        for x in range(0, w, step):
            if plan.floor[y, x]:
                g = plan.geometry((x, y))
                out[y:y + step, x:x + step] = float(model.predict(g["distance_m"], g["walls"]))
    out[~plan.floor] = np.nan
    return out


def _font(size: int):
    for path in ["/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render(plan: Plan, values: np.ndarray, out_path: Path, title: str, measured: list[dict] | None = None,
           zones=PRIOR_ZONES, levels=LEVELS, key: str = "rssi", smooth_px: float = 5.0) -> Path:
    """The plan with use zones (translucent), contour lines with labels, the router and the measured points."""
    base = Image.open(plan.image).convert("RGB")
    layer = np.asarray(base).astype(float)
    if smooth_px:  # display only: the raster wall count gives jagged shadow edges; diffraction softens them anyway
        known = ~np.isnan(values)
        num = ndimage.gaussian_filter(np.where(known, values, 0.0), smooth_px)
        den = ndimage.gaussian_filter(known.astype(float), smooth_px)
        values = np.where(known, num / np.maximum(den, 1e-9), np.nan)
    if zones:
        for threshold, _, color in sorted(zones, key=lambda z: z[0]):
            area = np.nan_to_num(values, nan=-999) >= threshold
            layer[area] = 0.55 * layer[area] + 0.45 * np.array(color)
    img = Image.fromarray(layer.astype(np.uint8))
    draw = ImageDraw.Draw(img)
    small, bold = _font(12), _font(14)
    filled = np.nan_to_num(values, nan=-999)
    for level in levels:
        above = filled >= level
        edge = (above ^ np.roll(above, 1, 0)) | (above ^ np.roll(above, 1, 1))
        edge &= plan.floor & np.roll(plan.floor, 1, 0) & np.roll(plan.floor, 1, 1)
        edge = ndimage.binary_dilation(edge)
        ys, xs = np.nonzero(edge)
        for x, y in zip(xs, ys):
            img.putpixel((int(x), int(y)), (25, 25, 25))
        if len(xs):
            k = len(xs) // 2
            draw.text((int(xs[k]) + 3, int(ys[k]) - 14), f"{level} dBm", fill=(10, 10, 10), font=small)
    rx, ry = plan.router
    draw.ellipse([rx - 8, ry - 8, rx + 8, ry + 8], fill=(220, 30, 30), outline=(255, 255, 255), width=2)
    for r in measured or []:
        x, y = r["xy"]
        test = r["id"] in plan.holdout
        draw.rectangle([x - 4, y - 4, x + 4, y + 4], fill=(255, 255, 255) if test else (20, 20, 20))
        if r.get(key) is not None:
            draw.text((x + 6, y - 6), f"{r[key]:.0f}", fill=(0, 0, 160) if test else (0, 0, 0), font=small)
    draw.rectangle([0, 0, img.width, 24], fill=(255, 255, 255))
    draw.text((8, 4), title, fill=(0, 0, 0), font=bold)
    if zones:
        x = 8
        y = img.height - 22
        draw.rectangle([0, y - 4, img.width, img.height], fill=(255, 255, 255))
        for threshold, name, color in zones:
            draw.rectangle([x, y, x + 14, y + 14], fill=color)
            text = f"{name} (≥ {threshold:.0f})" if threshold > -199 else name
            draw.text((x + 18, y), text, fill=(0, 0, 0), font=small)
            x += 30 + int(draw.textlength(text, font=small))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path
