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
from dataclasses import dataclass, field, fields, replace
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
    display_image: Path | None = None                        # another drawing to draw maps on (same pixel coordinates)
    _walls: np.ndarray | None = None
    _floor: np.ndarray | None = None

    @classmethod
    def load(cls, path: Path | str) -> "Plan":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["image"] = (path.parent / data["image"]).resolve()
        data["router"] = tuple(data["router"])
        if data.get("display_image"):
            data["display_image"] = (path.parent / data["display_image"]).resolve()
        # The plan file also holds settings for the walk script (throughput points, the point subset).
        known = {f.name for f in fields(cls) if not f.name.startswith("_")}
        return cls(**{k: v for k, v in data.items() if k in known})

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

    def for_router(self, xy, height_m: float | None = None) -> "Plan":
        """The same plan seen from another access point (the home has three); walls and floor are shared."""
        other = replace(self, router=tuple(xy), router_height_m=self.router_height_m if height_m is None else height_m)
        other._walls, other._floor = self._walls, self._floor
        return other


# ---------------------------------------------------------------- the path through open doors

class DoorPaths:
    """Shortest route from the router to each place through open space and open doors, never through a wall
    (Dijkstra on the floor grid, then pulled taut so it bends only at corners and door frames).

    Walk 2 showed why: where a concrete wall stands between them, a place reached through a door at twice the
    distance had a stronger signal than one right behind the wall; the signal travels along rooms and corridors
    and bends (diffraction, reflection) at door frames. Each bend costs signal; the total turn is measured in
    right angles (90 degrees = 1)."""

    def __init__(self, plan: "Plan", router, step: int = 2, clearance: int = 2):
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import dijkstra
        self.plan, self.step = plan, step
        free = plan.floor & ~ndimage.binary_dilation(plan.walls, iterations=clearance)
        self.free = free
        grid = free[::step, ::step]
        h, w = grid.shape
        index = -np.ones((h, w), dtype=np.int64)
        index[grid] = np.arange(int(grid.sum()))
        rows, cols, costs = [], [], []
        for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
            if dx >= 0:
                a, b = index[0:h - dy, 0:w - dx], index[dy:h, dx:w]
            else:
                a, b = index[0:h - dy, -dx:w], index[dy:h, 0:w + dx]
            ok = (a >= 0) & (b >= 0)
            rows.append(a[ok]); cols.append(b[ok]); costs.append(np.full(int(ok.sum()), math.hypot(dx, dy)))
        n = int(grid.sum())
        graph = coo_matrix((np.concatenate(costs), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)).tocsr()
        self.index, self.cells = index, np.argwhere(grid)          # cells: (row, col) of each node
        self.source = self._node(router)
        self.dist, self.pred = dijkstra(graph, directed=False, indices=self.source, return_predecessors=True)

    def _node(self, xy) -> int:
        """The reachable grid cell nearest to xy (a router stands against a wall, so its own pixel is not free)."""
        reach = getattr(self, "dist", None)
        ok = np.arange(len(self.cells)) if reach is None else np.flatnonzero(np.isfinite(reach))
        cells = self.cells[ok]
        k = int(np.argmin((cells[:, 1] * self.step - xy[0]) ** 2 + (cells[:, 0] * self.step - xy[1]) ** 2))
        return int(ok[k])

    def _visible(self, a, b) -> bool:
        n = max(1, int(math.dist(a, b)))
        xs = np.rint(np.linspace(a[0], b[0], n + 1)).astype(int)
        ys = np.rint(np.linspace(a[1], b[1], n + 1)).astype(int)
        return bool(self.free[ys, xs].all())

    def route(self, xy) -> dict:
        """Length (m, with the height difference), number of bends, total turn in right angles, the taut route."""
        node, chain = self._node(xy), []
        r0, c0 = self.cells[node]
        snapped = math.dist((c0 * self.step, r0 * self.step), xy) * self.plan.m_per_px   # > 0.5 m: no open way there
        while node >= 0:
            r, c = self.cells[node]
            chain.append((int(c) * self.step, int(r) * self.step))
            node = int(self.pred[node]) if node != self.source else -1
        chain.reverse()
        taut, i = [chain[0]], 0
        while i < len(chain) - 1:
            j = len(chain) - 1
            while j > i + 1 and not self._visible(chain[i], chain[j]):
                j -= 1
            taut.append(chain[j])
            i = j
        turns = []
        for a, b, c in zip(taut, taut[1:], taut[2:]):
            v1, v2 = np.subtract(b, a), np.subtract(c, b)
            cos = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
            angle = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
            if angle > 15:
                turns.append(angle)
        flat = sum(math.dist(a, b) for a, b in zip(taut, taut[1:])) * self.plan.m_per_px
        height = self.plan.device_height_m - self.plan.router_height_m
        return {"path_m": round(max(0.3, math.hypot(flat, height)), 2), "bends": len(turns),
                "turn": round(sum(turns) / 90, 2), "route": taut, "snapped_m": round(snapped, 2)}


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


def residual_idw(train: list[dict], model: Model, xy, key: str = "rssi") -> float:
    """Multi-wall prediction corrected by the interpolated residuals of the measured points (regression kriging
    with inverse-distance weights): the model carries the trend where nothing was measured, the residuals carry
    what the model does not know (which walls are concrete, furniture, the router's antenna pattern)."""
    residuals = [{"xy": r["xy"], "res": r[key] - float(model.predict(r["distance_m"], r["walls"]))} for r in train]
    return idw(residuals, xy, "res")


