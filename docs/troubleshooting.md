# 故障排除

本文档记录了部署过程中遇到的所有问题及解决方案。

## 1. Docker Engine 未安装

**现象**：`docker: command not found`

**解决方案**：从官方仓库安装 Docker CE：

```bash
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

如果 `dockerd` 未自动启动（非 systemd 环境）：

```bash
dockerd &
```

---

## 2. NVIDIA Container Toolkit 缺失

**现象**：
```
Error response from daemon: could not select device driver "nvidia" with capabilities: [[gpu]]
```

**原因**：Docker 访问 GPU 需要 NVIDIA Container Toolkit。NVIDIA 驱动（570.158.01）已安装，但容器运行时未安装。

**解决方案**：

```bash
# 添加 NVIDIA 仓库
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 安装
apt-get update
apt-get install -y nvidia-container-toolkit

# 配置 Docker
nvidia-ctk runtime configure --runtime=docker

# 重启 Docker 守护进程
pkill dockerd && dockerd &
```

**重要**：运行 `nvidia-ctk runtime configure` 后，该工具会覆盖 `/etc/docker/daemon.json`。如果之前有代理配置，必须重新添加：

```json
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
```

---

## 3. Docker 构建/下载速度慢

**现象**：Docker 构建下载速度约 1 MB/s，仅拉取基础镜像就需 45+ 分钟。

**原因**：中国大陆不使用代理时，连接 Docker Hub 和 PyPI 极慢。

**解决方案**：在多个层级配置代理：

### 层级 1：Docker 守护进程代理

```json
// /etc/docker/daemon.json
{
    "proxies": {
        "http-proxy": "http://127.0.0.1:1087",
        "https-proxy": "http://127.0.0.1:1087",
        "no-proxy": "localhost,127.0.0.1"
    }
}
```

### 层级 2：Docker 客户端代理

```json
// ~/.docker/config.json
{
    "proxies": {
        "default": {
            "httpProxy": "http://127.0.0.1:1087",
            "httpsProxy": "http://127.0.0.1:1087",
            "noProxy": "localhost,127.0.0.1"
        }
    }
}
```

### 层级 3：构建时环境变量

```bash
export http_proxy='http://127.0.0.1:1087'
export https_proxy='http://127.0.0.1:1087'
docker build --network host --progress=plain -t mineru:latest -f docker/Dockerfile docker/
```

使用代理后，下载速度从约 1 MB/s 提升至约 80 MB/s，总构建时间缩短至约 10 分钟。

---

## 4. Docker 构建完成但未生成镜像

**现象**：`docker images` 显示没有 `mineru:latest` 镜像，但构建看似已完成。`docker system df` 显示大量 "Images" 数据但数量为 0。

**原因**：VL 模型下载（`MinerU2.5-Pro-2604-1.2B`，13 个文件）需要约 6 分钟。如果构建命令作为后台任务运行且超时为 10 分钟，而前面的步骤已消耗大部分时间，构建会在最终镜像导出前被终止。

**关键观察**：步骤 1-3（基础镜像、apt-get、pip install）可缓存。步骤 4（模型下载）在完全完成前不会被缓存。VL 模型在 54%（7/13 文件）处是持续失败的节点。

**解决方案**：不在有超时限制的后台任务中运行构建，或确保超时至少为 20 分钟：

```bash
# 前台直接构建，设置足够超时
export http_proxy='http://127.0.0.1:1087'
export https_proxy='http://127.0.0.1:1087'
cd /root/mineru
docker build --network host --progress=plain -t mineru:latest -f docker/Dockerfile docker/
```

当缓存层可用时（步骤 1-3 CACHED），构建约 8 分钟即可完成（仅需下载模型）。

---

## 5. 构建输出截断 / tail 缓冲问题

**现象**：通过 `tail -20` 管道传输构建输出，导致长时间无输出，无法跟踪进度。

**原因**：`tail` 会缓冲输出直到上游进程完成，抵消了 `--progress=plain` 的优势。

**解决方案**：不要通过 `tail` 管道传输 docker build 输出。直接使用 `--progress=plain`：

```bash
# 正确 — 完整流式输出
docker build --progress=plain -t mineru:latest -f docker/Dockerfile docker/

# 错误 — 输出被缓冲，无法查看进度
docker build --progress=plain ... 2>&1 | tail -20
```

---

## 6. Docker 守护进程重启导致构建缓存丢失

**现象**：使用代理环境变量重启 `dockerd` 后，之前下载的层（约 42 GB）丢失。

**原因**：手动终止并重启 `dockerd` 时，进行中的层可能未正确提交到构建缓存。

**解决方案**：
- 尽可能使用 `systemctl restart docker` 进行优雅重启
- 避免在活跃构建期间终止 `dockerd`
- 接受重新下载；使用代理后，后续构建速度会快很多

---

## 7. apt-get 锁竞争

**现象**：
```
E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process XXXX
```

**原因**：之前的 `apt-get` 进程被中断但留下了锁文件。

**解决方案**：

```bash
# 终止残留进程
kill -9 <PID>

# 删除锁文件
rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock

# 重试
apt-get install -y <package>
```

---

## 8. 冷启动延迟

**现象**：第一个 API 请求耗时明显更长（2 MB PDF 约 15 秒，后续请求约 7 秒）。

**原因**：vLLM 引擎和 Pipeline 模型在首次请求时惰性加载。Qwen2VL 模型权重被加载到 GPU 显存，CUDA graph 被编译。

**解决方案**：这是预期行为。对于生产部署，容器启动后发送预热请求：

```bash
# 部署后预热
curl -s -X POST http://localhost:8000/file_parse \
  -F "files=@small_test.pdf" > /dev/null
```

---

## 9. 显存不足

**现象**：`torch.cuda.OutOfMemoryError` 或 vLLM 无法分配 KV Cache。

**原因**：vLLM 引擎使用大部分可用显存（约 23 GB）。默认 `gpu-memory-utilization` 下，KV Cache 可能占用过多内存。

**解决方案**：降低 GPU 显存利用率：

```yaml
# 在 compose.yaml 中
command:
  --host 0.0.0.0
  --port 8000
  --gpu-memory-utilization 0.5  # 从默认约 0.9 降低
```

如果问题仍然存在，可继续降低至 `0.4` 或更低。

---

## 10. SSRF 防护警告

**现象**：
```
WARNING: MinerU API is listening on 0.0.0.0. Disabling *-http-client backends and server_url by default
```

**原因**：安全特性。当 API 绑定到 `0.0.0.0` 时，外部调用者可以指定远程 HTTP 端点，存在 SSRF 风险。

**解决方案**：这是安全特性，不是错误。仅在了解风险的情况下禁用：

```yaml
command:
  --host 0.0.0.0
  --port 8000
  --allow-public-http-client  # 仅在私有网络中使用
```
