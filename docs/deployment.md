# Deployment Guide

## Environment Specification

| Item | Value |
|------|-------|
| OS | Ubuntu 22.04.5 LTS |
| Kernel | 5.15.0-171-generic |
| CPU | AMD EPYC 9K65 192-Core (16 cores / 32 threads) |
| Memory | 92 GB DDR5 |
| GPU | NVIDIA RTX 5880 Ada Generation (46 GB VRAM) |
| NVIDIA Driver | 570.158.01 |
| CUDA Version | 12.8 |
| Disk | 493 GB SSD |
| Docker Engine | 29.5.2 |
| Docker Compose | v5.1.4 |
| Docker Buildx | v0.34.0 |

## Step 1: Install Docker Engine

```bash
# Add Docker official apt repository
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## Step 2: Install NVIDIA Container Toolkit

```bash
# Add NVIDIA repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

apt-get update
apt-get install -y nvidia-container-toolkit

# Configure Docker to use NVIDIA runtime
nvidia-ctk runtime configure --runtime=docker
```

## Step 3: Configure Docker Proxy (China Mainland)

If deploying from China mainland, configure proxy for faster downloads:

```bash
# Docker daemon proxy
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

# Docker client proxy
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

Restart Docker daemon:

```bash
# If using systemd
systemctl restart docker

# If running dockerd manually
pkill dockerd
dockerd &
```

## Step 4: Build MinerU Docker Image

### Prepare Files

```bash
mkdir -p /root/mineru/docker

# Download official Dockerfile
curl -o /root/mineru/docker/Dockerfile \
  https://gcore.jsdelivr.net/gh/opendatalab/MinerU@master/docker/global/Dockerfile

# Download official compose.yaml
curl -o /root/mineru/docker/compose.yaml \
  https://gcore.jsdelivr.net/gh/opendatalab/MinerU@master/docker/compose.yaml
```

### Dockerfile Content

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

### Build Command

```bash
# Set proxy environment variables
export http_proxy='http://127.0.0.1:1087'
export https_proxy='http://127.0.0.1:1087'

# Build with --network host for proxy passthrough
cd /root/mineru
docker build --network host --progress=plain \
  -t mineru:latest \
  -f docker/Dockerfile docker/
```

**Build time**: ~10-15 minutes with proxy, ~45+ minutes without proxy.

**Image size**: 18.3 GB

### Build Breakdown

| Step | Description | Time (with proxy) | Cacheable |
|------|-------------|-------------------|-----------|
| Base image pull | `vllm/vllm-openai:v0.11.2` | ~3 min | Yes |
| apt-get | Fonts + libgl | ~1 min | Yes |
| pip install | `mineru[core]>=3.0.0` (v3.1.15) | ~2 min | Yes |
| Model download | 8 pipeline + VLM models | ~8 min | Yes |

## Step 5: Deploy Service

### Using Docker Compose (Recommended)

```bash
cd /root/mineru

# Start API service (port 8000)
docker compose -f docker/compose.yaml --profile api up -d

# Or start OpenAI-compatible server (port 30000)
docker compose -f docker/compose.yaml --profile openai-server up -d

# Or start Gradio UI (port 7860)
docker compose -f docker/compose.yaml --profile gradio up -d

# Or start Router (port 8002)
docker compose -f docker/compose.yaml --profile router up -d
```

### Using Docker Run

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

## Step 6: Verify Deployment

```bash
# Check container status
docker ps

# Check health endpoint
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","version":"3.1.15","protocol_version":1,
#  "queued_tasks":0,"processing_tasks":0,"max_concurrent_requests":3}

# Test with a PDF
curl -X POST http://localhost:8000/file_parse \
  -F "files=@test.pdf"

# Access Swagger UI
# http://localhost:8000/docs
```

## Service Profiles

| Profile | Port | Entry Point | Description |
|---------|------|-------------|-------------|
| `api` | 8000 | `mineru-api` | RESTful API with sync/async parsing |
| `openai-server` | 30000 | `mineru-openai-server` | OpenAI-compatible API server |
| `router` | 8002 | `mineru-router` | Multi-GPU request router |
| `gradio` | 7860 | `mineru-gradio` | Web UI for interactive parsing |

## Configuration Options

### GPU Memory Utilization

If encountering VRAM shortage, reduce the KV cache size:

```yaml
# In compose.yaml, add to the command section:
command:
  --host 0.0.0.0
  --port 8000
  --gpu-memory-utilization 0.5  # Default is ~0.9
```

### Multi-GPU Support

Modify `device_ids` in compose.yaml:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          device_ids: ["0", "1"]  # Use GPU 0 and 1
          capabilities: [gpu]
```

### SSRF Protection

By default, when binding to `0.0.0.0`, MinerU disables `*-http-client` backends and `server_url` to prevent SSRF attacks. To enable them (only if the API is on a private network):

```yaml
command:
  --host 0.0.0.0
  --port 8000
  --allow-public-http-client
```
