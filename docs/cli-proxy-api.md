# CLIProxyAPI（Go 代理）使用说明

> 本文档假设 `CLIProxyAPI/` 是一个独立的 Go 项目目录；下文提到的路径均以 `CLIProxyAPI/` 作为工作目录（repo root）来描述。

## 启动与配置

- 入口是 Go 程序 `cmd/server/main.go:72`，默认读取当前目录的 `config.yaml`（模板见 `config.example.yaml:1`）。
- 最小可跑配置：复制模板并把 `api-keys` 改成你自己的（这是“调用代理时”的鉴权 key，不是上游模型的 key）。
  - `Copy-Item config.example.yaml config.yaml`
- （可选）先做 OAuth 登录（会把凭据存到 `auth-dir` 下的 `*.json` 文件里），按需执行一次即可：`-login`(Gemini)、`-codex-login`(OpenAI Codex)、`-claude-login`、`-qwen-login`、`-iflow-login`（参数定义见 `cmd/server/main.go:72`）
  - 例：`go run ./cmd/server -codex-login -config config.yaml`
- 启动服务：
  - 直接跑：`go run ./cmd/server -config config.yaml`
  - 或先编译（Windows）：`go build -o cli-proxy-api.exe ./cmd/server` 然后 `.\cli-proxy-api.exe -config config.yaml`
  - 或 Docker：`docker compose up -d`（见 `docker-compose.yml:1`，默认映射 `8317` + OAuth 回调端口）

## 启动后如何调用

- 路由定义在 `internal/api/server.go:309`，`/v1/*` 与 `/v1beta/*` 默认都需要 `Authorization: Bearer <key>`（`<key>` 来自 `config.yaml` 的 `api-keys`）。
- 注意：`GET /v1beta/models` 可能返回形如 `models/gemini-3-flash-preview` 的模型名；实际调用 URL 已经包含 `/models/`，因此请求时用 `.../v1beta/models/gemini-3-flash-preview:generateContent`（把前缀 `models/` 去掉）。

```powershell
curl.exe -s  -H "Authorization: Bearer <key>" http://localhost:8317/v1/models

curl.exe -X POST -H "Authorization: Bearer <key>" -H "Content-Type: application/json" `
  http://localhost:8317/v1/chat/completions `
  -d '{"model":"gpt-5","messages":[{"role":"user","content":"Hello"}]}'

curl.exe -X POST -H "Authorization: Bearer <key>" -H "Content-Type: application/json" `
  http://localhost:8317/v1/responses `
  -d '{"model":"gpt-5","input":"Hello"}'

curl.exe -X POST -H "Authorization: Bearer <key>" -H "Content-Type: application/json" `
  http://localhost:8317/v1/messages `
  -d '{"model":"claude-sonnet-4-5-20250929","max_tokens":512,"messages":[{"role":"user","content":"Hello"}]}'

curl.exe -X POST -H "Authorization: Bearer <key>" -H "Content-Type: application/json" `
  "http://localhost:8317/v1beta/models/gemini-3-flash-preview:generateContent" `
  -d '{"contents":[{"parts":[{"text":"Hello"}]}]}'

curl.exe -s  -H "Authorization: Bearer <key>" http://localhost:8317/v1beta/models
```

## 可用的模型

- 以“你当前实例实际可用”为准：用 `GET /v1/models`（OpenAI 风格）或 `GET /v1beta/models`（Gemini 风格）查询。
- 项目内置的静态模型 ID 定义在 `internal/registry/model_definitions.go:7`（这些会在对应 provider 有可用账号/Key 时注册进 `/v1/models`）：
  - OpenAI/Codex：`gpt-5`, `gpt-5-minimal`, `gpt-5-low`, `gpt-5-medium`, `gpt-5-high`, `gpt-5-codex`, `gpt-5-codex-low`, `gpt-5-codex-medium`, `gpt-5-codex-high`, `gpt-5-codex-mini`, `gpt-5-codex-mini-medium`, `gpt-5-codex-mini-high`, `gpt-5.1`, `gpt-5.1-none`, `gpt-5.1-low`, `gpt-5.1-medium`, `gpt-5.1-high`, `gpt-5.1-codex`, `gpt-5.1-codex-low`, `gpt-5.1-codex-medium`, `gpt-5.1-codex-high`, `gpt-5.1-codex-mini`, `gpt-5.1-codex-mini-medium`, `gpt-5.1-codex-mini-high`, `gpt-5.1-codex-max`, `gpt-5.1-codex-max-low`, `gpt-5.1-codex-max-medium`, `gpt-5.1-codex-max-high`, `gpt-5.1-codex-max-xhigh`
  - Claude：`claude-haiku-4-5-20251001`, `claude-sonnet-4-5-20250929`, `claude-opus-4-1-20250805`, `claude-opus-4-20250514`, `claude-sonnet-4-20250514`, `claude-3-7-sonnet-20250219`, `claude-3-5-haiku-20241022`
  - Gemini：`gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3-flash-preview`, `gemini-3-pro-preview`
  - Gemini Vertex：`gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3-pro-preview`, `gemini-3-pro-image-preview`
  - AIStudio：`gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3-pro-preview`, `gemini-pro-latest`, `gemini-flash-latest`, `gemini-flash-lite-latest`, `gemini-2.5-flash-image-preview`, `gemini-2.5-flash-image`
  - Qwen：`qwen3-coder-plus`, `qwen3-coder-flash`, `vision-model`
  - iFlow：`tstars2.0`, `qwen3-coder-plus`, `qwen3-coder`, `qwen3-max`, `qwen3-vl-plus`, `qwen3-max-preview`, `kimi-k2-0905`, `glm-4.6`, `kimi-k2`, `kimi-k2-thinking`, `deepseek-v3.2`, `deepseek-v3.1`, `deepseek-r1`, `deepseek-v3`, `qwen3-32b`, `qwen3-235b-a22b-thinking-2507`, `qwen3-235b-a22b-instruct`, `qwen3-235b`, `minimax-m2`
- 你也可以在 `config.yaml` 里配置 `openai-compatibility` 自定义上游（例如 OpenRouter）模型别名；这些别名会直接出现在 `/v1/models`。
