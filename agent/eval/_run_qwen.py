"""Run Qwen zero-shot benchmark with DashScope env vars."""
import os, sys, subprocess

env = os.environ.copy()
env["QWEN_API_BASE"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
env["QWEN_API_KEY"] = "sk-ws-H.REIIXHX.LiaP.MEYCIQCAxPhVbfwM5uDU6zcsVSURPuAY8YyFqyNsYnQ7cz5z7QIhALzNYcFsSSpCPxsKtGkNpNpILHFFh9e8TBSDClMJXDfq"

cmd = [sys.executable, "eval/run_benchmark.py"] + sys.argv[1:]
result = subprocess.run(cmd, env=env, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.exit(result.returncode)
