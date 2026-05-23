# 部署指南

## 环境规格

| 项目 | 值 |
|------|-----|
| 操作系统 | Ubuntu 22.04.5 LTS |
| 内核 | 5.15.0-171-generic |
| CPU | AMD EPYC 9K65 192-Core（16 核 / 32 线程） |
| 内存 | 92 GB DDR5 |
| GPU | NVIDIA RTX 5880 Ada Generation（46 GB 显存） |
| NVIDIA 驱动 | 570.158.01 |
| CUDA 版本 | 12.8 |
| 磁盘 | 493 GB SSD |
| Docker Engine | 29.5.2 |
| Docker Compose | v5.1.4 |
| Docker Buildx | v0.34.0 |

## 第一步：安装 Docker Engine

```bash
# 添加 Docker 官方 apt 仓库
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## 第二步：安装 NVIDIA Container Toolkit

```bash
# 添加 NVIDIA 仓库
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

apt-get update
apt-get install -y nvidia-container-toolkit

# 配置 Docker 使用 NVIDIA 运行时
nvidia-ctk runtime configure --runtime=docker
```

## 第三步：配置 Docker 代理（中国大陆）

在中国大陆部署时，需配置代理以加速下载：

```bash
# Docker 守护进程代理
cat > /etc/docker/daemon.json << 'EOF'
{
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "nvidia-container-runtime"
        }
    },
    "proxies": {
        "http-proxy": "http://127.0.0.1:1087",
        "https-proxy": "http://127.0.0.1:1087",
        "no-proxy": "localhost,127.0.0.1"
    }
}
EOF

# Docker 客户端代理
mkdir -p ~/.docker
cat > ~/.docker/config.json << 'EOF'
{
    "proxies": {
        "default": {
            "httpProxy": "http://127.0.0.1:1087",
            "httpsProxy": "http://127.0.0.1:1087",
            "noProxy": "localhost,127.0.0.1"
        }
    }
}
EOF
```

重启 Docker 守护进程：

```bash
# 使用 systemd 时
systemctl restart docker

# 手动运行 dockerd 时
pkill dockerd
dockerd &
```

## 第四步：构建 MinerU Docker 镜像

### 准备文件

```bash
mkdir -p /root/mineru/docker

# 下载官方 Dockerfile
curl -o /root/mineru/docker/Dockerfile \
  https://gcore.jsdelivr.net/gh/opendatalab/MinerU@master/docker/global/Dockerfile

# 下载官方 compose.yaml
curl -o /root/mineru/docker/compose.yaml \
  https://gcore.jsdelivr.net/gh/opendatalab/MinerU@master/docker/compose.yaml
```

### Dockerfile 内容

```dockerfile
FROM vllm/vllm-openai:v0.11.2

RUN apt-get update && \
    apt-get install -y \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig \
        libgl1 && \
    fc-cache -fv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install -U 'mineru[core]>=3.0.0' --break-system-packages && \
    python3 -m pip cache purge

RUN /bin/bash -c "mineru-models-download -s huggingface -m all"

ENTRYPOINT ["/bin/bash", "-c", "export MINERU_MODEL_SOURCE=local && exec \"$@\"", "--"]
```

### 构建命令

```bash
# 设置代理环境变量
export http_proxy='http://127.0.0.1:1087'
export https_proxy='http://127.0.0.1:1087'

# 使用 --network host 传递代理
cd /root/mineru
docker build --network host --progress=plain \
  -t mineru:latest \
  -f docker/Dockerfile docker/
```

**构建时间**：使用代理约 10-15 分钟，不使用代理约 45+ 分钟。

**镜像大小**：18.3 GB

### 构建步骤分解

| 步骤 | 说明 | 耗时（使用代理） | 可缓存 |
|------|------|-----------------|--------|
| 基础镜像拉取 | `vllm/vllm-openai:v0.11.2` | 约 3 分钟 | 是 |
| apt-get | 字体 + libgl | 约 1 分钟 | 是 |
| pip install | `mineru[core]>=3.0.0`（v3.1.15） | 约 2 分钟 | 是 |
| 模型下载 | 8 个 pipeline + VLM 模型 | 约 8 分钟 | 是 |

## 第五步：部署服务

### 使用 Docker Compose（推荐）

```bash
cd /root/mineru

# 启动 API 服务（端口 8000）
docker compose -f docker/compose.yaml --profile api up -d

# 或启动 OpenAI 兼容服务（端口 30000）
docker compose -f docker/compose.yaml --profile openai-server up -d

# 或启动 Gradio UI（端口 7860）
docker compose -f docker/compose.yaml --profile gradio up -d

# 或启动 Router（端口 8002）
docker compose -f docker/compose.yaml --profile router up -d
```

### 使用 Docker Run

```bash
docker run -d \
  --name mineru-api \
  --gpus '"device=0"' \
  --ipc host \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -p 8000:8000 \
  -e MINERU_MODEL_SOURCE=local \
  mineru:latest \
  mineru-api --host 0.0.0.0 --port 8000
```

## 第六步：验证部署

```bash
# 检查容器状态
docker ps

# 检查健康端点
curl http://localhost:8000/health

# 预期响应：
# {"status":"healthy","version":"3.1.15","protocol_version":1,
#  "queued_tasks":0,"processing_tasks":0,"max_concurrent_requests":3}

# 使用 PDF 测试
curl -X POST http://localhost:8000/file_parse \
  -F "files=@test.pdf"

# 访问 Swagger UI
# http://localhost:8000/docs
```

## 服务配置文件

| Profile | 端口 | 入口命令 | 说明 |
|---------|------|---------|------|
| `api` | 8000 | `mineru-api` | RESTful API，支持同步/异步解析 |
| `openai-server` | 30000 | `mineru-openai-server` | OpenAI 兼容 API 服务 |
| `router` | 8002 | `mineru-router` | 多 GPU 请求路由器 |
| `gradio` | 7860 | `mineru-gradio` | Web 交互式解析界面 |

## 配置选项

### GPU 显存利用率

如遇显存不足，可降低 KV Cache 大小：

```yaml
# 在 compose.yaml 的 command 部分添加：
command:
  --host 0.0.0.0
  --port 8000
  --gpu-memory-utilization 0.5  # 默认约 0.9
```

### 多 GPU 支持

修改 compose.yaml 中的 `device_ids`：

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          device_ids: ["0", "1"]  # 使用 GPU 0 和 1
          capabilities: [gpu]
```

### SSRF 防护

默认情况下，绑定到 `0.0.0.0` 时 MinerU 会禁用 `*-http-client` 后端和 `server_url` 以防止 SSRF 攻击。如需启用（仅在私有网络中）：

```yaml
command:
  --host 0.0.0.0
  --port 8000
  --allow-public-http-client
```
