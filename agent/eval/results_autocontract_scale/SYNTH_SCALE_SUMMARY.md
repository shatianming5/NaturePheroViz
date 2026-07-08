# Goldless contract synthesis at scale (cross-vendor, de-leaked intent)

Pooled N = 115 (5 vendors x ~23 operators), de-leaked high-level-goal intent (no formula, no operator keyword).

| vendor | N | CORE (fire-slip & pass-correct) | FULL (+ alt-robust) |
|---|---|---|---|
| gpt-5.3-codex | 23 | 20/23 = 87.0% [67.9-95.5] | 19/23 = 82.6% [62.9-93.0] |
| gemini-3.1-pro-preview | 23 | 17/23 = 73.9% [53.5-87.5] | 16/23 = 69.6% [49.1-84.4] |
| gpt-5.4 | 23 | 18/23 = 78.3% [58.1-90.3] | 18/23 = 78.3% [58.1-90.3] |
| gpt-5.5 | 23 | 22/23 = 95.7% [79.0-99.2] | 22/23 = 95.7% [79.0-99.2] |
| claude-opus-4.8 | 23 | 15/23 = 65.2% [44.9-81.2] | 15/23 = 65.2% [44.9-81.2] |
| **POOLED** | **115** | **92/115 = 80.0% [71.8-86.3]** | **90/115 = 78.3% [69.9-84.8]** |
