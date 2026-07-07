# Exemplar ablation: k-repeat mean +/- sd (reproducibility)

Reasoning models are not bit-reproducible even at temperature 0, so we report the mean and sd of the CORE synthesis rate over k independent runs per vendor (same cached messy NL, operator known). The baseline arm is zero-shot synthesis.

| vendor | k | zero-shot (baseline) | one-shot | few-shot |
|---|---|---|---|---|
| gpt-5.4 | 3 | 83±0% | 65±4% | 57±7% |
| gemini-3.1-pro-preview | 2 | 63±2% | 48±4% | 57±0% |
| **pooled** | 5 | **75±10%** | **58±9%** | **57±5%** |

**Reading:** zero-shot 75±10% vs one-shot 58±9% vs few-shot 57±5%. The run-to-run sd (10--9 pts) is the scale of the exemplar effect, confirming exemplars do not reliably improve synthesis (the trend is within run-to-run noise). Zero-shot is the right default.
