# CropFit reliability inference benchmark v5

Median of 100 warm runs over one baseline plus ten historical climate scenarios on the same host; each model must produce exact nested equality between its scenario loop and batched path.

| Model | Artifact | Scenario loop | Batched | Internal speedup |
|---|---:|---:|---:|---:|
| v0.12.1 production | 1.9 KB | 1.734 ms | 1.633 ms | 1.06x |
| v0.11 champion | 64.3 MB | 9.975 ms | 2.599 ms | 3.84x |

Production batched inference is **1.59x faster** (37.2% lower latency), with a **99.9970%** smaller artifact.

Gate: **PASS**. Warm local CPU timing is machine-dependent; exact output equality, artifact hashes, and byte sizes are deterministic.
