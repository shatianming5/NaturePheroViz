import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.ablation_runner import run_ablation_suite


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()

    summary = run_ablation_suite(args.output_dir, rounds=args.rounds)
    print(
        json.dumps(
            {
                "output_dir": summary["output_dir"],
                "runs_csv": str(Path(summary["output_dir"]) / "ablation_runs.csv"),
                "aggregates_csv": str(Path(summary["output_dir"]) / "ablation_aggregates.csv"),
                "configs": [item["name"] for item in summary["configs"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
