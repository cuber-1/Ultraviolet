# CropFit presentation graphics

These PNGs use a verified CropFit v0.2 prediction snapshot for Houston with
irrigation enabled and soil pH 6.5:

- `cropfit-growing-calendar.png` — monthly suitability heatmap
- `cropfit-tomato-fingerprint.png` — tomato requirements and learned signals
- `cropfit-portfolio-map.png` — sunlight demand versus model suitability
- `cropfit-crop-classification-map.png` — temperature ranges, sunlight needs,
  crop classes, and cycle lengths
- `cropfit-model-derived-houston-classification.png` — trained location-fit
  classes with profile temperature ranges, ensemble disagreement, crop-cycle
  size, score, and planting month; every quantitative mark comes from CropFit
- `cropfit-learned-temperature-response.png` — city-independent response curves
  learned by the promoted model while non-temperature inputs stay optimal
- `cropfit-model-evaluation-diagnostics.png` — selected-model held-out scatter,
  residual distribution, metrics, and the rejected XGBoost candidate's loss and
  learning-rate curves

Regenerate them with the full ML environment:

```bash
PYTHONPATH=machine-learning machine-learning/.venv/bin/python \
  machine-learning/visualizations/generate_presentation_graphs.py
```

The figures are presentation assets for an agroclimatic screening model. They
are not parcel-specific yield or investment forecasts.
