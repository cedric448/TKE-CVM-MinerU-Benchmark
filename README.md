# TKE-CVM-MinerU-Benchmark

MinerU PDF 解析服务在 NVIDIA RTX 5880 Ada GPU（腾讯云 CVM & TKE）上的性能基准测试。

## 核心结果

| 指标 | 本地 Docker | TKE（CLB） |
|------|-------------|-----------|
| 吞吐量 | **18.1 文件/分钟** | **14.82 文件/分钟** |
| 平均每文件耗时 | 3.32s | 4.05s |
| GPU 利用率 | 68.8% 平均 | 68.8% 平均 |
| 成功率 | 100% | 100% |
| TKE 额外开销 | - | +22% 延迟 |

| 指标 | 顺序 | 并发（19 个 PDF） |
|------|------|-----------------|
| 平均延迟 | **8.68 秒/文档** | - |
| 总挂钟时间 | 164.95s | **73.62s** |
| 吞吐量 | 0.115 文档/秒 | **0.258 文档/秒** |
| 加速比 | 1x | **2.24x** |

## 测试环境

- **GPU**：NVIDIA RTX 5880 Ada（46 GB 显存）
- **CPU**：AMD EPYC 9K65（16 核/32 线程）
- **内存**：92 GB
- **操作系统**：Ubuntu 22.04.5 LTS
- **MinerU**：3.1.15（Docker，vLLM 0.11.2）
- **VLM**：MinerU2.5-Pro-2604-1.2B（Qwen2VL）
- **部署方式**：CVM（本地 Docker）+ TKE（K8s + CLB）

## 项目结构

```
.
├── docker/
│   ├── Dockerfile              # MinerU Docker 镜像定义
│   └── compose.yaml            # Docker Compose 服务配置
├── k8s/
│   ├── mineru-deploy.yaml      # TKE Kubernetes 部署
│   └── mineru-ingress.yaml     # TKE Ingress / CLB 配置
├── pdf/                        # 测试 PDF 文档（22 个文件，CVPR 论文）
├── output/                     # 本地基准测试结果
│   ├── batch_summary.json      # 批量推理结果
│   ├── stress_test_summary.json # 压力测试结果
│   └── gpu_metrics_summary.json # DCGM GPU 指标
├── output_tke/                 # TKE 基准测试结果
│   └── stress_test_summary.json
├── output_local/               # 本地 CLI 压力测试结果
├── monitor/                    # DCGM 监控截图
├── docs/
│   ├── architecture.md         # 系统架构设计
│   ├── deployment.md           # 部署指南
│   ├── usage.md                # API 使用手册
│   ├── benchmark-report.md     # 完整性能报告与对比
│   └── troubleshooting.md      # 问题与解决方案
├── batch_inference.py          # 批量推理脚本
├── stress_test.py              # API 压力测试脚本
├── gpu_monitor.py              # GPU 指标采集脚本
├── dcgm_monitor.sh             # DCGM 监控脚本
├── batch_stress_test_local.sh  # 本地压力测试运行器
├── batch_stress_test_tke.sh    # TKE 压力测试运行器
├── batch_stress_test_10r.sh    # 10 轮压力测试运行器
└── README.md
```

## 快速开始

```bash
# 1. 构建 Docker 镜像
docker build --network host --progress=plain \
  -t mineru:latest -f docker/Dockerfile docker/

# 2. 启动 API 服务
docker compose -f docker/compose.yaml --profile api up -d

# 3. 测试
curl http://localhost:8000/health
curl -X POST http://localhost:8000/file_parse -F "files=@pdf/test.pdf"
```

## 压力测试

```bash
# 对所有 PDF 运行批量推理
python3 batch_inference.py

# 运行压力测试（3 轮，每轮 22 个 PDF）
python3 stress_test.py

# 搭配 GPU 监控运行
bash dcgm_monitor.sh &
python3 stress_test.py

# TKE 压力测试（通过 CLB）
bash batch_stress_test_tke.sh

# 本地压力测试
bash batch_stress_test_local.sh
```

## 文档

- [架构设计](docs/architecture.md) - 系统组件、数据流、资源需求
- [部署指南](docs/deployment.md) - 逐步搭建说明
- [使用手册](docs/usage.md) - API 参考、示例、压力测试脚本
- [性能报告](docs/benchmark-report.md) - 完整性能数据、本地 vs TKE 对比
- [故障排除](docs/troubleshooting.md) - 常见问题与解决方案

## 许可证

本基准测试项目仅供参考。MinerU 本身使用 [MinerU Open Source License](https://github.com/opendatalab/MinerU) 许可。
