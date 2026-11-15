"""Generate the synthetic chart and table set with known values (Stage 6 development).

Every chart is drawn from data written in this file, so a value read from a chart can be compared
with the true value. The same pages are written twice:
    evals/charts/files/charts_vector.pdf   vector pages: labels and numbers are in the text layer
    evals/charts/files/charts_raster.pdf   the same pages as images only: no text layer at all
and each chart is also saved as a PNG. The true values go to evals/charts/answers.toml. Both PDFs are
copied to evals/documents/files/ as synthetic_charts_vector.pdf and synthetic_charts_raster.pdf, so the
document test runner can ask questions about them (evals/documents/tables.toml).

Usage:
    python scripts/make_chart_set.py
"""

from __future__ import annotations

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evals" / "charts" / "files"
ANSWERS = ROOT / "evals" / "charts" / "answers.toml"

for name in ("Noto Sans CJK KR", "NanumGothic", "AppleGothic", "Malgun Gothic"):
    if any(f.name == name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = name
        break
plt.rcParams["axes.unicode_minus"] = False

QUARTERS = ["Q1 '25", "Q2 '25", "Q3 '25", "Q4 '25", "Q1 '26", "Q2 '26"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CHARTS: list[dict] = [
    {"id": "C01", "kind": "bar, values labelled", "title": "Northwind revenue by quarter (USD million)",
     "x": QUARTERS, "y": [412.0, 438.5, 401.2, 476.9, 455.3, 503.8]},
    {"id": "C02", "kind": "bar, no value labels", "title": "Northwind operating income by quarter (USD million)",
     "x": QUARTERS, "y": [62.0, 71.0, 48.0, 88.0, 79.0, 95.0]},
    {"id": "C03", "kind": "line, no value labels", "title": "Units shipped per month, 2025 (thousand units)",
     "x": MONTHS, "y": [120, 135, 128, 150, 162, 158, 171, 180, 176, 195, 210, 232]},
    {"id": "C04", "kind": "grouped bar, values labelled", "title": "Revenue by region (USD million)",
     "x": ["Americas", "Europe", "Asia", "Other"], "series": {"2024": [820, 540, 610, 95], "2025": [905, 515, 702, 110]}},
    {"id": "C05", "kind": "stacked bar, totals labelled only", "title": "Revenue by segment (USD million)",
     "x": ["2022", "2023", "2024", "2025"],
     "series": {"Devices": [900, 950, 1010, 1060], "Cloud": [300, 420, 560, 720], "Licensing": [150, 140, 125, 110]}},
    {"id": "C06", "kind": "pie, percentages labelled", "title": "2025 revenue mix",
     "labels": ["Devices", "Cloud", "Licensing", "Services"], "y": [45.5, 30.9, 4.7, 18.9]},
    {"id": "C07", "kind": "bars on the left axis, line on the right axis", "title": "Revenue (bars, USD million) and operating margin (line, %)",
     "x": ["2021", "2022", "2023", "2024", "2025"], "y": [1210, 1350, 1510, 1695, 1890], "y2": [8.5, 10.2, 9.1, 12.4, 14.0]},
    {"id": "C08", "kind": "bar with negative values, Korean, values labelled", "title": "사업부별 영업이익 (단위: 조원)",
     "x": ["반도체", "모바일", "디스플레이", "가전", "전장"], "y": [24.9, 12.9, 4.1, -0.6, 1.5]},
]

# Tables drawn as images. T02 has one wrong subtotal on purpose (gross profit 2025 should be 1,260).
TABLES: list[dict] = [
    {"id": "T01", "title": "Northwind Inc. — Statement of operations (USD million)",
     "columns": ["", "2024", "2025"],
     "rows": [["Revenue", "1,695", "1,890"], ["Cost of revenue", "(1,120)", "(1,230)"], ["Gross profit", "575", "660"],
              ["Operating expenses", "(365)", "(395)"], ["Operating income", "210", "265"], ["Interest expense", "(18)", "(15)"],
              ["Income before taxes", "192", "250"], ["Income taxes", "(38)", "(52)"], ["Net income", "154", "198"]]},
    {"id": "T02", "title": "Contoso Ltd. — Statement of operations (USD million)",
     "columns": ["", "2024", "2025"],
     "rows": [["Revenue", "2,040", "2,310"], ["Cost of revenue", "(930)", "(1,050)"], ["Gross profit", "1,110", "1,360"],
              ["Operating expenses", "(780)", "(850)"], ["Operating income", "330", "410"]],
     "error": "Gross profit 2025 is printed as 1,360, but 2,310 − 1,050 = 1,260; operating income 410 matches 1,260 − 850."},
]


def draw_chart(c: dict):
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=100)
    kind = c["id"]
    if kind in ("C01", "C02", "C08"):
        colors = ["#2f5597" if v >= 0 else "#c0504d" for v in c["y"]]
        bars = ax.bar(c["x"], c["y"], color=colors)
        if kind != "C02":
            ax.bar_label(bars, labels=[f"{v:,.1f}" for v in c["y"]], padding=3)
        if kind == "C02":
            ax.set_yticks(range(0, 101, 20))
            ax.grid(axis="y", alpha=0.4)
        if kind == "C08":
            ax.axhline(0, color="black", linewidth=0.8)
    elif kind == "C03":
        ax.plot(c["x"], c["y"], marker="o")
        ax.set_ylim(100, 250)
        ax.set_yticks(range(100, 251, 25))
        ax.grid(alpha=0.4)
    elif kind == "C04":
        xs = range(len(c["x"]))
        for i, (year, values) in enumerate(c["series"].items()):
            bars = ax.bar([x + (i - 0.5) * 0.38 for x in xs], values, width=0.38, label=year)
            ax.bar_label(bars, padding=2, fontsize=8)
        ax.set_xticks(list(xs), c["x"])
        ax.legend()
    elif kind == "C05":
        bottom = [0] * len(c["x"])
        for name, values in c["series"].items():
            ax.bar(c["x"], values, bottom=bottom, label=name)
            bottom = [b + v for b, v in zip(bottom, values)]
        for x, total in zip(c["x"], bottom):
            ax.annotate(f"{total:,}", (x, total), ha="center", va="bottom", xytext=(0, 3), textcoords="offset points")
        ax.legend(loc="upper left")
        ax.set_ylim(0, 2200)
    elif kind == "C06":
        ax.pie(c["y"], labels=c["labels"], autopct="%1.1f%%", startangle=90, counterclock=False)
        ax.axis("equal")
    elif kind == "C07":
        ax.bar(c["x"], c["y"], color="#9dc3e6")
        ax.set_ylim(0, 2000)
        ax.set_ylabel("Revenue (USD million)")
        ax2 = ax.twinx()
        ax2.plot(c["x"], c["y2"], color="#c00000", marker="o")
        for x, v in zip(c["x"], c["y2"]):
            ax2.annotate(f"{v:.1f}%", (x, v), ha="center", va="bottom", xytext=(0, 5), textcoords="offset points")
        ax2.set_ylim(0, 20)
        ax2.set_ylabel("Operating margin (%)")
    ax.set_title(c["title"])
    fig.tight_layout()
    return fig


def draw_table(t: dict):
    fig, ax = plt.subplots(figsize=(8, 0.45 * (len(t["rows"]) + 2)), dpi=100)
    ax.axis("off")
    table = ax.table(cellText=t["rows"], colLabels=t["columns"], loc="center", cellLoc="right", colLoc="right")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.3)
    for (r, col), cell in table.get_celld().items():
        if col == 0:
            cell.set_text_props(ha="left")
        cell.set_edgecolor("#bbbbbb")
    ax.set_title(t["title"])
    fig.tight_layout()
    return fig


