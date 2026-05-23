# 使用手册

## API 端点

### 健康检查

```bash
curl http://localhost:8000/health
```

响应：
```json
{
  "status": "healthy",
  "version": "3.1.15",
  "protocol_version": 1,
  "queued_tasks": 0,
  "processing_tasks": 0,
  "completed_tasks": 0,
  "failed_tasks": 0,
  "max_concurrent_requests": 3,
  "processing_window_size": 64,
  "task_retention_seconds": 86400,
  "task_cleanup_interval_seconds": 300
}
```

### 同步解析

等待解析完成后在同一响应中返回结果。

```bash
curl -X POST http://localhost:8000/file_parse \
  -F "files=@document.pdf"
```

响应：
```json
{
  "task_id": "a029cbf5-...",
  "status": "completed",
  "backend": "hybrid-auto-engine",
  "file_names": ["document"],
  "created_at": "2026-05-23T03:19:14.751931+00:00",
  "started_at": "2026-05-23T03:19:14.752094+00:00",
  "completed_at": "2026-05-23T03:19:41.938601+00:00",
  "results": {
    "document": {
      "md_content": "# 解析内容\n\n..."
    }
  }
}
```

### 异步解析

立即返回 task_id，客户端轮询获取结果。

**第 1 步 — 提交任务：**

```bash
curl -X POST http://localhost:8000/tasks \
  -F "files=@document.pdf"
```

响应：
```json
{
  "task_id": "cf222e69-...",
  "status": "pending",
  "queued_ahead": 0,
  "message": "Task submitted successfully",
  "status_url": "http://localhost:8000/tasks/cf222e69-...",
  "result_url": "http://localhost:8000/tasks/cf222e69-.../result"
}
```

**第 2 步 — 查询状态：**

```bash
curl http://localhost:8000/tasks/{task_id}
```

**第 3 步 — 获取结果（状态为 "completed" 时）：**

```bash
curl http://localhost:8000/tasks/{task_id}/result
```

## 请求参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `files` | file[] | **必填** | PDF、图片、DOCX、PPTX 或 XLSX 文件 |
| `backend` | string | `hybrid-auto-engine` | 解析后端（见下方） |
| `lang_list` | string[] | `["ch"]` | OCR 语言提示 |
| `parse_method` | string | `auto` | `auto`、`txt` 或 `ocr` |
| `formula_enable` | bool | `true` | 启用公式解析 |
| `table_enable` | bool | `true` | 启用表格解析 |
| `image_analysis` | bool | `true` | 启用图片/图表分析（VLM/混合后端） |
| `return_md` | bool | `true` | 返回 Markdown 内容 |
| `return_middle_json` | bool | `false` | 返回中间 JSON |
| `return_model_output` | bool | `false` | 返回模型输出 JSON |
| `return_content_list` | bool | `false` | 返回内容列表 JSON |
| `return_images` | bool | `false` | 返回提取的图片 |
| `response_format_zip` | bool | `false` | 以 ZIP 格式返回（而非 JSON） |
| `start_page_id` | int | `0` | 起始页码（从 0 开始） |
| `end_page_id` | int | `99999` | 结束页码（从 0 开始） |

### 后端选项

| 后端 | 说明 | 是否需要 GPU | 支持语言 |
|------|------|-------------|---------|
| `pipeline` | 传统流水线，无幻觉 | 可选 | 多语言 |
| `vlm-auto-engine` | 通过本地 GPU 运行 VLM | 需要 | 中英文 |
| `vlm-http-client` | 通过远程服务器运行 VLM | 不需要 | 中英文 |
| `hybrid-auto-engine` | Pipeline + VLM 混合（**默认**） | 需要 | 多语言 |
| `hybrid-http-client` | 通过远程服务器运行混合模式 | 不需要 | 多语言 |

### 语言选项

常用 `lang_list` 值：

| 代码 | 语言 |
|------|------|
| `ch` | 中文、英文、繁体中文 |
| `en` | 英文 |
| `japan` | 中文、英文、繁体中文、日文 |
| `korean` | 韩文、英文 |
| `latin` | 法文、德文、意大利文、西班牙文、葡萄牙文等 |
| `arabic` | 阿拉伯文、波斯文、乌尔都文等 |
| `cyrillic` | 俄文、乌克兰文、保加利亚文等 |

