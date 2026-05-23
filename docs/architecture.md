# 架构设计

## 系统概述

MinerU 是一个文档解析服务，可将 PDF、图片、DOCX、PPTX 和 XLSX 文件转换为 Markdown 和结构化 JSON。本部署采用 Docker 容器化方案，使用 vLLM 作为 VLM（视觉语言模型）组件的推理后端。

```
+-------------------+       +-------------------+       +-------------------+
|   客户端 / 用户    |------>|   MinerU API      |------>|   vLLM 引擎       |
|                   |  HTTP |   (FastAPI)       |       |   (VLM 推理)      |
|  curl / SDK / UI  |<------|   端口 8000       |<------|   GPU 加速        |
+-------------------+       +-------------------+       +-------------------+
                                     |
                                     v
                            +-------------------+
                            |  Pipeline 模型    |
                            |  (CPU/GPU 混合)   |
                            +-------------------+
```

## 核心组件

### 1. MinerU API（FastAPI 服务）

- **框架**：FastAPI + Uvicorn
- **端口**：8000
- **入口命令**：`mineru-api`
- **并发模型**：异步任务队列，最大并发请求数可配置（默认：3）
- **处理窗口**：64 个任务管理槽位
- **任务保留时间**：86400 秒（24 小时）

API 提供两种解析模式：

| 模式 | 端点 | 说明 |
|------|------|------|
| 同步 | `POST /file_parse` | 阻塞等待解析完成，直接返回结果 |
| 异步 | `POST /tasks` | 立即返回 task_id，客户端轮询获取结果 |

### 2. vLLM 推理引擎

- **版本**：v0.11.2 (CUDA 12.9)
- **模型**：`opendatalab/MinerU2.5-Pro-2604-1.2B`（Qwen2VL 架构）
- **计算能力**：8.9（Ada Lovelace）
- **特性**：分块预填充、前缀缓存、自定义 logits 处理器
- **最大模型长度**：8192 tokens
- **数据类型**：bfloat16
- **GPU 显存**：约 23-25 GB

### 3. Pipeline 模型（PDF-Extract-Kit-1.0）

| 模型 | 类型 | 路径 | 用途 |
|------|------|------|------|
| PP-DocLayoutV2 | 版面检测 | `models/Layout/PP-DocLayoutV2` | 页面版面分析 |
| unimernet_hf_small_2503 | MFR（数学公式识别） | `models/MFR/unimernet_hf_small_2503` | 公式提取 |
| pp_formulanet_plus_m | MFR | `models/MFR/pp_formulanet_plus_m` | 高级公式识别 |
| paddleocr_torch | OCR | `models/OCR/paddleocr_torch` | 文字识别（22 个文件） |
| SlanetPlus | 表格识别 | `models/TabRec/SlanetPlus` | 表格结构解析 |
| UnetStructure | 表格识别 | `models/TabRec/UnetStructure` | 表格单元格检测 |
| PP-LCNet_table_cls | 表格分类 | `models/TabCls/paddle_table_cls` | 表格类型分类 |

### 4. Docker 基础设施

```
+--------------------------------------------------+
|  Docker 容器: mineru-api                          |
|                                                   |
|  +---------------------------------------------+ |
|  |  vLLM 引擎 (PID 1)                          | |
|  |    -> Qwen2VL 1.2B on GPU:0                 | |
|  +---------------------------------------------+ |
|  |  FastAPI 应用                                | |
|  |    -> /file_parse (同步)                     | |
|  |    -> /tasks (异步)                          | |
|  |    -> /health                                | |
|  |    -> /docs (Swagger UI)                     | |
|  +---------------------------------------------+ |
|  |  Pipeline 模型（按需加载）                    | |
|  |    -> Layout, OCR, MFR, TabRec, TabCls      | |
|  +---------------------------------------------+ |
|                                                   |
|  GPU: NVIDIA RTX 5880 Ada (device_ids: ["0"])    |
|  IPC: host  |  Memlock: 无限制                    |
+--------------------------------------------------+
```

## 解析后端

MinerU 支持多种解析后端，可按请求选择：

| 后端 | 说明 | 是否需要 GPU | 支持语言 |
|------|------|-------------|---------|
| `pipeline` | 传统流水线，无幻觉 | 可选 | 多语言 |
| `vlm-auto-engine` | 通过本地 GPU 运行 VLM | 需要 | 中英文 |
| `vlm-http-client` | 通过远程服务器运行 VLM | 不需要（仅客户端） | 中英文 |
| `hybrid-auto-engine` | Pipeline + VLM 混合（默认） | 需要 | 多语言 |
| `hybrid-http-client` | 通过远程服务器运行混合模式 | 不需要（仅客户端） | 多语言 |

**默认**：`hybrid-auto-engine` — 结合通用流水线与 VLM，实现最高精度。

## 数据流

```
1. 客户端通过 POST /file_parse 或 POST /tasks 上传 PDF
         |
2. API 接收文件，创建异步任务
         |
3. Pipeline 阶段：
   a. 版面检测 (PP-DocLayoutV2) -> 识别区域
   b. OCR (paddleocr_torch) -> 从区域提取文字
   c. 表格识别 (SlanetPlus/UnetStructure) -> 解析表格
   d. 公式识别 (unimernet/pp_formulanet) -> 解析公式
         |
4. VLM 阶段（混合后端）：
   a. 图片区域通过 vLLM 发送给 Qwen2VL
   b. 模型生成结构化描述
         |
5. 后处理：
   a. 合并 Pipeline + VLM 结果
   b. 生成 Markdown 输出
   c. 构建内容列表和中间 JSON
         |
6. 返回结果给客户端（同步）或存储待轮询（异步）
```

## 资源需求

| 资源 | 最低要求 | 推荐配置 |
|------|---------|---------|
| GPU 显存 | 24 GB | 46 GB (RTX 5880 Ada) |
| 系统内存 | 16 GB | 92 GB |
| 磁盘空间 | 50 GB | 100 GB |
| CPU 核心数 | 8 | 16+ (AMD EPYC 9K65) |
| Docker | 24.0+ | 29.5+ |
| NVIDIA 驱动 | 535+ | 570.158+ |
| CUDA | 12.0+ | 12.8 |

## GPU 显存分配

| 组件 | 显存占用 |
|------|---------|
| vLLM 引擎 (Qwen2VL 1.2B) | 约 23 GB |
| Pipeline 模型（按需加载） | 约 2-3 GB 峰值 |
| KV Cache | 剩余部分（约 20 GB） |
| **总可用显存** | **46 GB** |
