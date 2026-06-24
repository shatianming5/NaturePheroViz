# Benchmark Results

## Systems × Metrics

| system | tasks | exec_pass_rate | data_fidelity | visual_form | series_cohesion | rounds | pass@1 |
|---|---|---|---|---|---|---|---|
| claude_oneshot | 24 | 17/24 (70.8%) | 0.599 | 0.000 | 0.000 | 1.0 | 0.708 |
| gpt4o_oneshot | 24 | 19/24 (79.2%) | 0.387 | 0.000 | 0.000 | 1.0 | 0.792 |
| lida | 3 | 0/3 (0.0%) | 0.000 | 0.000 | 0.000 | 0.0 | 0.000 |
| ours | 23 | 15/23 (65.2%) | 0.289 | 0.656 | 0.694 | 1.5 | 0.652 |
| qwen_zeroshot | 22 | 18/22 (81.8%) | 0.670 | 0.000 | 0.000 | 1.0 | 0.818 |

## Per-System Detail

### claude_oneshot
- Tasks: 24
- Exec-pass: 17/24 (70.8%)
- Mean data_fidelity: 0.599
- Median data_fidelity: 1.000
- Mean visual_form: 0.000
- Mean series_cohesion: 0.000
- Mean rounds used: 1.0
- Fidelity distribution: [0-.25):7 [.25-.50):0 [.50-.75):0 [.75-1.0]:10

### gpt4o_oneshot
- Tasks: 24
- Exec-pass: 19/24 (79.2%)
- Mean data_fidelity: 0.387
- Median data_fidelity: 0.093
- Mean visual_form: 0.000
- Mean series_cohesion: 0.000
- Mean rounds used: 1.0
- Fidelity distribution: [0-.25):12 [.25-.50):0 [.50-.75):0 [.75-1.0]:7

### lida
- Tasks: 3
- Exec-pass: 0/3 (0.0%)
- Mean data_fidelity: 0.000
- Median data_fidelity: 0.000
- Mean visual_form: 0.000
- Mean series_cohesion: 0.000
- Mean rounds used: 0.0
- Fidelity distribution: [0-.25):0 [.25-.50):0 [.50-.75):0 [.75-1.0]:0

### ours
- Tasks: 23
- Exec-pass: 15/23 (65.2%)
- Mean data_fidelity: 0.289
- Median data_fidelity: 0.000
- Mean visual_form: 0.656
- Mean series_cohesion: 0.694
- Mean rounds used: 1.5
- Fidelity distribution: [0-.25):10 [.25-.50):0 [.50-.75):2 [.75-1.0]:3

### qwen_zeroshot
- Tasks: 22
- Exec-pass: 18/22 (81.8%)
- Mean data_fidelity: 0.670
- Median data_fidelity: 1.000
- Mean visual_form: 0.000
- Mean series_cohesion: 0.000
- Mean rounds used: 1.0
- Fidelity distribution: [0-.25):5 [.25-.50):1 [.50-.75):1 [.75-1.0]:11

## Per-Task Breakdown

| task_id | claude_oneshot_exec | claude_oneshot_fid | gpt4o_oneshot_exec | gpt4o_oneshot_fid | lida_exec | lida_fid | ours_exec | ours_fid | qwen_zeroshot_exec | qwen_zeroshot_fid |
|---|---|---|---|---|---|---|---|---|---|---|
| 100 | PASS | 1.000 | PASS | 0.000 | - | - | PASS | 0.000 | PASS | 1.000 |
| 76 | PASS | 0.000 | PASS | 0.000 | FAIL | 0.000 | FAIL | 0.000 | PASS | 1.000 |
| 77 | PASS | 1.000 | PASS | 1.000 | FAIL | 0.000 | PASS | 0.667 | PASS | 1.000 |
| 78 | PASS | 1.000 | PASS | 0.000 | FAIL | 0.000 | FAIL | 0.000 | PASS | 1.000 |
| 79 | PASS | 1.000 | PASS | 1.000 | - | - | PASS | 0.000 | PASS | 0.000 |
| 80 | FAIL | 0.000 | FAIL | 0.000 | - | - | PASS | 0.000 | PASS | 1.000 |
| 81 | PASS | 0.000 | PASS | 0.000 | - | - | FAIL | 0.000 | PASS | 0.000 |
| 83 | PASS | 0.000 | PASS | 0.000 | - | - | PASS | 0.000 | PASS | 0.400 |
| 84 | PASS | 1.000 | PASS | 0.857 | - | - | PASS | 0.000 | PASS | 1.000 |
| 85 | FAIL | 0.000 | FAIL | 0.000 | - | - | FAIL | 0.000 | PASS | 1.000 |
| 86 | FAIL | 0.000 | FAIL | 0.000 | - | - | FAIL | 0.000 | FAIL | 0.000 |
| 87 | PASS | 0.000 | PASS | 0.191 | - | - | FAIL | 0.000 | FAIL | 0.000 |
| 88 | PASS | 0.000 | FAIL | 0.000 | - | - | FAIL | 0.000 | FAIL | 0.000 |
| 89 | PASS | 0.000 | PASS | 0.000 | - | - | PASS | 1.000 | PASS | 0.000 |
| 90 | FAIL | 0.000 | FAIL | 0.000 | - | - | FAIL | 0.000 | PASS | 1.000 |
| 91 | FAIL | 0.000 | PASS | 0.093 | - | - | PASS | 0.000 | PASS | 0.667 |
| 92 | FAIL | 0.000 | PASS | 0.000 | - | - | PASS | 0.000 | PASS | 1.000 |
| 93 | PASS | 1.000 | PASS | 1.000 | - | - | PASS | 0.000 | PASS | 1.000 |
| 95 | FAIL | 0.000 | PASS | 0.000 | - | - | PASS | 0.000 | FAIL | 0.000 |
| 96 | PASS | 1.000 | PASS | 1.000 | - | - | PASS | 0.667 | PASS | 0.000 |
| 97 | PASS | 1.000 | PASS | 0.032 | - | - | PASS | 1.000 | PASS | 1.000 |
| 99 | PASS | 0.179 | PASS | 0.179 | - | - | PASS | 0.000 | PASS | 0.000 |
| builtin_001 | PASS | 1.000 | PASS | 1.000 | - | - | PASS | 1.000 | - | - |
| builtin_002 | PASS | 1.000 | PASS | 1.000 | - | - | - | - | - | - |
