# USDA atlas lookup benchmark v1

Median of five warm-cache rounds across four fixed U.S. coordinates; exact nearest-county identity checked for all supported crops.

| Case | Crop | Brute ms/lookup | Indexed ms/lookup | Speedup |
|---|---|---:|---:|---:|
| supported crop | corn | 0.8291 | 0.0326 | **25.4x** |
| unsupported crop | tomato | 0.1101 | 0.0121 | **9.1x** |

Atlas records: 5,562. Results are machine-dependent; the correctness check is deterministic.