## 使用示例

### 指定后端解析

```bash
# 仅 Pipeline（无需 GPU，但较慢）
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "backend=pipeline"

# VLM 自动引擎（需要 GPU）
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "backend=vlm-auto-engine"
```

### 解析指定页面

```bash
# 仅解析第 0-5 页
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "start_page_id=0" \
  -F "end_page_id=5"
```

### 指定语言提示

```bash
# 英文文档
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "lang_list=en"

# 日文文档
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "lang_list=japan"
```

### 禁用公式/表格解析

```bash
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "formula_enable=false" \
  -F "table_enable=false"
```

### 获取所有输出格式

```bash
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "return_md=true" \
  -F "return_middle_json=true" \
  -F "return_content_list=true" \
  -F "return_images=true" \
  -F "response_format_zip=true"
```

### Python 客户端示例

```python
import requests

API_URL = "http://localhost:8000"

# 同步解析
with open("document.pdf", "rb") as f:
    response = requests.post(
        f"{API_URL}/file_parse",
        files={"files": ("document.pdf", f, "application/pdf")},
        data={"backend": "hybrid-auto-engine", "lang_list": ["ch"]},
    )
    result = response.json()
    print(result["results"]["document"]["md_content"])

# 异步解析
with open("document.pdf", "rb") as f:
    submit = requests.post(
        f"{API_URL}/tasks",
        files={"files": ("document.pdf", f, "application/pdf")},
    )
    task_id = submit.json()["task_id"]

import time
while True:
    status = requests.get(f"{API_URL}/tasks/{task_id}").json()
    if status["status"] == "completed":
        result = requests.get(f"{API_URL}/tasks/{task_id}/result").json()
        print(result["results"]["document"]["md_content"])
        break
    elif status["status"] == "failed":
        print("解析失败:", status.get("error"))
        break
    time.sleep(2)
```

## 压力测试

### 顺序延迟测试

```bash
#!/bin/bash
# 逐个测量每个文件的解析延迟
for pdf in pdf/*.pdf; do
    start=$(date +%s%N)
    curl -s -X POST http://localhost:8000/file_parse -F "files=@$pdf" > /dev/null
    end=$(date +%s%N)
    elapsed=$(( (end - start) / 1000000 ))
    echo "$(basename $pdf): ${elapsed}ms"
done
```

### 并发吞吐量测试

```bash
#!/bin/bash
# 同时提交所有 PDF，测量总吞吐量
TASK_IDS=()
for pdf in pdf/*.pdf; do
    resp=$(curl -s -X POST http://localhost:8000/tasks -F "files=@$pdf")
    tid=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
    TASK_IDS+=("$tid")
done

# 轮询直到全部完成
while true; do
    all_done=true
    for tid in "${TASK_IDS[@]}"; do
        status=$(curl -s http://localhost:8000/tasks/$tid | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
        if [ "$status" != "completed" ] && [ "$status" != "failed" ]; then
            all_done=false
        fi
    done
    $all_done && break
    sleep 2
done
```

### Python 压力测试脚本

```python
import requests, time, statistics, concurrent.futures

API_URL = "http://localhost:8000"
PDF_FILES = ["pdf/doc1.pdf", "pdf/doc2.pdf", "pdf/doc3.pdf"]

def parse_pdf(pdf_path):
    start = time.time()
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            f"{API_URL}/file_parse",
            files={"files": (pdf_path, f, "application/pdf")},
        )
    elapsed = time.time() - start
    return {"file": pdf_path, "elapsed": elapsed, "status": resp.json().get("status")}

# 使用 5 个并发 worker 测试
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(parse_pdf, pdf) for pdf in PDF_FILES * 3]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]

times = [r["elapsed"] for r in results if r["status"] == "completed"]
print(f"平均: {statistics.mean(times):.2f}s")
print(f"吞吐量: {len(times) / sum(times):.2f} 文档/秒")
```
