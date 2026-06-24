import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.bon_comparison import run_best_of_n_hard_case_compare


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    summary = run_best_of_n_hard_case_compare(args.output_dir)
    output_dir = Path(args.output_dir) if args.output_dir else Path(summary["input_csv"]).resolve().parent
    summary_path = output_dir / "bon_hard_case_compare.json"
    print(json.dumps({"summary_path": str(summary_path), "comparison": summary["comparison"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