METHODS = ("multi-wall", "multi-wall + residuals", "interpolation (IDW)", "distance only", "free space (n = 2)")


def _predictor(method: str, train: list[dict], key: str):
    if method == "interpolation (IDW)":
        return lambda r: idw(train, r["xy"], key)
    if method == "distance only":
        m = fit(train, key, walls=False)
    elif method == "free space (n = 2)":
        m = fit(train, key, walls=False, fixed_n=2.0)
    else:
        m = fit(train, key)
    if method == "multi-wall + residuals":
        return lambda r: float(m.predict(r["distance_m"], r["walls"])) + residual_idw(train, m, r["xy"], key)
    return lambda r: float(m.predict(r["distance_m"], r["walls"]))


def loo_rmse(train: list[dict], method: str, key: str) -> float | None:
    """Leave-one-out error on the training points only: chooses a method without touching the held-out points."""
    errs = []
    for i, r in enumerate(train):
        rest = train[:i] + train[i + 1:]
        if len(rest) < 4:
            return None
        errs.append(_predictor(method, rest, key)(r) - r[key])
    return round(float(np.sqrt(np.mean(np.square(errs)))), 2) if errs else None


def compare(plan: Plan, rows: list[dict], key: str = "rssi") -> dict:
    """Every method fitted on the training points, chosen by leave-one-out error on them, scored on the held-out
    points (chosen before the walk) once."""
    train = [r for r in rows if r["id"] not in plan.holdout and r.get(key) is not None]
    test = [r for r in rows if r["id"] in plan.holdout and r.get(key) is not None]
    out = {"train_points": len(train), "test_points": len(test)}
    if len(train) < 5:
        return out
    for method in METHODS:
        predict = _predictor(method, train, key)
        entry = {"loo_rmse_db": loo_rmse(train, method, key),
                 "holdout": errors([predict(r) for r in test], [r[key] for r in test])}
        if method in ("multi-wall", "distance only", "free space (n = 2)"):
            m = fit(train, key, walls=method == "multi-wall", fixed_n=2.0 if method.startswith("free") else None)
            entry.update(a_dbm=round(m.a, 1), n=round(m.n, 2), wall_db=round(m.wall_db, 1), fit_rmse_db=round(m.rmse_fit, 2))
        out[method] = entry
    out["_model"] = fit(train, key)
    out["_train"] = train
    out["chosen"] = min((m for m in METHODS if out[m]["loo_rmse_db"] is not None), key=lambda m: out[m]["loo_rmse_db"])
    mw, h = out["multi-wall"]["holdout"], {m: out[m]["holdout"].get("rmse_db", 1e9) for m in METHODS}
    out["gate_multi_wall"] = bool(mw) and mw["rmse_db"] <= 5 and all(h["multi-wall"] < h[m] for m in METHODS if m not in ("multi-wall", "multi-wall + residuals"))
    return out


# ---------------------------------------------------------------- maps

def predict_map(plan: Plan, model: Model, step: int = 3, method: str = "multi-wall", train: list[dict] | None = None,
                key: str = "rssi") -> np.ndarray:
    """Predicted signal for every floor pixel (computed every `step` pixels and filled in), NaN elsewhere, by the
    multi-wall model, the model plus interpolated residuals, or interpolation alone."""
    h, w = plan.walls.shape
    out = np.full((h, w), np.nan)
    ys, xs = np.mgrid[0:h:step, 0:w:step]
    keep = plan.floor[ys, xs]
    ys, xs = ys[keep], xs[keep]
    if method != "interpolation (IDW)":
        model_values = np.array([float(model.predict(plan.distance_m((x, y)), walls_crossed(plan.walls, plan.router, (x, y))))
                                 for x, y in zip(xs, ys)])
    if method in ("interpolation (IDW)", "multi-wall + residuals") and train:
        pts = np.array([r["xy"] for r in train], dtype=float)
        vals = np.array([r[key] - (float(model.predict(r["distance_m"], r["walls"])) if method != "interpolation (IDW)" else 0.0)
                         for r in train])
        d = np.hypot(xs[:, None] - pts[None, :, 0], ys[:, None] - pts[None, :, 1])
        wgt = 1 / np.maximum(d, 1e-6) ** 2
        interp = (wgt * vals).sum(axis=1) / wgt.sum(axis=1)
        values = interp if method == "interpolation (IDW)" else model_values + interp
    else:
        values = model_values
    for x, y, v in zip(xs, ys, values):
        out[y:y + step, x:x + step] = v
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
    base = Image.open(plan.display_image or plan.image).convert("RGB")
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
    if zones:  # legend under the title, clear of the plan and its scale bar
        x, y = 8, 28
        draw.rectangle([0, 24, img.width, 46], fill=(255, 255, 255))
        for threshold, name, color in zones:
            draw.rectangle([x, y, x + 14, y + 14], fill=color)
            text = f"{name} (≥ {threshold:.0f})" if threshold > -199 else name
            draw.text((x + 18, y), text, fill=(0, 0, 0), font=small)
            x += 30 + int(draw.textlength(text, font=small))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path
