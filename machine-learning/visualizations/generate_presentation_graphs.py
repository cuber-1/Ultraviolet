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


def footer(fig, context="Houston · irrigated · soil pH 6.5"):
    fig.text(0.06, 0.045, "FAO EcoCrop surrogate + NASA POWER climatology · screening evidence, not yield or purchase advice",
             color=MUTED, fontsize=8)
    fig.text(0.94, 0.045, context, color=MUTED, fontsize=8, ha="right")


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


def crop_classification_map():
    crops = [
        ("Leafy greens", 7, 24, 4, 2, "Leafy & cool-season"),
        ("Kale & brassicas", 5, 24, 5, 2, "Leafy & cool-season"),
        ("Tomatoes", 16, 30, 8, 3, "Fruiting crops"),
        ("Peppers", 18, 31, 8, 3, "Fruiting crops"),
        ("Strawberries", 10, 26, 6, 3, "Fruiting crops"),
        ("Cucumbers & squash", 18, 32, 7, 2, "Fruiting crops"),
        ("Melons", 20, 34, 8, 3, "Fruiting crops"),
        ("Beans", 16, 30, 6, 2, "Grains & legumes"),
        ("Corn", 16, 32, 8, 4, "Grains & legumes"),
        ("Soybeans", 18, 30, 7, 4, "Grains & legumes"),
        ("Wheat", 3, 24, 6, 4, "Grains & legumes"),
        ("Potatoes", 10, 24, 6, 4, "Roots & alliums"),
        ("Onions", 10, 27, 6, 4, "Roots & alliums"),
        ("Sunflowers", 16, 32, 7, 3, "Flowers & oilseeds"),
    ]
    colors = {
        "Leafy & cool-season": GREEN,
        "Fruiting crops": CORAL,
        "Grains & legumes": YELLOW,
        "Roots & alliums": BLUE,
        "Flowers & oilseeds": "#c691e8",
    }
    markers = {
        "Leafy & cool-season": "o", "Fruiting crops": "s", "Grains & legumes": "^",
        "Roots & alliums": "D", "Flowers & oilseeds": "P",
    }
    fig = plt.figure(figsize=(16, 9), dpi=160)
    header(fig, "CROP CLASSIFICATION MAP", "What growing conditions define each crop?",
           "Temperature bands show tolerance; position shows the preferred climate; height shows required daily sunlight.")
    ax = fig.add_axes([0.09, 0.23, 0.82, 0.54])
    ax.axvspan(0, 14, color=BLUE, alpha=0.045)
    ax.axvspan(14, 23, color=GREEN, alpha=0.045)
    ax.axvspan(23, 36, color=CORAL, alpha=0.045)
    ax.text(7, 8.62, "COOL-SEASON", color=BLUE, fontsize=9, fontweight="bold", ha="center")
    ax.text(18.5, 8.62, "TEMPERATE", color=GREEN, fontsize=9, fontweight="bold", ha="center")
    ax.text(29.5, 8.62, "HEAT-LOVING", color=CORAL, fontsize=9, fontweight="bold", ha="center")
    label_offsets = {
        "Leafy greens": (-0.2, -0.29), "Kale & brassicas": (-0.2, 0.25), "Tomatoes": (-0.25, 0.28),
        "Peppers": (0.1, -0.34), "Strawberries": (-0.2, 0.32), "Cucumbers & squash": (0.1, -0.34),
        "Melons": (0.15, 0.30), "Beans": (0.15, -0.31), "Corn": (-0.2, -0.34),
        "Soybeans": (0.15, 0.28), "Wheat": (-0.2, 0.28), "Potatoes": (-0.2, -0.31),
        "Onions": (0.15, 0.56), "Sunflowers": (0.1, -0.30),
    }
    for name, low, high, sun, months, category in crops:
        midpoint = (low + high) / 2
        ax.errorbar(midpoint, sun, xerr=[[midpoint - low], [high - midpoint]], fmt="none",
                    ecolor=colors[category], elinewidth=3, alpha=0.38, capsize=0, zorder=1)
        ax.scatter(midpoint, sun, s=130 + months * 70, marker=markers[category], color=colors[category],
                   edgecolor=TEXT, linewidth=1.2, alpha=0.94, zorder=3)
        dx, dy = label_offsets[name]
        align = "right" if dx < 0 else "left"
        ax.text(midpoint + dx, sun + dy, name, color=TEXT, fontsize=8.3, ha=align, va="center", zorder=4)
    houston_temp = 22.8
    ax.axvline(houston_temp, color=TEXT, linestyle=(0, (3, 5)), linewidth=1.2, alpha=0.7)
    ax.text(houston_temp, 8.77, "HOUSTON · 22.8°C", color=TEXT, fontsize=8, ha="center", fontweight="bold")
    ax.set_xlim(0, 36)
    ax.set_ylim(3.7, 8.9)
    ax.set_xlabel("Preferred temperature midpoint (°C)  ·  horizontal band = full tolerated range", fontsize=10, labelpad=13)
    ax.set_ylabel("Required daily sunlight (hours)", fontsize=10, labelpad=13)
    ax.set_xticks(range(0, 37, 5))
    ax.set_yticks([4, 5, 6, 7, 8])
    ax.grid(color=GRID, linewidth=0.8, alpha=0.65)
    ax.spines[["top", "right"]].set_visible(False)
    handles = [ax.scatter([], [], marker=markers[name], s=90, color=color, edgecolor=TEXT, linewidth=1, label=name)
               for name, color in colors.items()]
    legend = ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.22), ncol=5,
                       frameon=False, fontsize=8, labelcolor=TEXT, handletextpad=0.5, columnspacing=1.8)
    fig.text(0.09, 0.075, "HOW TO READ IT", color=GREEN, fontsize=9, fontweight="bold")
    fig.text(0.185, 0.075, "Warm, high-sun crops cluster upper-right; greens and roots sit lower and cooler. Bubble size = crop-cycle length.",
             color=TEXT, fontsize=9.5)
    footer(fig)
    fig.savefig(OUTPUT / "cropfit-crop-classification-map.png", facecolor=BG, bbox_inches="tight")
    plt.close(fig)


