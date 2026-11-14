"""Stand-in crop model server implementing ml/CONTRACT.md.

Replace predict() with the trained model. Standard library only:
    python3 ml/stub_server.py [--port 8765]
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = {"name": "stub-heuristic", "version": "0.1"}


def clamp01(value):
    return max(0.0, min(1.0, value))


def predict(request):
    """Return one prediction per site x crop. Swap this body for the trained model."""
    preferred = int(request.get("preferredMonth", 0)) % 12
    predictions = []
    for site in request.get("sites", []):
        climate = site.get("climate") or {}
        temps = climate.get("temperatureC") or []
        solar = climate.get("solarMjM2Day") or []
        rain = climate.get("precipitationMmDay") or []
        roof = site.get("roof") or {}
        for crop in request.get("crops", []):
            grow = int(crop["growMonths"])
            growable = [crop["tempMinC"] <= t <= crop["tempMaxC"] for t in temps] if len(temps) == 12 else []
            plant = None
            wait = None
            for offset in range(12):
                start = (preferred + offset) % 12
                if growable and all(growable[(start + i) % 12] for i in range(grow)):
                    plant, wait = start, offset
                    break
            season = 0.0 if plant is None else 0.7 + 0.3 * (1 - wait / 11)
            if roof.get("meanSunHours") is not None:
                sun = clamp01(roof["meanSunHours"] / crop["sunHours"])
            elif solar:
                sun = clamp01((sum(solar) / len(solar) - 12) / 10)
            else:
                sun = 0.5
            water = clamp01(sum(rain) / len(rain) / 3) if rain else 0.5
            obstacles = roof.get("obstructionCount") or 0
            suitability = clamp01(0.5 * season + 0.35 * sun + 0.15 * water - 0.01 * obstacles)
            predictions.append({
                "siteId": site["id"],
                "cropId": crop["id"],
                "suitability": round(suitability, 3),
                "plantMonth": plant,
                "harvestMonth": None if plant is None else (plant + grow - 1) % 12,
                "confidence": 0.4,
                "expectedYield": None,
                "notes": "Stub heuristic; replace with the trained model." if plant is not None else "No full growing season here.",
            })
    return {"model": MODEL, "predictions": predictions}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "model": MODEL})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/predict":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            request = json.loads(self.rfile.read(length) or b"{}")
            self._send(200, predict(request))
        except (ValueError, KeyError, TypeError) as error:
            self._send(400, {"error": f"bad request: {error}"})

    def log_message(self, fmt, *args):
        print("[crop-model]", fmt % args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    port = parser.parse_args().port
    print(f"Crop model stub on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
