"""Run full Qwen zero-shot MatPlotBench benchmark."""
import os, sys

# Must set env BEFORE any imports that cache them
os.environ["QWEN_API_BASE"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
os.environ["QWEN_API_KEY"] = "sk-ws-H.REIIXHX.LiaP.MEYCIQCAxPhVbfwM5uDU6zcsVSURPuAY8YyFqyNsYnQ7cz5z7QIhALzNYcFsSSpCPxsKtGkNpNpILHFFh9e8TBSDClMJXDfq"
os.environ["LLM_API_BASE"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
os.environ["LLM_API_KEY"] = "sk-ws-H.REIIXHX.LiaP.MEYCIQCAxPhVbfwM5uDU6zcsVSURPuAY8YyFqyNsYnQ7cz5z7QIhALzNYcFsSSpCPxsKtGkNpNpILHFFh9e8TBSDClMJXDfq"

agent_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(agent_dir)
sys.path.insert(0, agent_dir)

from eval.run_benchmark import main

# Simulate: python eval/run_benchmark.py --system qwen_zeroshot --dataset matplotbench --out eval/results_bench
sys.argv = ["run_benchmark.py", "--system", "qwen_zeroshot", "--dataset", "matplotbench", "--out", "eval/results_bench"]
main()
