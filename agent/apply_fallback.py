"""Deprecated one-off patch helper.

The upstream copy of this file contains an unterminated embedded code string.
The runnable PheroViz pipeline lives in ``app/services/single_chain_runner.py``;
this helper should not be used against the integrated workspace.
"""


def main() -> None:
    raise SystemExit(
        "apply_fallback.py is a deprecated upstream patch helper and is disabled "
        "in the integrated workspace. Use agent/run_chain.py for normal runs."
    )


if __name__ == "__main__":
    main()