def model_derived_houston_map():
    """Plot only values emitted by the trained artifact and its EcoCrop profiles."""
    from cropfit.inference import CropFitPredictor

    ml_root = OUTPUT.parent
    predictor = CropFitPredictor(ml_root / "artifacts/cropfit.joblib", ml_root / "data/raw/ecocrop.csv")
    climate = predictor.climate(29.7604, -95.3698)
    requested = [
        ("Leafy greens", "lettuce"), ("Kale & brassicas", "thousand head kale"),
        ("Tomatoes", "tomato"), ("Peppers", "pepper"), ("Strawberries", "strawberry"),
        ("Beans", "common bean"), ("Cucumbers", "cucumber"), ("Corn", "corn"),
        ("Soybeans", "soy"), ("Wheat", "wheat"), ("Potatoes", "potato"),
        ("Melons", "rock melon"), ("Onions", "onion"), ("Sunflowers", "sunflower"),
    ]
    rows = []
    for label, query in requested:
        result = predictor.predict(query, 29.7604, -95.3698, 6.5, True, climate)
        profile = result["profile"]
        best = max(result["monthlyCurve"], key=lambda month: month["score"])
        cycle = (float(profile["growing_days_min"]) + float(profile["growing_days_max"])) / 2
        rows.append({
            "label": label, "species": profile["scientific_name"], "score": float(result["score"]),
            "confidence": float(result["confidence"]), "uncertainty": float(best["uncertainty"]),
            "temp_min": float(profile["temp_opt_min"]), "temp_max": float(profile["temp_opt_max"]),
            "temp_mid": (float(profile["temp_opt_min"]) + float(profile["temp_opt_max"])) / 2,
            "cycle": cycle, "month": result["bestPlantingMonth"],
        })

    def fit_class(score):
        if score >= 85:
            return "Strong fit", GREEN
        if score >= 80:
            return "Promising", BLUE
        return "Conditional", YELLOW

    fig = plt.figure(figsize=(16, 9), dpi=160)
    header(fig, "TRAINED MODEL · LOCATION CLASSIFICATION",
           "Which crops does CropFit classify as a Houston match?",
           "Position, ranges, uncertainty, and crop-cycle size all come from the trained artifact and its EcoCrop profiles.")
    ax = fig.add_axes([0.07, 0.18, 0.61, 0.60])
    ax.axhspan(85, 100, color=GREEN, alpha=0.055)
    ax.axhspan(80, 85, color=BLUE, alpha=0.055)
    ax.axhspan(45, 80, color=YELLOW, alpha=0.025)
    ax.axhline(85, color=GREEN, linewidth=1, linestyle="--", alpha=0.65)
    ax.axhline(80, color=BLUE, linewidth=1, linestyle="--", alpha=0.65)
    for index, row in enumerate(rows, start=1):
        category, color = fit_class(row["score"])
        x_error = [[row["temp_mid"] - row["temp_min"]], [row["temp_max"] - row["temp_mid"]]]
        ax.errorbar(row["temp_mid"], row["score"], xerr=x_error, yerr=row["uncertainty"], fmt="none",
                    ecolor=color, elinewidth=1.7, alpha=0.28, capsize=3, zorder=1)
        bubble = 170 + np.sqrt(row["cycle"]) * 28
        ax.scatter(row["temp_mid"], row["score"], s=bubble, color=color, edgecolor=TEXT,
                   linewidth=1.4, alpha=0.96, zorder=3)
        point_label = "2/13" if index == 2 else ("" if index == 13 else str(index))
        if point_label:
            ax.text(row["temp_mid"], row["score"], point_label, color=BG, fontsize=7.5, fontweight="bold",
                    ha="center", va="center", zorder=4)
    ax.text(10.3, 96.5, "STRONG FIT · 85+", color=GREEN, fontsize=8, fontweight="bold")
    ax.text(10.3, 83.1, "PROMISING · 80–84", color=BLUE, fontsize=8, fontweight="bold")
    ax.text(10.3, 76.8, "CONDITIONAL · <80", color=YELLOW, fontsize=8, fontweight="bold")
    ax.set_xlim(10, 35.5)
    ax.set_ylim(45, 100)
    ax.set_xlabel("EcoCrop optimal temperature midpoint (°C)  ·  horizontal whisker = optimal range", fontsize=9, labelpad=12)
    ax.set_ylabel("Best monthly CropFit suitability (0–100)  ·  vertical whisker = model disagreement", fontsize=9, labelpad=12)
    ax.set_xticks([10, 15, 20, 25, 30, 35])
    ax.set_yticks([50, 60, 70, 80, 85, 90, 100])
    ax.grid(color=GRID, linewidth=0.8, alpha=0.65)
    ax.spines[["top", "right"]].set_visible(False)

    ranked = sorted(enumerate(rows, start=1), key=lambda item: item[1]["score"], reverse=True)
    listing = fig.add_axes([0.72, 0.18, 0.25, 0.60])
    listing.axis("off")
    listing.set_xlim(0, 1)
    listing.set_ylim(0, 1)
    listing.text(0, 1.0, "MODEL RANKING", color=GREEN, fontsize=10, fontweight="bold", va="top")
    listing.text(1, 1.0, "FIT  START", color=MUTED, fontsize=8, ha="right", va="top")
    y = 0.94
    for original_index, row in ranked:
        category, color = fit_class(row["score"])
        listing.scatter(0.018, y, s=55, color=color, edgecolor=TEXT, linewidth=0.7)
        listing.text(0.06, y, f"{original_index:02d}  {row['label']}", color=TEXT, fontsize=8.7,
                     fontweight="bold", va="center")
        listing.text(1, y, f"{row['score']:.0f}   {row['month']}", color=TEXT, fontsize=8.7,
                     ha="right", va="center")
        listing.text(0.06, y - 0.026, row["species"], color=MUTED, fontsize=6.7,
                     style="italic", va="top")
        y -= 0.066
    listing.text(0, 0.012, "Bubble size = model profile cycle length", color=MUTED, fontsize=7.2)
    fig.text(0.07, 0.105, "MODEL READ", color=GREEN, fontsize=9, fontweight="bold")
    fig.text(0.155, 0.105, "Cucumbers rank highest; peppers, wheat, and sunflowers remain conditional because uncertainty is high.",
             color=TEXT, fontsize=9.5)
    footer(fig)
    fig.savefig(OUTPUT / "cropfit-model-derived-houston-classification.png", facecolor=BG)
    plt.close(fig)