def toml_value(v) -> str:
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, dict):
        return "{ " + ", ".join(f'"{k}" = {toml_value(x)}' for k, x in v.items()) + " }"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    return repr(v)


def main() -> None:
    from PIL import Image

    OUT.mkdir(parents=True, exist_ok=True)
    figures = [(c["id"], draw_chart(c)) for c in CHARTS] + [(t["id"], draw_table(t)) for t in TABLES]
    images = []
    with PdfPages(OUT / "charts_vector.pdf") as pdf:
        for ident, fig in figures:
            pdf.savefig(fig)
            buffer = io.BytesIO()
            fig.savefig(buffer, format="png", dpi=150)
            fig.savefig(OUT / f"{ident}.png", dpi=150)
            images.append(Image.open(io.BytesIO(buffer.getvalue())).convert("RGB"))
            plt.close(fig)
    images[0].save(OUT / "charts_raster.pdf", save_all=True, append_images=images[1:], resolution=150)
    documents = ROOT / "evals" / "documents" / "files"
    documents.mkdir(parents=True, exist_ok=True)
    for kind in ("vector", "raster"):
        (documents / f"synthetic_charts_{kind}.pdf").write_bytes((OUT / f"charts_{kind}.pdf").read_bytes())

    lines = ["# True values of the synthetic chart and table set, written by scripts/make_chart_set.py.",
             "# Page n of charts_vector.pdf and charts_raster.pdf is item n below (C01-C08, then T01-T02).", ""]
    for page, item in enumerate(CHARTS + TABLES, 1):
        lines.append("[[item]]")
        lines.append(f"page = {page}")
        for key, value in item.items():
            lines.append(f"{key} = {toml_value(value)}")
        lines.append("")
    ANSWERS.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(figures)} pages -> {OUT.relative_to(ROOT)}; answers -> {ANSWERS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
