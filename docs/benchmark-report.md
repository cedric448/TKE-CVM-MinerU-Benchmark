# Benchmark Performance Report

## Test Environment

| Item | Value |
|------|-------|
| **Machine** | CVM (Tencent Cloud Virtual Machine) |
| **OS** | Ubuntu 22.04.5 LTS |
| **Kernel** | 5.15.0-171-generic |
| **CPU** | AMD EPYC 9K65 192-Core (16 cores / 32 threads) |
| **Memory** | 92 GB DDR5 |
| **GPU** | NVIDIA RTX 5880 Ada Generation |
| **GPU VRAM** | 46,068 MiB |
| **NVIDIA Driver** | 570.158.01 |
| **CUDA** | 12.8 |
| **Disk** | 493 GB SSD |
| **Docker** | 29.5.2 |
| **MinerU** | 3.1.15 |
| **vLLM** | 0.11.2+cu129 |
| **VLM Model** | MinerU2.5-Pro-2604-1.2B (Qwen2VL) |
| **Parsing Backend** | hybrid-auto-engine (default) |

## Test Methodology

### Test Dataset

19 unique PDF documents from `pdf/` directory, primarily CVPR 2020 academic papers:

| Size Category | Count | Size Range |
|---------------|-------|------------|
| Small (<2 MB) | 8 | 631 KB - 1.9 MB |
| Medium (2-5 MB) | 7 | 2.0 MB - 4.8 MB |
| Large (>5 MB) | 4 | 5.3 MB - 9.8 MB |

### Test Scenarios

1. **Sequential Single-Request Latency**: Send one request at a time, measure per-file latency
2. **Concurrent Async Throughput**: Submit all 19 PDFs simultaneously via async API, measure total throughput
3. **GPU Utilization**: Monitor VRAM usage, GPU compute utilization, and power draw

### Test Procedure

1. Start the MinerU API container (`mineru-api`, profile `api`)
2. Send one warmup request to trigger lazy model loading
3. Run sequential benchmark: parse each PDF one at a time via `POST /file_parse`
4. Run concurrent benchmark: submit all PDFs via `POST /tasks` simultaneously, poll until completion
5. Record GPU metrics via `nvidia-smi`

## Performance Results

### 1. Sequential Single-Request Latency

| Metric | Value |
|--------|-------|
| Total files | 19 |
| Total time | 164.95s |
| **Average** | **8.68s** |
| **Median** | **8.32s** |
| Min | 6.26s |
| Max | 11.63s |

#### Per-File Results

| # | File | Size | Latency | MD Length | Status |
|---|------|------|---------|-----------|--------|
| 1 | 2001.00309v3.pdf | 4,837 KB | 6.26s | 55,408 | completed |
| 2 | 2002.10187v1.pdf | 1,945 KB | 10.80s | 53,736 | completed |
| 3 | 2003.07540v1.pdf | 3,148 KB | 9.02s | 57,705 | completed |
| 4 | 2003.09163v2.pdf | 4,795 KB | 7.59s | 57,320 | completed |
| 5 | 2004.01547v1.pdf | 8,723 KB | 7.63s | 57,844 | completed |
| 6 | 2006.04356v1.pdf | 9,792 KB | 7.49s | 54,200 | completed |
| 7 | Cao_D2Det...pdf | 1,854 KB | 9.02s | 60,507 | completed |
| 8 | Chibane_Implicit...pdf | 1,408 KB | 7.93s | 61,010 | completed |
| 9 | Guo_AugFPN...pdf | 631 KB | 10.71s | 54,515 | completed |
| 10 | He_PVN3D...pdf | 1,938 KB | 10.52s | 61,124 | completed |
| 11 | MSeg.pdf | 5,346 KB | 11.63s | 52,830 | completed |
| 12 | Mir_Texture...pdf | 3,673 KB | 8.32s | 54,557 | completed |
| 13 | Niemeyer2020CVPR.pdf | 7,011 KB | 9.35s | 63,560 | completed |
| 14 | Patel_TailorNet...pdf | 3,023 KB | 7.91s | 53,239 | completed |
| 15 | Peng_IDA-3D...pdf | 1,452 KB | 7.17s | 47,241 | completed |
| 16 | Wang_BiFuse...pdf | 1,131 KB | 8.63s | 44,944 | completed |
| 17 | Wang_ContourNet...pdf | 977 KB | 7.44s | 54,559 | completed |
| 18 | Zhang_Interactive...pdf | 2,917 KB | 7.80s | 56,921 | completed |
| 19 | siamrcnn.pdf | 3,473 KB | 9.73s | 68,408 | completed |

