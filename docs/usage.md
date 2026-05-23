# Usage Manual

## API Endpoints

### Health Check

```bash
curl http://localhost:8000/health
```

Response:
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

### Synchronous Parsing

Waits for the parsing to complete and returns the result in the same response.

```bash
curl -X POST http://localhost:8000/file_parse \
  -F "files=@document.pdf"
```

Response:
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
      "md_content": "# Parsed Content\n\n..."
    }
  }
}
```

### Asynchronous Parsing

Returns a task_id immediately; client polls for completion.

**Step 1 - Submit task:**

```bash
curl -X POST http://localhost:8000/tasks \
  -F "files=@document.pdf"
```

Response:
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

**Step 2 - Check status:**

```bash
curl http://localhost:8000/tasks/{task_id}
```

**Step 3 - Get result (when status is "completed"):**

```bash
curl http://localhost:8000/tasks/{task_id}/result
```

## Request Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `files` | file[] | **required** | PDF, image, DOCX, PPTX, or XLSX files |
| `backend` | string | `hybrid-auto-engine` | Parsing backend (see below) |
| `lang_list` | string[] | `["ch"]` | OCR language hints |
| `parse_method` | string | `auto` | `auto`, `txt`, or `ocr` |
| `formula_enable` | bool | `true` | Enable formula parsing |
| `table_enable` | bool | `true` | Enable table parsing |
| `image_analysis` | bool | `true` | Enable image/chart analysis (VLM/hybrid) |
| `return_md` | bool | `true` | Return markdown content |
| `return_middle_json` | bool | `false` | Return middle JSON |
| `return_model_output` | bool | `false` | Return model output JSON |
| `return_content_list` | bool | `false` | Return content list JSON |
| `return_images` | bool | `false` | Return extracted images |
| `response_format_zip` | bool | `false` | Return as ZIP instead of JSON |
| `start_page_id` | int | `0` | Starting page (0-indexed) |
| `end_page_id` | int | `99999` | Ending page (0-indexed) |

### Backend Options

| Backend | Description | GPU | Languages |
|---------|-------------|-----|-----------|
| `pipeline` | Traditional pipeline, hallucination-free | Optional | Multi-language |
| `vlm-auto-engine` | VLM via local GPU | Required | Chinese, English |
| `vlm-http-client` | VLM via remote server | No | Chinese, English |
| `hybrid-auto-engine` | Pipeline + VLM hybrid (**default**) | Required | Multi-language |
| `hybrid-http-client` | Hybrid via remote server | No | Multi-language |

### Language Options

Common `lang_list` values:

| Code | Languages |
|------|-----------|
| `ch` | Chinese, English, Chinese Traditional |
| `en` | English |
| `japan` | Chinese, English, Chinese Traditional, Japanese |
| `korean` | Korean, English |
| `latin` | French, German, Italian, Spanish, Portuguese, etc. |
| `arabic` | Arabic, Persian, Urdu, etc. |
| `cyrillic` | Russian, Ukrainian, Bulgarian, etc. |

## Usage Examples

### Parse with specific backend

```bash
# Pipeline-only (no GPU required, but slower)
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "backend=pipeline"

# VLM auto engine (GPU required)
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "backend=vlm-auto-engine"
```

### Parse specific pages

```bash
# Parse pages 0-5 only
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "start_page_id=0" \
  -F "end_page_id=5"
```

### Parse with language hint

```bash
# For English documents
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "lang_list=en"

# For Japanese documents
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "lang_list=japan"
```

### Disable formula/table parsing

```bash
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "formula_enable=false" \
  -F "table_enable=false"
```

### Get all output formats

```bash
curl -X POST http://localhost:8000/file_parse \
  -F "files=@doc.pdf" \
  -F "return_md=true" \
  -F "return_middle_json=true" \
  -F "return_content_list=true" \
  -F "return_images=true" \
  -F "response_format_zip=true"
```

### Python client example

```python
import requests

API_URL = "http://localhost:8000"

# Synchronous parsing
with open("document.pdf", "rb") as f:
    response = requests.post(
        f"{API_URL}/file_parse",
        files={"files": ("document.pdf", f, "application/pdf")},
        data={"backend": "hybrid-auto-engine", "lang_list": ["ch"]},
    )
    result = response.json()
    print(result["results"]["document"]["md_content"])

# Asynchronous parsing
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
        print("Parsing failed:", status.get("error"))
        break
    time.sleep(2)
```

## Stress Testing

### Sequential Latency Test

```bash
#!/bin/bash
# Measure per-file parsing latency sequentially
for pdf in pdf/*.pdf; do
    start=$(date +%s%N)
    curl -s -X POST http://localhost:8000/file_parse -F "files=@$pdf" > /dev/null
    end=$(date +%s%N)
    elapsed=$(( (end - start) / 1000000 ))
    echo "$(basename $pdf): ${elapsed}ms"
done
```

### Concurrent Throughput Test

```bash
#!/bin/bash
# Submit all PDFs at once and measure total throughput
TASK_IDS=()
for pdf in pdf/*.pdf; do
    resp=$(curl -s -X POST http://localhost:8000/tasks -F "files=@$pdf")
    tid=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
    TASK_IDS+=("$tid")
done

# Poll until all complete
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

### Python Stress Test Script

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

# Concurrent test with 5 workers
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(parse_pdf, pdf) for pdf in PDF_FILES * 3]
    results = [f.result() for f in concurrent.futures.as_completed(futures)]

times = [r["elapsed"] for r in results if r["status"] == "completed"]
print(f"Avg: {statistics.mean(times):.2f}s")
print(f"Throughput: {len(times) / sum(times):.2f} docs/s")
```
