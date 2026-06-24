import os, sys, json
os.environ["LLM_API_BASE"] = "http://1.14.177.180:4141/v1"
os.environ["LLM_API_KEY"] = "sk-intern"
sys.path.insert(0, ".")
from eval.baseline_runners import _qwen_generate, QWEN_MODELS
import pandas as pd

# Create a minimal task
task = {
    "task_id": "76",
    "goal": "Show monthly sales trend",
    "family": "line",
    "intent": {"x": "month", "y": "sales"},
    "data": pd.DataFrame({"month": ["Jan","Feb","Mar"], "sales": [100,200,150]})
}

print(f"Model: {QWEN_MODELS['qwen_zeroshot']}")
code = _qwen_generate(task, QWEN_MODELS["qwen_zeroshot"])
print(f"Generated code: {code}")