#### Latency by File Size

| Size Category | Count | Avg Latency | Min | Max |
|---------------|-------|-------------|-----|-----|
| <2 MB | 8 | 9.03s | 7.17s | 10.80s |
| 2-5 MB | 7 | 8.09s | 6.26s | 9.73s |
| >5 MB | 4 | 9.03s | 7.49s | 11.63s |

**Observation**: Latency is relatively consistent across file sizes (6-12s). The hybrid-auto-engine backend processes each page through both pipeline and VLM stages, so page count and content complexity matter more than file size.

### 2. Concurrent Async Throughput

| Metric | Value |
|--------|-------|
| Total submitted | 19 |
| **Completed** | **19/19 (100%)** |
| Failed | 0 |
| Timeout | 0 |
| Submit time | 0.59s |
| **Total wall time** | **73.62s** |
| Avg completion time | 39.11s |
| **Throughput** | **0.258 docs/s** |

#### Sequential vs Concurrent Comparison

| Mode | Total Time | Avg Per-Doc | Throughput |
|------|-----------|-------------|------------|
| Sequential (1 by 1) | 164.95s | 8.68s | 0.115 docs/s |
| Concurrent (19 at once) | 73.62s | 39.11s* | 0.258 docs/s |

*Note: Avg completion time in concurrent mode measures from submit to completion, including queue wait time. The actual processing time per document is similar to sequential, but parallelism allows overlapping.*

**Concurrent speedup**: 2.24x (73.62s vs 164.95s for the same 19 documents)

### 3. GPU Utilization

| Metric | Idle | Under Load |
|--------|------|------------|
| VRAM Used | 0 MiB | 25,370 - 25,552 MiB |
| VRAM Total | 46,068 MiB | 46,068 MiB |
| VRAM Utilization | 0% | ~55% |
| GPU Compute | 0% | Variable (spikes during inference) |
| Power Draw | 9W | 65-71W |
| Power Limit | 285W | 285W |

**Key observations**:
- The vLLM engine allocates ~23 GB VRAM at startup for the Qwen2VL model
- Pipeline models add ~2-3 GB peak when loaded on-demand
- Total VRAM usage stays at ~55% (25 GB / 46 GB), leaving headroom for larger batch sizes
- GPU compute utilization is bursty (spikes during VLM inference, idle during I/O)
- Power consumption is moderate (65-71W vs 285W max), indicating the workload is not fully compute-bound

### 4. Cold Start vs Warm Latency

Using a 2.2 MB PDF (Attention Is All You Need):

| Metric | Cold Start | Warm (avg of 3) |
|--------|-----------|-----------------|
| Latency | 14.96s | 6.46s |
| Stdev | - | 0.05s |

**Cold start overhead**: ~8.5s for model loading and CUDA graph compilation on first request.

## Performance Summary

| Metric | Value |
|--------|-------|
| **Avg sequential latency** | **8.68s / doc** |
| **Concurrent throughput** | **0.258 docs/s** |
| **Max concurrent requests** | 3 |
| **Cold start latency** | ~15s |
| **Warm latency** | ~6.5s |
| **GPU VRAM usage** | ~55% (25/46 GB) |
| **Success rate** | 100% (19/19) |

## Bottleneck Analysis

