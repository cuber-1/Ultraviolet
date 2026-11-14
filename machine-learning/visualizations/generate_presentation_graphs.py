"""Generate presentation-ready CropFit PNGs from a verified Houston model snapshot."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle


OUTPUT = Path(__file__).resolve().parent
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
CROPS = {
    "Leafy greens": {"fit": 82.9, "confidence": 0.51, "sun": 4, "temp": "7–24°C", "cycle": 2,
                     "curve": [80.3, 80.3, 82.9, 78.8, 62.1, 48.5, 45.5, 39.0, 69.3, 79.6, 77.9, 80.1]},
    "Tomatoes": {"fit": 85.1, "confidence": 0.58, "sun": 8, "temp": "16–30°C", "cycle": 3,
                 "curve": [54.4, 69.7, 85.1, 80.0, 69.9, 68.2, 70.7, 72.7, 82.2, 68.1, 55.7, 55.5]},
    "Peppers": {"fit": 78.4, "confidence": 0.41, "sun": 8, "temp": "18–31°C", "cycle": 3,
                "curve": [54.5, 74.7, 78.4, 75.6, 67.7, 65.6, 67.1, 69.5, 75.3, 66.3, 57.7, 58.9]},
    "Strawberries": {"fit": 82.8, "confidence": 0.62, "sun": 6, "temp": "10–26°C", "cycle": 3,
                     "curve": [82.8, 79.6, 65.5, 55.2, 63.9, 9.6, 0.0, 0.0, 53.5, 69.0, 80.4, 82.4]},
}

BG = "#0b120e"
PANEL = "#142019"
TEXT = "#edf7ef"
MUTED = "#94a699"
GRID = "#304238"
GREEN = "#61d689"
YELLOW = "#f2c94c"
BLUE = "#6bb7f0"
CORAL = "#ff8a70"


def setup():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "text.color": TEXT, "axes.labelcolor": MUTED,
        "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": GRID,
        "figure.facecolor": BG, "axes.facecolor": BG,
    })


def header(fig, eyebrow, title, subtitle):
    fig.text(0.06, 0.935, eyebrow, color=GREEN, fontsize=10, fontweight="bold")
    fig.text(0.06, 0.875, title, color=TEXT, fontsize=25, fontweight="bold")
    fig.text(0.06, 0.825, subtitle, color=MUTED, fontsize=11)
    fig.text(0.94, 0.925, "CROPFIT v0.2", color=MUTED, fontsize=9, ha="right")


def footer(fig):
    fig.text(0.06, 0.045, "FAO EcoCrop surrogate + NASA POWER climatology · screening evidence, not yield or purchase advice",
             color=MUTED, fontsize=8)
    fig.text(0.94, 0.045, "Houston · irrigated · soil pH 6.5", color=MUTED, fontsize=8, ha="right")


def growing_calendar():
    fig = plt.figure(figsize=(16, 9), dpi=160)
    header(fig, "PLANTING-WINDOW MODEL", "When does each crop fit?",
           "Monthly suitability exposes the useful window—and the months where a crop fails.")
    ax = fig.add_axes([0.12, 0.20, 0.76, 0.55])
    values = np.array([item["curve"] for item in CROPS.values()])
    cmap = LinearSegmentedColormap.from_list("cropfit", ["#19251d", "#28643d", GREEN])
    image = ax.imshow(values, cmap=cmap, vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(12), MONTHS, fontsize=10)
    ax.set_yticks(range(4), list(CROPS), fontsize=12)
    ax.tick_params(length=0, pad=12)
    for row, (name, item) in enumerate(CROPS.items()):
        best = int(np.argmax(item["curve"]))
        ax.add_patch(Rectangle((best - 0.48, row - 0.46), 0.96, 0.92, fill=False, edgecolor=TEXT, linewidth=2.2))
        for column, score in enumerate(item["curve"]):
            ax.text(column, row, f"{score:.0f}", ha="center", va="center",
                    color=BG if score >= 70 else TEXT, fontsize=9, fontweight="bold" if column == best else "normal")
        ax.text(11.75, row, f"   {item['sun']}H SUN · {item['temp']} · {item['cycle']} MO",
                va="center", color=MUTED, fontsize=9, clip_on=False)
    for x in np.arange(-0.5, 12, 1):
        ax.axvline(x, color=BG, linewidth=5)
    for y in np.arange(-0.5, 4, 1):
        ax.axhline(y, color=BG, linewidth=5)
    for spine in ax.spines.values():
        spine.set_visible(False)
    cax = fig.add_axes([0.36, 0.125, 0.28, 0.018])
    bar = fig.colorbar(image, cax=cax, orientation="horizontal")
    bar.set_ticks([0, 50, 100], labels=["0 · poor", "50 · marginal", "100 · strong"])
    bar.ax.tick_params(labelsize=8, length=0, colors=MUTED)
    bar.outline.set_visible(False)
    fig.text(0.12, 0.105, "Outlined cell = best planting month", color=TEXT, fontsize=9)
    footer(fig)
    fig.savefig(OUTPUT / "cropfit-growing-calendar.png", facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def tomato_fingerprint():
    fig = plt.figure(figsize=(16, 9), dpi=160)
    header(fig, "CROP REQUIREMENT FINGERPRINT", "Tomatoes on a Houston roof",
           "One visual connects the crop’s requirements, learned fit, and the evidence behind the score.")
    categories = ["Roof sun", "Temperature", "Water", "Soil pH", "Season"]
    values = [89, 73, 100, 100, 85]
    angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
    angles += angles[:1]
    radar_values = values + values[:1]
    ax = fig.add_axes([0.06, 0.13, 0.48, 0.65], polar=True)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1], categories, color=MUTED, fontsize=11)
    ax.set_yticks([25, 50, 75, 100], ["", "50", "75", "100"], color=MUTED, fontsize=8)
    ax.set_ylim(0, 100)
    ax.grid(color=GRID, linewidth=1)
    ax.spines["polar"].set_color(GRID)
    ax.plot(angles, radar_values, color=GREEN, linewidth=2.5)
    ax.fill(angles, radar_values, color=GREEN, alpha=0.24)
    ax.scatter(angles[:-1], values, s=55, color=GREEN, edgecolor=TEXT, linewidth=1, zorder=3)
    ax.text(0, 0, "85\nFIT", ha="center", va="center", color=TEXT, fontsize=23, fontweight="bold")
    detail = fig.add_axes([0.60, 0.16, 0.34, 0.58])
    detail.axis("off")
    detail.text(0, 0.97, "WHAT TOMATOES NEED", color=GREEN, fontsize=10, fontweight="bold")
    requirements = [("Daily sunlight", "8 hours", "Roof median: 7.1 h", 0.89),
                    ("Temperature", "16–30°C", "Best-window mean: 22.8°C", 0.73),
                    ("Crop cycle", "3 months", "Best start: March", 0.85)]
    y = 0.82
    for label, value, evidence, match in requirements:
        detail.text(0, y, label, color=MUTED, fontsize=10)
        detail.text(1, y, value, color=TEXT, fontsize=13, fontweight="bold", ha="right")
        detail.add_patch(Rectangle((0, y - 0.07), 1, 0.025, color=GRID, transform=detail.transAxes))
        detail.add_patch(Rectangle((0, y - 0.07), match, 0.025, color=GREEN, transform=detail.transAxes))
        detail.text(0, y - 0.12, evidence, color=MUTED, fontsize=9)
        y -= 0.24
    detail.text(0, 0.09, "MODEL READ", color=GREEN, fontsize=10, fontweight="bold")
    detail.text(0, 0.015, "Strong climate candidate. Reserve the brightest\nroof cells because sunlight is the practical constraint.",
                color=TEXT, fontsize=11, linespacing=1.5)
    footer(fig)
    fig.savefig(OUTPUT / "cropfit-tomato-fingerprint.png", facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def portfolio_map():
    fig = plt.figure(figsize=(16, 9), dpi=160)
    header(fig, "CROP PORTFOLIO", "Which crop gives the best roof trade-off?",
           "Model fit on the vertical axis; daily sunlight demand on the horizontal axis; bubble size is crop-cycle length.")
    ax = fig.add_axes([0.10, 0.22, 0.80, 0.54])
    colors = [GREEN, YELLOW, CORAL, BLUE]
    offsets = {"Leafy greens": (0.08, 0.45), "Tomatoes": (-0.55, 0.55), "Peppers": (-0.48, -1.1), "Strawberries": (0.12, 0.55)}
    for (name, item), color in zip(CROPS.items(), colors):
        size = 700 + item["cycle"] * 260
        ax.scatter(item["sun"], item["fit"], s=size, color=color, alpha=0.90, edgecolor=TEXT, linewidth=1.4, zorder=3)
        dx, dy = offsets[name]
        ax.text(item["sun"] + dx, item["fit"] + dy, name, color=TEXT, fontsize=11, fontweight="bold",
                ha="right" if dx < 0 else "left", va="bottom")
        ax.text(item["sun"] + dx, item["fit"] + dy - 0.12, f"{item['fit']:.0f} fit · {item['sun']}h sun",
                color=MUTED, fontsize=8, ha="right" if dx < 0 else "left", va="top")
    ax.axhline(80, color=GREEN, linewidth=1.2, linestyle="--", alpha=0.7)
    ax.axvline(7.1, color=YELLOW, linewidth=1.2, linestyle="--", alpha=0.7)
    ax.text(4.05, 80.25, "STRONG-FIT LINE", color=GREEN, fontsize=8, fontweight="bold")
    ax.text(7.06, 75.6, "ROOF MEDIAN\n7.1 HOURS", color=YELLOW, fontsize=8, fontweight="bold", ha="right")
    ax.fill_between([3.5, 7.1], 80, 88, color=GREEN, alpha=0.05)
    ax.text(3.65, 87.2, "DEPENDABLE ROOF CROPS", color=GREEN, fontsize=9, fontweight="bold")
    ax.set_xlim(3.5, 8.7)
    ax.set_ylim(74, 88)
    ax.set_xlabel("Required daily sunlight (hours)", fontsize=10, labelpad=12)
    ax.set_ylabel("Trained CropFit suitability (0–100)", fontsize=10, labelpad=12)
    ax.set_xticks([4, 5, 6, 7, 8])
    ax.set_yticks([75, 80, 85])
    ax.grid(color=GRID, linewidth=0.8, alpha=0.75)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(0.10, 0.125, "PORTFOLIO READ", color=GREEN, fontsize=9, fontweight="bold")
    fig.text(0.205, 0.125, "Use leafy greens as the dependable base crop; reserve the brightest cells for tomatoes.",
             color=TEXT, fontsize=10)
    footer(fig)
    fig.savefig(OUTPUT / "cropfit-portfolio-map.png", facecolor=BG, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    setup()
    growing_calendar()
    tomato_fingerprint()
    portfolio_map()
    print("Generated 3 CropFit presentation PNGs in", OUTPUT)
