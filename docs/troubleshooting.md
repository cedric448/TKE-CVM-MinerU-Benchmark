# Troubleshooting

This document records all issues encountered during the deployment process and their solutions.

## 1. Docker Engine Not Installed

**Symptom**: `docker: command not found`

**Solution**: Install Docker CE from the official repository:

```bash
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

If `dockerd` is not started automatically (non-systemd environments):

```bash
dockerd &
```

---

## 2. NVIDIA Container Toolkit Missing

**Symptom**:
```
Error response from daemon: could not select device driver "nvidia" with capabilities: [[gpu]]
```

**Cause**: The NVIDIA Container Toolkit is required for Docker to access the GPU. The NVIDIA driver (570.158.01) was installed but the container runtime was not.

**Solution**:

```bash
# Add NVIDIA repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install
apt-get update
apt-get install -y nvidia-container-toolkit

# Configure Docker
nvidia-ctk runtime configure --runtime=docker

# Restart Docker daemon
pkill dockerd && dockerd &
```

**Important**: After running `nvidia-ctk runtime configure`, the tool overwrites `/etc/docker/daemon.json`. If you had proxy configuration there, you must re-add it:

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

## 3. Slow Docker Build / Download Speed

**Symptom**: Docker build downloads at ~1 MB/s, taking 45+ minutes for base image pull alone.

**Cause**: Without proxy, connections to Docker Hub and PyPI from China mainland are extremely slow.

**Solution**: Configure proxy at multiple levels:

### Level 1: Docker Daemon Proxy

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

### Level 2: Docker Client Proxy

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

### Level 3: Build-time Environment Variables

```bash
export http_proxy='http://127.0.0.1:1087'
export https_proxy='http://127.0.0.1:1087'
docker build --network host --progress=plain -t mineru:latest -f docker/Dockerfile docker/
```

With proxy, download speeds improved from ~1 MB/s to ~80 MB/s, reducing total build time to ~10 minutes.

---

## 4. Docker Build Completes But No Image Created

**Symptom**: `docker images` shows no `mineru:latest` image after a build that appeared to complete. Docker system df shows large "Images" data but 0 count.

**Cause**: The VL model download (`MinerU2.5-Pro-2604-1.2B`, 13 files) takes ~6 minutes. If the build command is run as a background task with a 10-minute timeout, and earlier steps consume most of the time, the build gets killed before the final image export completes.

**Key observation**: Steps 1-3 (base image, apt-get, pip install) are cacheable. Step 4 (model download) is not cached until it fully completes. The VL model at 54% (7/13 files) was the consistent failure point.

**Solution**: Run the build without a background timeout, or ensure the timeout is at least 20 minutes:

```bash
# Direct foreground build with sufficient timeout
export http_proxy='http://127.0.0.1:1087'
export https_proxy='http://127.0.0.1:1087'
cd /root/mineru
docker build --network host --progress=plain -t mineru:latest -f docker/Dockerfile docker/
```

When cached layers are available (steps 1-3 CACHED), the build completes in ~8 minutes (model download only).

---

## 5. Build Output Truncated / tail Buffering

**Symptom**: Piping build output through `tail -20` causes no output to appear for extended periods, making it impossible to track progress.

**Cause**: `tail` buffers output until the upstream process completes, negating the benefit of `--progress=plain`.

**Solution**: Do not pipe docker build output through `tail`. Use `--progress=plain` directly and let the full output stream:

```bash
# Good - full streaming output
docker build --progress=plain -t mineru:latest -f docker/Dockerfile docker/

# Bad - output buffered, no visibility
docker build --progress=plain ... 2>&1 | tail -20
```

---

## 6. Docker Daemon Restart Clears Build Cache

**Symptom**: After restarting `dockerd` with proxy environment variables, previously downloaded layers (~42 GB) are lost.

**Cause**: When `dockerd` is killed and restarted manually, in-progress layers may not be properly committed to the build cache.

**Solution**:
- Use `systemctl restart docker` when possible for graceful restarts
- Avoid killing `dockerd` during active builds
- Accept the re-download; with proxy, subsequent builds are much faster

---

## 7. apt-get Lock Contention

**Symptom**:
```
E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process XXXX
```

**Cause**: A previous `apt-get` process was interrupted but left the lock file.

**Solution**:

```bash
# Kill the stale process
kill -9 <PID>

# Remove lock files
rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock

# Retry
apt-get install -y <package>
```

---

## 8. Cold Start Latency

**Symptom**: The first API request takes significantly longer (~15s for a 2 MB PDF vs ~7s for subsequent requests).

**Cause**: The vLLM engine and pipeline models are lazily loaded on the first request. The Qwen2VL model weights are loaded into GPU memory, and the CUDA graph is compiled.

**Solution**: This is expected behavior. For production deployments, send a warmup request after container startup:

```bash
# Warmup after deployment
curl -s -X POST http://localhost:8000/file_parse \
  -F "files=@small_test.pdf" > /dev/null
```

---

## 9. VRAM Shortage

**Symptom**: `torch.cuda.OutOfMemoryError` or vLLM fails to allocate KV cache.

**Cause**: The vLLM engine uses most available VRAM (~23 GB). With the default `gpu-memory-utilization`, the KV cache may consume too much memory.

**Solution**: Reduce GPU memory utilization:

```yaml
# In compose.yaml
command:
  --host 0.0.0.0
  --port 8000
  --gpu-memory-utilization 0.5  # Reduce from default ~0.9
```

Or set to `0.4` or lower if issues persist.

---

## 10. SSRF Protection Warning

**Symptom**:
```
WARNING: MinerU API is listening on 0.0.0.0. Disabling *-http-client backends and server_url by default
```

**Cause**: Security feature. When the API binds to `0.0.0.0`, external callers could specify remote HTTP endpoints, creating SSRF risk.

**Solution**: This is a security feature, not an error. Only disable it if you understand the risks:

```yaml
command:
  --host 0.0.0.0
  --port 8000
  --allow-public-http-client  # Only if on a private network
```
