import os, sys, json, requests

# Set env
os.environ["QWEN_API_BASE"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
os.environ["QWEN_API_KEY"] = "sk-ws-H.REIIXHX.LiaP.MEYCIQCAxPhVbfwM5uDU6zcsVSURPuAY8YyFqyNsYnQ7cz5z7QIhALzNYcFsSSpCPxsKtGkNpNpILHFFh9e8TBSDClMJXDfq"

# Add parent to path
agent_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, agent_dir)

# Import and use the qwen runner directly
from eval.baseline_runners import run_qwen_zeroshot, _qwen_generate
from eval.run_benchmark import _builtin_tasks

tasks = _builtin_tasks()
task = tasks[0]
print(f"Testing task: {task['task_id']}")
print(f"  Columns: {list(task['data'].columns)}")
print(f"  Goal: {task['goal']}")
print()

# Test API call
print("Calling _qwen_generate...")
try:
    code = _qwen_generate(task, "qwen-plus")
    print(f"  Generated code: {code}")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
