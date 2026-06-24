# RUN 执行日志

说明：记录每次执行命令的参数、环境与结果概要（数据保存在 `outputs/`，该目录被 `.gitignore` 忽略）。

## 2025-09-24 运行1
- 命令：python scripts/env_bootstrap.py --query "cancer" --max 10 --images --out outputs/run_cancer_1 --sleep 1.0
- 环境：Python 3.11.11；Conda 检测（active env: None）
- 结果：成功，保存 10 条记录；如有 PMC 开放获取文章，图像保存至 outputs/run_cancer_1/images/

## 2025-09-24 运行2
- 命令：python scripts/env_bootstrap.py --query "cancer immunotherapy" --max 15 --images --out outputs/run_ci_1 --sleep 1.0
- 环境：Python 3.11.11；Conda 检测（active env: None）
- 结果：成功，保存 15 条记录；如有 PMC 开放获取文章，图像保存至 outputs/run_ci_1/images/

## 2025-09-24 运行3
- 命令：python scripts/env_bootstrap.py --query "肿瘤免疫" --max 15 --images --out outputs/run_cn_imm_1 --sleep 1.0
- 环境：Python 3.11.11；Conda 检测（active env: None）
- 结果：成功，保存 14 条记录；如有 PMC 开放获取文章，图像保存至 outputs/run_cn_imm_1/images/

## 2025-09-24 运行4
- 命令：python scripts/env_bootstrap.py --query "checkpoint inhibitor" --max 20 --images --out outputs/run_ci_checkpt_1 --sleep 1.0 --timeout 30 --max-retries 3 --append
- 环境：Python 3.11.11；Conda 检测（active env: None）
- 结果：成功，保存 20 条记录；如有 PMC 开放获取文章，图像保存至 outputs/run_ci_checkpt_1/images/

## 2025-09-24 运行5
- 命令：python scripts/env_bootstrap.py --query "单细胞 癌症" --max 20 --images --out outputs/run_cn_scRNA_1 --sleep 1.0 --timeout 30 --max-retries 3 --append
- 环境：Python 3.11.11；Conda 检测（active env: None）
- 结果：成功，保存 14 条记录；如有 PMC 开放获取文章，图像保存至 outputs/run_cn_scRNA_1/images/

## 2025-09-24 运行6（已获授权）
- 命令：python scripts/nature_fig_fetch.py --url "https://www.nature.com/articles/s41586-025-09507-9/figures/1" --out outputs/nature_test --sleep 1.0 --timeout 30 --max-retries 2
- 结果：成功，已保存图片与 caption；输出目录 outputs/nature_test/s41586-025-09507-9/

## 2025-09-24 运行7（已获授权）
- 命令：python scripts/nature_source_data_fetch.py --url "https://www.nature.com/articles/s41586-025-09507-9" --out outputs/nature_source_test --sleep 1.0 --timeout 30 --max-retries 3
- 结果：发现 5 个 Source data 链接（包含 Fig. 4 与 Extended Data Fig. 7）；文件与清单位于 outputs/nature_source_test/s41586-025-09507-9/

## 2025-09-24 运行8（批量后处理，已获授权）
- 命令：python scripts/nature_post_fetch.py --jsonl outputs/run_ci_checkpt_1/articles.jsonl --out outputs/nature_content --authorized-figs --authorized-source --max-figs 2 --max-articles 2 --sleep 0.8 --timeout 30 --max-retries 2
- 结果：对前 2 篇 Nature 文章尝试抓取前 2 个图页与整页 Source data；部分文章无可用图像或 Source data，已记录清单与提示。

## 2025-09-25 01:39:53 ??(auto --stream ?????)
- ??:python nature_all_in_one.py auto --stream --max-per-keyword 1 --max-articles 2 --max-figs 1 --sort year_desc --timeout 30 --max-retries 2
- ??:?????? 2 ???;??? outputs/nature_content/<article-id>/{figures,source_data,meta}

## 2026-06-02 运行9（Codex 修复验证，已获授权）
- 复现命令：`python nature_download/nature_all_in_one.py source --url https://www.nature.com/articles/s41586-025-09507-9 --out outputs/codex_probe_source --section-id Sec71 --sleep 0 --timeout 30 --max-retries 1`
- 复现结果：修复前 `Source data links found: 0`。原因是 `#Sec71` 命中 `h2` 标题节点，真实 Source data 下载链接位于后续同级内容中。
- 修复内容：`find_source_data_links()` 支持 section 标题后续 sibling 扫描，并在 section 范围为空时回退全页扫描；`auto` 非流式完成后立即返回并透传 `max_empty_figs`；`postfetch_article()` 处理不可达文章返回 `None` 的情况。
- 验证命令：`python nature_download/nature_all_in_one.py source --url https://www.nature.com/articles/s41586-025-09507-9 --out outputs/codex_probe_source_fix --section-id Sec71 --sleep 0 --timeout 30 --max-retries 1`
- 验证结果：成功发现 2 个 Source data 链接，保存 `41586_2025_9507_MOESM16_ESM.xlsx` 与 `41586_2025_9507_MOESM17_ESM.xlsx`。
- 验证命令：`python nature_download/nature_all_in_one.py fig --url https://www.nature.com/articles/s41586-025-09507-9/figures/1 --out outputs/codex_probe_fig_fix --sleep 0 --timeout 30 --max-retries 1`
- 验证结果：成功保存 `fig_001.png` 和 `fig_001.txt` caption。
- 验证命令：`python nature_download/nature_all_in_one.py postfetch --jsonl <generated-jsonl> --out outputs/codex_probe_postfetch_fix --max-articles 1 --max-figs 1 --max-empty-figs 1 --sleep 0 --timeout 30 --max-retries 1 --processed-file outputs/codex_probe_postfetch_fix/_processed_codex.txt`
- 验证结果：完整 postfetch 链路成功，在同一文章目录下保存 figure、caption、两个 Source data XLSX 和 manifest。
- 附加验证：`python -m py_compile nature_download/nature_all_in_one.py` 成功；`python -m pytest -q agent/tests/test_smoke.py` 结果为 `2 passed`。
- Git 状态：当前集成工作目录不是 Git 仓库，无法 commit/push。
