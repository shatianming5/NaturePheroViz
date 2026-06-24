# Cross-vendor frontier-model comparison (68-grid)

Every current frontier model — across OpenAI, Anthropic, Google, including a
code-specialized model — still commits silent semantic errors at a high rate,
while the goldless oracle keeps 0% false-positives on all of them.

| model | vendor | ambiguous silent | clarified silent | oracle recall | oracle FP |
|---|---|---|---|---|---|
| gpt-5.4 | OpenAI | 29/68 = 42% | 10/68 = 14% | 35/39 = 89% | 0/97 = 0% |
| gpt-5.5 | OpenAI | 22/68 = 32% | 8/68 = 11% | 26/30 = 86% | 0/103 = 0% |
| gpt-5.3-codex | OpenAI | 25/68 = 36% | 9/68 = 13% | 25/34 = 73% | 0/100 = 0% |
| gemini-3.1-pro-preview | Google | 23/68 = 33% | 11/68 = 16% | 27/34 = 79% | 0/102 = 0% |
| claude-opus-4.8 | Anthropic | 26/68 = 38% | 10/68 = 14% | 32/36 = 88% | 0/100 = 0% |

## Reading
- All 5 frontier models (incl. the strongest from 3 vendors + a code model) show
  32-42% ambiguous silent-error rate — silent error is NOT a weak/old-model artifact.
- Oracle FP = 0% on every model (502+ correct results) — zero false alarms cross-vendor.
- recall 73-89% incl. the 5 new contract-immature families; core-12 classes stay 100%.