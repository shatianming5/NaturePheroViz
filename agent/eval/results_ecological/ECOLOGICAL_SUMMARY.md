# Ecological-validity pilot — operator-ambiguity of REAL analyst requests (DS-1000)

Question the 77% headline conditions on: how often is a real, in-the-wild
data-transform request operator-ambiguous (leaves an outcome-changing operator
choice unspecified)? Corpus = real StackOverflow-derived DS-1000 pandas intents
in the ambiguity-prone families; each stripped to its prose intent (the embedded
I/O example a benchmark adds is dropped). Conservative: DS-1000 is curated to be
answerable, yet its prose still under-specifies the operator at this rate.

- N real requests: 40
- **LLM judge (opencode/north-mini-code-free): operator-ambiguous 32/40 (80% [95% CI 65-90])**
- lexical baseline: operator-ambiguous 9/40 (22% [95% CI 12-38])
- LLM-vs-lexical agreement: 9/40 (22%)

## Ambiguity axis (LLM judge, among ambiguous)
- grouping         13
- boundary         8
- missing          3
- none             3
- duplicate        2
- ordering         2
- tie              1

## Interpretation
A substantial ambiguous fraction shows the 77% regime is ecologically real —
real analyst prose routinely leaves the operator decision open, exactly the
under-specification the headline measures — not an artifact of author-designed
traps. Per-item labels (prose + LLM + lexical) are in ambiguity.json for audit.

Caveat: the LLM judge is a SINGLE free model and, on a few items, residual
embedded tables may leak into its view; the lexical 22% is a keyword-only lower
bound. Read the two rates as BRACKETING the true value, not a point estimate;
the released prose+labels allow human re-scoring. Precise deployment distribution
is future work.
