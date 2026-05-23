# Architecture Design

## System Overview

MinerU is a document parsing service that converts PDF, images, DOCX, PPTX, and XLSX files into Markdown and structured JSON. This deployment uses the Docker containerized approach with vLLM as the inference backend for the VLM (Vision Language Model) component.

```
+-------------------+       +-------------------+       +-------------------+
|   Client / User   |------>|   MinerU API      |------>|   vLLM Engine     |
|                   |  HTTP |   (FastAPI)       |       |   (VLM Inference) |
|  curl / SDK / UI  |<------|   Port 8000       |<------|   GPU Accelerated |
+-------------------+       +-------------------+       +-------------------+
                                     |
                                     v
                            +-------------------+
                            |  Pipeline Models  |
                            |  (CPU/GPU hybrid) |
                            +-------------------+
```

## Core Components

### 1. MinerU API (FastAPI Service)

- **Framework**: FastAPI + Uvicorn
- **Port**: 8000
- **Entry Point**: `mineru-api`
- **Concurrency Model**: Async task queue with configurable max concurrent requests (default: 3)
- **Processing Window**: 64 slots for task management
- **Task Retention**: 86400s (24 hours)

The API exposes two parsing modes:

| Mode | Endpoint | Description |
|------|----------|-------------|
| Synchronous | `POST /file_parse` | Blocks until parsing completes, returns result directly |
| Asynchronous | `POST /tasks` | Returns task_id immediately, client polls for result |

### 2. vLLM Inference Engine

- **Version**: v0.11.2 (CUDA 12.9)
- **Model**: `opendatalab/MinerU2.5-Pro-2604-1.2B` (Qwen2VL architecture)
- **Compute Capability**: 8.9 (Ada Lovelace)
- **Features**: Chunked prefill, prefix caching, custom logits processors
- **Max Model Length**: 8192 tokens
- **Data Type**: bfloat16
- **GPU Memory**: ~23-25 GB VRAM

### 3. Pipeline Models (PDF-Extract-Kit-1.0)

| Model | Type | Path | Purpose |
|-------|------|------|---------|
| PP-DocLayoutV2 | Layout Detection | `models/Layout/PP-DocLayoutV2` | Page layout analysis |
| unimernet_hf_small_2503 | MFR (Math Formula Recognition) | `models/MFR/unimernet_hf_small_2503` | Formula extraction |
| pp_formulanet_plus_m | MFR | `models/MFR/pp_formulanet_plus_m` | Advanced formula recognition |
| paddleocr_torch | OCR | `models/OCR/paddleocr_torch` | Text recognition (22 files) |
| SlanetPlus | Table Recognition | `models/TabRec/SlanetPlus` | Table structure parsing |
| UnetStructure | Table Recognition | `models/TabRec/UnetStructure` | Table cell detection |
| PP-LCNet_table_cls | Table Classification | `models/TabCls/paddle_table_cls` | Table type classification |

### 4. Docker Infrastructure

```
+--------------------------------------------------+
|  Docker Container: mineru-api                     |
|                                                   |
|  +---------------------------------------------+ |
|  |  vLLM Engine (PID 1)                        | |
|  |    -> Qwen2VL 1.2B on GPU:0                 | |
|  +---------------------------------------------+ |
|  |  FastAPI Application                        | |
|  |    -> /file_parse (sync)                    | |
|  |    -> /tasks (async)                        | |
|  |    -> /health                               | |
|  |    -> /docs (Swagger UI)                    | |
|  +---------------------------------------------+ |
|  |  Pipeline Models (on-demand loading)        | |
|  |    -> Layout, OCR, MFR, TabRec, TabCls     | |
|  +---------------------------------------------+ |
|                                                   |
|  GPU: NVIDIA RTX 5880 Ada (device_ids: ["0"])    |
|  IPC: host  |  Memlock: unlimited                 |
+--------------------------------------------------+
```

## Parsing Backends

MinerU supports multiple parsing backends, selectable per request:

| Backend | Description | GPU Required | Languages |
|---------|-------------|-------------|-----------|
| `pipeline` | Traditional pipeline, hallucination-free | Optional | Multi-language |
| `vlm-auto-engine` | VLM via local GPU | Required | Chinese, English |
| `vlm-http-client` | VLM via remote server | No (client only) | Chinese, English |
| `hybrid-auto-engine` | Pipeline + VLM hybrid (default) | Required | Multi-language |
| `hybrid-http-client` | Hybrid via remote server | No (client only) | Multi-language |

**Default**: `hybrid-auto-engine` - combines the general pipeline with VLM for highest accuracy.

## Data Flow

```
1. Client uploads PDF via POST /file_parse or POST /tasks
         |
2. API receives file, creates async task
         |
3. Pipeline stage:
   a. Layout Detection (PP-DocLayoutV2) -> identify regions
   b. OCR (paddleocr_torch) -> extract text from regions
   c. Table Recognition (SlanetPlus/UnetStructure) -> parse tables
   d. Formula Recognition (unimernet/pp_formulanet) -> parse formulas
         |
4. VLM stage (hybrid backend):
   a. Image regions sent to Qwen2VL via vLLM
   b. Model generates structured descriptions
         |
5. Post-processing:
   a. Merge pipeline + VLM results
   b. Generate Markdown output
   c. Build content list and middle JSON
         |
6. Return result to client (sync) or store for polling (async)
```

## Resource Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| GPU VRAM | 24 GB | 46 GB (RTX 5880 Ada) |
| System RAM | 16 GB | 92 GB |
| Disk Space | 50 GB | 100 GB |
| CPU Cores | 8 | 16+ (AMD EPYC 9K65) |
| Docker | 24.0+ | 29.5+ |
| NVIDIA Driver | 535+ | 570.158+ |
| CUDA | 12.0+ | 12.8 |

## GPU Memory Allocation

| Component | VRAM Usage |
|-----------|-----------|
| vLLM Engine (Qwen2VL 1.2B) | ~23 GB |
| Pipeline Models (on-demand) | ~2-3 GB peak |
| KV Cache | Remaining (~20 GB) |
| **Total Available** | **46 GB** |