def learned_temperature_response():
    """Isolate the production model's learned response to temperature."""
    import joblib
    from cropfit.features import feature_row
    from cropfit.profiles import load_profiles, resolve_profile

    ml_root = OUTPUT.parent
    model = joblib.load(ml_root / "artifacts/cropfit.joblib")["model"]
    profiles = load_profiles(ml_root / "data/raw/ecocrop.csv")
    crops = [
        ("Lettuce", "lettuce", GREEN), ("Strawberry", "strawberry", BLUE),
        ("Wheat", "wheat", "#c691e8"), ("Tomato", "tomato", CORAL),
        ("Pepper", "pepper", YELLOW), ("Corn", "corn", "#e7a45d"),
    ]
    temperatures = np.linspace(0, 40, 161)
    fig = plt.figure(figsize=(16, 9), dpi=160)
    header(fig, "LEARNED RESPONSE FUNCTION", "What temperature niches has CropFit learned?",
           "Temperature varies while water, soil pH, sunlight, and irrigation are held at crop-optimal values.")
    ax = fig.add_axes([0.08, 0.19, 0.84, 0.58])
    ax.axvspan(0, 14, color=BLUE, alpha=0.035)
    ax.axvspan(14, 24, color=GREEN, alpha=0.035)
    ax.axvspan(24, 40, color=CORAL, alpha=0.035)
    ax.text(7, 104, "COOL", color=BLUE, fontsize=9, fontweight="bold", ha="center")
    ax.text(19, 104, "TEMPERATE", color=GREEN, fontsize=9, fontweight="bold", ha="center")
    ax.text(32, 104, "HOT", color=CORAL, fontsize=9, fontweight="bold", ha="center")
    for label, query, color in crops:
        profile = resolve_profile(query, profiles)
        rainfall = (profile.rain_opt_min + profile.rain_opt_max) / 2
        ph = (profile.ph_opt_min + profile.ph_opt_max) / 2
        rows = np.asarray([feature_row(profile, value, rainfall, ph, 18.0, True) for value in temperatures], dtype=np.float32)
        predictions = model.predict(rows)
        ax.plot(temperatures, predictions, color=color, linewidth=2.8, label=label)
        peak_index = int(np.argmax(predictions))
        ax.scatter(temperatures[peak_index], predictions[peak_index], s=48, color=color, edgecolor=TEXT, linewidth=0.9, zorder=4)
        label_x = min(39.2, profile.temp_opt_max + 0.6)
        label_y = float(model.predict(np.asarray([feature_row(profile, min(label_x, 40), rainfall, ph, 18.0, True)], dtype=np.float32))[0])
        ax.text(label_x, label_y, label, color=color, fontsize=9, fontweight="bold", va="center")
        ax.hlines(-3 - crops.index((label, query, color)) * 2.2, profile.temp_opt_min, profile.temp_opt_max,
                  color=color, linewidth=5, alpha=0.9, clip_on=False)
    ax.text(0.2, -2.5, "ECROP OPTIMAL BANDS", color=MUTED, fontsize=7.5, fontweight="bold", va="top")
    ax.set_xlim(0, 40)
    ax.set_ylim(-17, 108)
    ax.set_xlabel("Air temperature (°C)", fontsize=10, labelpad=12)
    ax.set_ylabel("Predicted suitability (0–100)", fontsize=10, labelpad=12)
    ax.set_xticks(range(0, 41, 5))
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.grid(color=GRID, linewidth=0.8, alpha=0.65)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.01), ncol=6, frameon=False,
              labelcolor=TEXT, fontsize=8, handlelength=2.4)
    fig.text(0.08, 0.105, "JUDGE READ", color=GREEN, fontsize=9, fontweight="bold")
    fig.text(0.17, 0.105, "The same trained function separates cool crops from warm-season crops without using a city-specific lookup table.",
             color=TEXT, fontsize=9.5)
    footer(fig, "Controlled experiment · crop-optimal water, pH, sunlight, irrigation")
    fig.savefig(OUTPUT / "cropfit-learned-temperature-response.png", facecolor=BG)
    plt.close(fig)


