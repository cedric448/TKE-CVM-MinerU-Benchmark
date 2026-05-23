# TKE-CVM-MinerU-Benchmark

MinerU PDF parsing service benchmark on NVIDIA RTX 5880 Ada GPU (Tencent Cloud CVM & TKE).

## Quick Results

| Metric | Local Docker | TKE (CLB) |
|--------|-------------|-----------|
| Throughput | **18.1 files/min** | **14.82 files/min** |
| Avg time per file | 3.32s | 4.05s |
| GPU Utilization | 68.8% avg | 68.8% avg |
| Success rate | 100% | 100% |
| TKE overhead | - | +22% latency |

| Metric | Sequential | Concurrent (19 PDFs) |
|--------|-----------|---------------------|
| Avg latency | **8.68s / doc** | - |
| Total wall time | 164.95s | **73.62s** |
| Throughput | 0.115 docs/s | **0.258 docs/s** |
| Speedup | 1x | **2.24x** |

## Test Environment

- **GPU**: NVIDIA RTX 5880 Ada (46 GB VRAM)
- **CPU**: AMD EPYC 9K65 (16C/32T)
- **RAM**: 92 GB
- **OS**: Ubuntu 22.04.5 LTS
- **MinerU**: 3.1.15 (Docker, vLLM 0.11.2)
- **VLM**: MinerU2.5-Pro-2604-1.2B (Qwen2VL)
- **Deployment**: CVM (local Docker) + TKE (K8s + CLB)

## Project Structure

```
.
├── docker/
│   ├── Dockerfile              # MinerU Docker image definition
│   └── compose.yaml            # Docker Compose service profiles
├── k8s/
│   ├── mineru-deploy.yaml      # TKE Kubernetes deployment
│   └── mineru-ingress.yaml     # TKE ingress / CLB config
├── pdf/                        # Test PDF documents (22 files, CVPR papers)
├── output/                     # Local benchmark results
│   ├── batch_summary.json      # Batch inference results
│   ├── stress_test_summary.json # Stress test results
│   └── gpu_metrics_summary.json # DCGM GPU metrics
├── output_tke/                 # TKE benchmark results
│   └── stress_test_summary.json
├── output_local/               # Local CLI stress test results
├── monitor/                    # DCGM monitoring screenshots
├── docs/
│   ├── architecture.md         # System architecture design
│   ├── deployment.md           # Deployment guide
│   ├── usage.md                # API usage manual
│   ├── benchmark-report.md     # Full benchmark report & comparison
│   └── troubleshooting.md      # Issues & solutions
├── batch_inference.py          # Batch inference script
├── stress_test.py              # API stress test script
├── gpu_monitor.py              # GPU metrics collector
├── dcgm_monitor.sh             # DCGM monitoring script
├── batch_stress_test_local.sh  # Local stress test runner
├── batch_stress_test_tke.sh    # TKE stress test runner
├── batch_stress_test_10r.sh    # 10-round stress test runner
└── README.md
```

## Quick Start

```bash
# 1. Build Docker image
docker build --network host --progress=plain \
  -t mineru:latest -f docker/Dockerfile docker/

# 2. Start API service
docker compose -f docker/compose.yaml --profile api up -d

# 3. Test
curl http://localhost:8000/health
curl -X POST http://localhost:8000/file_parse -F "files=@pdf/test.pdf"
```

## Stress Testing

```bash
# Run batch inference on all PDFs
python3 batch_inference.py

# Run stress test (3 rounds, 22 PDFs/round)
python3 stress_test.py

# Run with GPU monitoring
bash dcgm_monitor.sh &
python3 stress_test.py

# TKE stress test (via CLB)
bash batch_stress_test_tke.sh

# Local stress test
bash batch_stress_test_local.sh
```

## Documentation

- [Architecture Design](docs/architecture.md) - System components, data flow, resource requirements
- [Deployment Guide](docs/deployment.md) - Step-by-step setup instructions
- [Usage Manual](docs/usage.md) - API reference, examples, stress testing scripts
- [Benchmark Report](docs/benchmark-report.md) - Full performance data, local vs TKE comparison
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions

## License

This benchmark project is for reference purposes. MinerU itself is licensed under [MinerU Open Source License](https://github.com/opendatalab/MinerU).
