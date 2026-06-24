import os, sys, json
from pathlib import Path

os.environ["LLM_API_BASE"] = "http://1.14.177.180:4141/v1"
os.environ["LLM_API_KEY"] = "sk-intern"

mpa_dir = Path("eval/MatPlotAgent")

from run_benchmark import _load_matplotbench
tasks = _load_matplotbench()
task = tasks[0]
print(f"Testing task {task['task_id']}: {task['goal']}")

workspace = Path("eval/_mpa_test_ws")
workspace.mkdir(parents=True, exist_ok=True)
task["data"].to_csv(workspace / "data.csv", index=False)

sys.path.insert(0, str(Path(__file__).parent / "MatPlotAgent"))

from agents.plot_agent import PlotAgent

config = {'workspace': str(workspace)}
action_agent = PlotAgent(config, task["goal"])
print("Calling run_one_time with model_type='gpt-5.4'...")
log, code = action_agent.run_one_time("gpt-5.4", "test.png", no_sysprompt=False)
print(f"Log: {log[:300]}")
print(f"Code:\n{code[:500]}")