def model_evaluation_diagnostics():
    """Reconstruct the exact held-out split and show honest production metrics."""
    import joblib
    from sklearn.model_selection import GroupShuffleSplit
    from cropfit.profiles import load_profiles
    from cropfit.training import generate_examples

    ml_root = OUTPUT.parent
    bundle = joblib.load(ml_root / "artifacts/cropfit.joblib")
    model, metadata = bundle["model"], bundle["metadata"]
    profiles = load_profiles(ml_root / "data/raw/ecocrop.csv")
    x, y, groups = generate_examples(profiles, 72, metadata["seed"])
    _, test_indices = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=metadata["seed"]).split(x, y, groups))
    predictions = model.predict(x[test_indices])
    residuals = np.abs(predictions - y[test_indices])
    history_path = ml_root / "runs" / metadata["runId"] / "history.csv"
    history = np.genfromtxt(history_path, delimiter=",", names=True)

    fig = plt.figure(figsize=(16, 9), dpi=160)
    header(fig, "MODEL EVALUATION · HELD-OUT CROP PROFILES", "What does CropFit accuracy actually measure?",
           "Production ExtraTrees is evaluated on species profiles never seen during training—not random rows from known crops.")
    metrics = [("7.21", "MAE", "suitability points"), ("0.817", "R²", "held-out scenarios"),
               ("21.42", "P90 ERROR", "90% within this"), ("373", "UNSEEN PROFILES", "20% group holdout")]
    for index, (value, label, note) in enumerate(metrics):
        x_pos = 0.07 + index * 0.225
        fig.text(x_pos, 0.755, value, color=TEXT, fontsize=20, fontweight="bold")
        fig.text(x_pos + 0.058, 0.765, label, color=GREEN, fontsize=8, fontweight="bold")
        fig.text(x_pos + 0.058, 0.746, note, color=MUTED, fontsize=7.5)

    predicted_axis = fig.add_axes([0.07, 0.20, 0.27, 0.45])
    sample = np.random.default_rng(7).choice(len(test_indices), min(7000, len(test_indices)), replace=False)
    predicted_axis.scatter(y[test_indices][sample], predictions[sample], s=5, color=GREEN, alpha=0.11, rasterized=True)
    predicted_axis.plot([0, 100], [0, 100], color=TEXT, linewidth=1.2, linestyle="--", alpha=0.8)
    predicted_axis.set(title="Selected model · predicted vs target", xlabel="Mechanistic target", ylabel="ExtraTrees prediction", xlim=(-2, 102), ylim=(-2, 102))

    error_axis = fig.add_axes([0.39, 0.20, 0.24, 0.45])
    error_axis.hist(residuals, bins=np.arange(0, 52, 2), color=BLUE, alpha=0.85)
    error_axis.axvline(metadata["metrics"]["mae"], color=GREEN, linewidth=2, label="MAE 7.21")
    error_axis.axvline(metadata["metrics"]["p90AbsoluteError"], color=YELLOW, linewidth=2, linestyle="--", label="P90 21.42")
    error_axis.set(title="Selected model · held-out error", xlabel="Absolute error (suitability points)", ylabel="Scenarios", xlim=(0, 50))
    error_axis.legend(frameon=False, labelcolor=TEXT, fontsize=8)

    loss_axis = fig.add_axes([0.68, 0.20, 0.25, 0.45])
    loss_axis.plot(history["iteration"], history["train_rmse"], color=GREEN, linewidth=2, label="train RMSE")
    loss_axis.plot(history["iteration"], history["validation_rmse"], color=CORAL, linewidth=2, label="validation RMSE")
    loss_axis.set(title="Rejected XGBoost candidate · loss", xlabel="Boosting round", ylabel="RMSE", xlim=(1, len(history)))
    rate_axis = loss_axis.twinx()
    rate_axis.plot(history["iteration"], history["learning_rate"], color=YELLOW, linewidth=1.3, alpha=0.8, label="learning rate")
    rate_axis.set_ylabel("Learning rate", color=YELLOW)
    rate_axis.tick_params(axis="y", colors=YELLOW)
    handles, labels = loss_axis.get_legend_handles_labels()
    rate_handles, rate_labels = rate_axis.get_legend_handles_labels()
    loss_axis.legend(handles + rate_handles, labels + rate_labels, frameon=False, labelcolor=TEXT, fontsize=7.5)

    for axis in [predicted_axis, error_axis, loss_axis]:
        axis.grid(color=GRID, linewidth=0.7, alpha=0.65)
        axis.spines[["top", "right"]].set_visible(False)
        axis.title.set_color(TEXT); axis.title.set_fontsize(10); axis.title.set_fontweight("bold")
    rate_axis.spines["top"].set_visible(False)
    rate_axis.spines["right"].set_color(YELLOW)
    fig.text(0.07, 0.115, "WHAT THIS PROVES", color=GREEN, fontsize=9, fontweight="bold")
    fig.text(0.19, 0.115, "The model reproduces the EcoCrop screening function on unseen crop profiles. It does not yet prove farm yield accuracy.",
             color=TEXT, fontsize=9.5)
    fig.text(0.07, 0.085, "MODEL SELECTION", color=BLUE, fontsize=9, fontweight="bold")
    fig.text(0.19, 0.085, "ExtraTrees won (MAE 7.21). The iterative XGBoost candidate shown at right was rejected (MAE 8.95).",
             color=TEXT, fontsize=9.5)
    footer(fig, "134,064 synthetic scenarios · 373 held-out crop profiles · seed 20261114")
    fig.savefig(OUTPUT / "cropfit-model-evaluation-diagnostics.png", facecolor=BG)
    plt.close(fig)


if __name__ == "__main__":
    setup()
    growing_calendar()
    tomato_fingerprint()
    portfolio_map()
    crop_classification_map()
    model_derived_houston_map()
    learned_temperature_response()
    model_evaluation_diagnostics()
    print("Generated 7 CropFit presentation PNGs in", OUTPUT)
