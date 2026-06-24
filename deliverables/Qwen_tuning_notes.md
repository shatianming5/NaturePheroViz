# Qwen 调优笔记

## 环境配置

- **Base URL**: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- **模型**: `qwen-plus`
- **Key 前缀**: `sk-ws-...` (阿里百炼格式)

## 遇到的问题与解决

### 1. API Key 认证问题

**症状**: 用代理地址 `http://1.14.177.180:4141` 返回 401。  
**原因**: Key 是阿里百炼格式，不能用代理。  
**解决**: 使用正确的 DashScope base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`

### 2. Frequency Limit (间歇性 401/429)

**症状**: 连续请求后返回 401。  
**原因**: DashScope 有频率限制。  
**解决**: 
- 每个请求间间隔 0.6s
- 401/429 时重试最多 3 次，指数退避 (2s, 4s, 6s)

### 3. 代码提取问题 (核心改进)

**症状**: 初始版本要求 JSON 输出 `{"code": "..."}`，Qwen 经常不返回合法 JSON，导致大面积 exec-fail (2/22)。

**解决**: 实现 `_extract_code()` 多层回退提取:

```
优先级:
1) 正则匹配 {"code": "..."}  (JSON 片段)
2) 完整 JSON 解析 { ... }
3) ```python ... ``` 代码块提取
4) ax./plt. 行直接匹配
5) 基于列名 + 图表类型的分数线选择
```

**效果对比**:

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| Exec-pass | 2/22 (9%) | 18/22 (82%) |
| Data Fidelity | 0.29 | 0.67 |

### 4. Prompt 优化

**修复前**:
```
Return ONLY strict JSON: {"code": "<plotting code body using df and ax>"}
```

**修复后**:
```
Write a SINGLE line of matplotlib code to plot this data.
Output ONLY the code, nothing else. Example: ax.bar(df['x_col'], df['y_col'])
```

改为要求直接输出纯代码行而非 JSON，大幅提升成功率。

---

## 最终配置

```python
QWEN_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_API_KEY = "sk-ws-H..."
model = "qwen-plus"
temperature = 0.2
max_tokens = 400
rate_limit = 0.6s/call + 3 retries with exponential backoff
```