1. **vLLM Inference**: The VLM (Qwen2VL 1.2B) inference is the primary latency contributor. Each page requires a forward pass through the model.

2. **Max Concurrent = 3**: The default concurrency limit of 3 prevents overload but caps throughput. Increasing `max_concurrent_requests` could improve throughput if VRAM allows.

3. **I/O Bound**: Pipeline models (OCR, layout) involve CPU+GPU operations with significant I/O, creating bursty GPU utilization.

4. **File Size vs Latency**: Weak correlation (r ≈ 0.1). Content complexity (page count, number of images/tables) is a stronger predictor than raw file size.

## Local vs TKE Deployment Comparison

The same MinerU service was also deployed on TKE (Tencent Kubernetes Engine) with an internal CLB (Classic Load Balancer). The TKE deployment uses the same GPU and Docker image but adds a network layer (Kubernetes service + CLB).

### TKE Stress Test Results (3 rounds, 22 PDFs, via CLB)

| Metric | Value |
|--------|-------|
| API Endpoint | `http://172.21.128.65` (Internal CLB) |
| Total tasks | 66 (3 rounds x 22 PDFs) |
| **Completed** | **66/66 (100%)** |
| Failed | 0 |
| Overall time | 267.2s |
| **Avg time per file** | **4.05s** |
| **Throughput** | **14.82 files/min** |

### Local Stress Test Results (3 rounds, 22 PDFs, direct Docker)

| Metric | Value |
|--------|-------|
| API Endpoint | `http://localhost:8000` |
| Total tasks | 66 (3 rounds x 22 PDFs) |
| **Completed** | **66/66 (100%)** |
| Failed | 0 |
| Overall time | 218.8s |
| **Avg time per file** | **3.32s** |
| **Throughput** | **18.1 files/min** |

### GPU Metrics (Local, DCGM monitoring during stress test)

| Metric | Avg | Min | Max |
|--------|-----|-----|-----|
| GPU Utilization | 68.8% | 0% | 100% |
| Memory Utilization | 50.2% | 0% | 70% |
| Memory Used | 22,937 MB | 22,935 MB | 22,937 MB |
| Power Draw | 212.6W | 9.4W | 247.6W |
| Temperature | 61.3°C | - | 72.0°C |

### Local vs TKE Comparison

| Metric | Local (Docker) | TKE (CLB) | Delta |
|--------|---------------|-----------|-------|
| Overall time | 218.8s | 267.2s | +22.1% |
| Avg time per file | 3.32s | 4.05s | +22.0% |
| Throughput (files/min) | 18.1 | 14.82 | -18.1% |
| Success rate | 100% | 100% | 0% |

**Key finding**: TKE deployment via CLB adds ~22% latency overhead compared to local Docker access. This overhead comes from the additional network hops through Kubernetes service mesh and CLB. For latency-sensitive workloads, consider using pod-level access or hostNetwork.

## Monitoring Screenshots

DCGM monitoring dashboards captured during stress testing are available in `monitor/`:

- `ScreenShot_2026-05-23_102027_775.png` - GPU utilization overview
- `ScreenShot_2026-05-23_102149_527.png` - Memory and power metrics
- `ScreenShot_2026-05-23_102529_916.png` - Temperature and clock speed

## Optimization Recommendations

1. **Increase concurrency**: Raise `max_concurrent_requests` from 3 to 5-8, as VRAM headroom exists (~20 GB free)
2. **Use `pipeline` backend for text-heavy PDFs**: Skip VLM inference when high-accuracy VLM output is not needed
3. **Pre-warm the service**: Send a warmup request after deployment to eliminate cold start
4. **Batch processing**: Use the async API for bulk processing to maximize throughput
5. **GPU memory tuning**: If increasing concurrency, monitor VRAM and adjust `--gpu-memory-utilization` accordingly
6. **TKE network optimization**: For TKE deployment, use hostNetwork or pod-level access to reduce CLB latency overhead
