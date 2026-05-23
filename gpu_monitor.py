#!/usr/bin/env python3
"""GPU metrics collector using DCGM - records GPU utilization and memory usage."""

import subprocess
import time
import csv
import json
import os
from datetime import datetime

OUTPUT_DIR = os.environ.get("MINERU_OUTPUT_DIR", "/root/mineru/output")
INTERVAL = 2  # seconds between samples
CSV_FILE = os.path.join(OUTPUT_DIR, "gpu_metrics.csv")
SUMMARY_FILE = os.path.join(OUTPUT_DIR, "gpu_metrics_summary.json")


def collect_dcgmi_stats():
    """Collect GPU stats via dcgmi."""
    try:
        result = subprocess.run(
            ["dcgmi", "stats", "-e"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout
    except Exception:
        return ""


def collect_nvidia_smi():
    """Collect GPU stats via nvidia-smi as fallback."""
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=timestamp,utilization.gpu,utilization.memory,memory.used,memory.total,memory.free,power.draw,power.limit,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return ""


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Write CSV header
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "gpu_util_pct", "mem_util_pct",
            "mem_used_mb", "mem_total_mb", "mem_free_mb",
            "power_draw_w", "power_limit_w", "temp_c"
        ])

    print(f"GPU metrics collection started -> {CSV_FILE}")
    print(f"Sampling every {INTERVAL}s. Press Ctrl+C to stop.")

    samples = []
    try:
        while True:
            line = collect_nvidia_smi()
            if not line:
                time.sleep(INTERVAL)
                continue

            # Parse: timestamp, gpu_util, mem_util, mem_used, mem_total, mem_free, power_draw, power_limit, temp
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 9:
                time.sleep(INTERVAL)
                continue

            ts = parts[0]
            gpu_util = float(parts[1]) if parts[1] != "[N/A]" else 0
            mem_util = float(parts[2]) if parts[2] != "[N/A]" else 0
            mem_used = float(parts[3]) if parts[3] != "[N/A]" else 0
            mem_total = float(parts[4]) if parts[4] != "[N/A]" else 0
            mem_free = float(parts[5]) if parts[5] != "[N/A]" else 0
            power_draw = float(parts[6]) if parts[6] != "[N/A]" else 0
            power_limit = float(parts[7]) if parts[7] != "[N/A]" else 0
            temp = float(parts[8]) if parts[8] != "[N/A]" else 0

            with open(CSV_FILE, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    ts, gpu_util, mem_util, mem_used, mem_total, mem_free,
                    power_draw, power_limit, temp
                ])

            samples.append({
                "timestamp": ts,
                "gpu_util_pct": gpu_util,
                "mem_util_pct": mem_util,
                "mem_used_mb": mem_used,
                "mem_total_mb": mem_total,
                "power_draw_w": power_draw,
                "temp_c": temp,
            })

            # Print live stats every 10 samples
            if len(samples) % 10 == 0:
                print(f"[{ts}] GPU: {gpu_util}% | Mem: {mem_util}% ({mem_used}/{mem_total}MB) | Power: {power_draw}W | Temp: {temp}C")

            time.sleep(INTERVAL)

    except KeyboardInterrupt:
        print(f"\nStopped after {len(samples)} samples")

    # Compute summary
    if samples:
        gpu_utils = [s["gpu_util_pct"] for s in samples]
        mem_utils = [s["mem_util_pct"] for s in samples]
        mem_used = [s["mem_used_mb"] for s in samples]
        power_draws = [s["power_draw_w"] for s in samples]
        temps = [s["temp_c"] for s in samples]

        summary = {
            "collection_start": samples[0]["timestamp"],
            "collection_end": samples[-1]["timestamp"],
            "total_samples": len(samples),
            "sample_interval_s": INTERVAL,
            "gpu_utilization_pct": {
                "avg": round(sum(gpu_utils) / len(gpu_utils), 1),
                "max": round(max(gpu_utils), 1),
                "min": round(min(gpu_utils), 1),
            },
            "memory_utilization_pct": {
                "avg": round(sum(mem_utils) / len(mem_utils), 1),
                "max": round(max(mem_utils), 1),
                "min": round(min(mem_utils), 1),
            },
            "memory_used_mb": {
                "avg": round(sum(mem_used) / len(mem_used), 1),
                "max": round(max(mem_used), 1),
                "min": round(min(mem_used), 1),
            },
            "power_draw_w": {
                "avg": round(sum(power_draws) / len(power_draws), 1),
                "max": round(max(power_draws), 1),
                "min": round(min(power_draws), 1),
            },
            "temperature_c": {
                "avg": round(sum(temps) / len(temps), 1),
                "max": round(max(temps), 1),
            },
        }

        with open(SUMMARY_FILE, "w") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        print(f"\nSummary saved to {SUMMARY_FILE}")
        print(f"  GPU Util:  avg={summary['gpu_utilization_pct']['avg']}% max={summary['gpu_utilization_pct']['max']}%")
        print(f"  Mem Util:  avg={summary['memory_utilization_pct']['avg']}% max={summary['memory_utilization_pct']['max']}%")
        print(f"  Mem Used:  avg={summary['memory_used_mb']['avg']}MB max={summary['memory_used_mb']['max']}MB")
        print(f"  Power:     avg={summary['power_draw_w']['avg']}W max={summary['power_draw_w']['max']}W")
        print(f"  Temp:      avg={summary['temperature_c']['avg']}C max={summary['temperature_c']['max']}C")


if __name__ == "__main__":
    main()
