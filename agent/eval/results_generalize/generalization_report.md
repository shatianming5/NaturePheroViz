# W3 NL→operator generalization — three honest layers (raw JSON: intent_llm.json)

| eval | set | inferer | op-accuracy | note |
|---|---|---|---|---|
| grid (templated) | 68 | regex | 100% | co-designed upper bound (signals = grid lexicon) |
| held-out paraphrase | 19 | regex | **26%** (5/19, 12 abstain, 2 wrong) | honest generalization; abstain-safe (only 2 miswired) |
| held-out paraphrase | 19 | **LLM (opencode north-mini-code-free)** | **84%** (16/19) | deployable classifier; no API key; per-case JSON saved |

Reading: the regex inferer overfits the grid (100%→26% off-lexicon) but abstains safely
(2/19 miswired). A free-model LLM classifier recovers 84% on the same held-out paraphrases,
so NL→operator is solvable for deployment; the oracle/contracts (the contribution) are
unchanged. The 2 regex miswires ("share of"→within_group_share, "ties"→topn) are expected
keyword failure modes that motivate the LLM path. Scripts: transform_paraphrase.py, intent_llm.py.
