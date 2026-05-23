#!/usr/bin/env python3
"""MinerU stress test - run multiple rounds of batch inference with concurrent GPU monitoring."""

import os
import sys
import time
import json
import glob
import subprocess
import signal
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

API_BASE = os.environ.get("MINERU_API_URL", "http://localhost:8000")
PDF_DIR = os.environ.get("MINERU_PDF_DIR", "/root/mineru/pdf")
OUTPUT_DIR = os.environ.get("MINERU_OUTPUT_DIR", "/root/mineru/output")
MAX_CONCURRENT = 3
POLL_INTERVAL = 3
NUM_ROUNDS = 3  # repeat batch to sustain GPU load

GPU_MONITOR_SCRIPT = "/root/mineru/gpu_monitor.py"
GPU_METRICS_CSV = os.path.join(OUTPUT_DIR, "gpu_metrics.csv")
GPU_METRICS_SUMMARY = os.path.join(OUTPUT_DIR, "gpu_metrics_summary.json")


def start_gpu_monitor():
    """Start GPU monitor as background process."""
    # Clean old metrics
    for f in [GPU_METRICS_CSV, GPU_METRICS_SUMMARY]:
        if os.path.exists(f):
            os.remove(f)
    proc = subprocess.Popen(
        [sys.executable, GPU_MONITOR_SCRIPT],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        preexec_fn=os.setsid
    )
    print(f"[GPU MONITOR] Started PID={proc.pid}")
    time.sleep(3)  # let it collect a few idle samples
    return proc


def stop_gpu_monitor(proc):
    """Stop GPU monitor and wait for summary generation."""
    print("[GPU MONITOR] Stopping...")
    os.killpg(os.getpgid(proc.pid), signal.SIGINT)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("[GPU MONITOR] Stopped")


def submit_task(pdf_path: str) -> dict:
    filename = os.path.basename(pdf_path)
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            f"{API_BASE}/tasks",
            files={"files": (filename, f, "application/pdf")},
            data={"backend": "vlm-auto-engine", "lang_list": "en"},
            timeout=300,
        )
    resp.raise_for_status()
    result = resp.json()
    task_id = result.get("task_id") or result.get("id")
    return {"filename": filename, "task_id": task_id}


def poll_task(task_info: dict) -> dict:
    task_id = task_info["task_id"]
    filename = task_info["filename"]
    start = time.time()
    while True:
        try:
            resp = requests.get(f"{API_BASE}/tasks/{task_id}", timeout=30)
            data = resp.json()
        except Exception:
            time.sleep(POLL_INTERVAL)
            continue
        status = data.get("status", "unknown")
        elapsed = time.time() - start
        if status in ("completed", "done", "success"):
            return {"filename": filename, "status": "completed", "elapsed": elapsed}
        elif status in ("failed", "error"):
            return {"filename": filename, "status": "failed", "elapsed": elapsed}
        else:
            time.sleep(POLL_INTERVAL)


def run_one_round(pdfs, round_num):
    """Submit all PDFs and poll concurrently."""
    print(f"\n--- Round {round_num}/{NUM_ROUNDS} ---")
    print(f"[SUBMIT] Submitting {len(pdfs)} PDFs...")
    tasks = []
    for pdf in pdfs:
        try:
            task = submit_task(pdf)
            tasks.append(task)
        except Exception as e:
            print(f"  [ERROR] {os.path.basename(pdf)}: {e}")

    print(f"[POLL] Processing {len(tasks)} tasks (concurrency={MAX_CONCURRENT})...")
    round_start = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {executor.submit(poll_task, t): t for t in tasks}
        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                task = futures[future]
                results.append({"filename": task["filename"], "status": "error"})

    round_time = time.time() - round_start
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] != "completed")
    print(f"[ROUND {round_num}] {completed} ok, {failed} fail, {round_time:.1f}s")
    return results, round_time


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pdfs = sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf")))
    if not pdfs:
        print(f"No PDFs in {PDF_DIR}")
        sys.exit(1)

    print(f"Stress Test Configuration:")
    print(f"  PDFs: {len(pdfs)}")
    print(f"  Rounds: {NUM_ROUNDS}")
    print(f"  Concurrency: {MAX_CONCURRENT}")
    print(f"  Total tasks: {len(pdfs) * NUM_ROUNDS}")
    print("=" * 60)

    # Start GPU monitor
    monitor_proc = start_gpu_monitor()

    all_results = []
    overall_start = time.time()

    try:
        for rnd in range(1, NUM_ROUNDS + 1):
            results, round_time = run_one_round(pdfs, rnd)
            all_results.extend(results)
    except KeyboardInterrupt:
        print("\n[Interrupted]")
    finally:
        # Stop GPU monitor
        stop_gpu_monitor(monitor_proc)

    overall_time = time.time() - overall_start

    # Load GPU summary
    gpu_summary = {}
    if os.path.exists(GPU_METRICS_SUMMARY):
        with open(GPU_METRICS_SUMMARY) as f:
            gpu_summary = json.load(f)

    # Count active GPU samples (util > 0) for stress test metrics
    active_gpu_utils = []
    active_mem_utils = []
    if os.path.exists(GPU_METRICS_CSV):
        import csv as csv_mod
        with open(GPU_METRICS_CSV) as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                gu = float(row.get("gpu_util_pct", 0))
                mu = float(row.get("mem_util_pct", 0))
                if gu > 0 or mu > 0:
                    active_gpu_utils.append(gu)
                    active_mem_utils.append(mu)

    completed = sum(1 for r in all_results if r["status"] == "completed")
    failed = sum(1 for r in all_results if r["status"] != "completed")

    summary = {
        "test_type": "stress_test",
        "num_rounds": NUM_ROUNDS,
        "pdfs_per_round": len(pdfs),
        "total_tasks": len(all_results),
        "completed": completed,
        "failed": failed,
        "overall_time_s": round(overall_time, 1),
        "avg_time_per_file_s": round(overall_time / max(completed, 1), 2),
        "throughput_files_per_min": round(completed / (overall_time / 60), 2),
        "gpu_metrics": gpu_summary,
        "active_period_metrics": {
            "gpu_util_pct_avg": round(sum(active_gpu_utils) / max(len(active_gpu_utils), 1), 1),
            "gpu_util_pct_max": round(max(active_gpu_utils), 1) if active_gpu_utils else 0,
            "mem_util_pct_avg": round(sum(active_mem_utils) / max(len(active_mem_utils), 1), 1),
            "mem_util_pct_max": round(max(active_mem_utils), 1) if active_mem_utils else 0,
            "active_samples": len(active_gpu_utils),
        },
        "results": all_results,
    }

    summary_path = os.path.join(OUTPUT_DIR, "stress_test_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Print report
    print("\n" + "=" * 60)
    print("STRESS TEST REPORT")
    print("=" * 60)
    print(f"  Rounds:      {NUM_ROUNDS}")
    print(f"  Total tasks: {len(all_results)}")
    print(f"  Completed:   {completed}")
    print(f"  Failed:      {failed}")
    print(f"  Total time:  {overall_time:.1f}s")
    print(f"  Avg/file:    {overall_time / max(completed, 1):.1f}s")
    print(f"  Throughput:  {completed / (overall_time / 60):.1f} files/min")
    print()
    if gpu_summary:
        gu = gpu_summary.get("gpu_utilization_pct", {})
        mu = gpu_summary.get("memory_utilization_pct", {})
        mw = gpu_summary.get("memory_used_mb", {})
        pw = gpu_summary.get("power_draw_w", {})
        tp = gpu_summary.get("temperature_c", {})
        print("GPU METRICS (full period):")
        print(f"  GPU Util:    avg={gu.get('avg',0)}% max={gu.get('max',0)}%")
        print(f"  Mem Util:    avg={mu.get('avg',0)}% max={mu.get('max',0)}%")
        print(f"  Mem Used:    avg={mw.get('avg',0)}MB max={mw.get('max',0)}MB / {mw.get('min',0)}MB min")
        print(f"  Power:       avg={pw.get('avg',0)}W max={pw.get('max',0)}W")
        print(f"  Temp:        avg={tp.get('avg',0)}C max={tp.get('max',0)}C")
    if active_gpu_utils:
        print()
        print("GPU METRICS (active period, util>0):")
        print(f"  GPU Util:    avg={summary['active_period_metrics']['gpu_util_pct_avg']}% max={summary['active_period_metrics']['gpu_util_pct_max']}%")
        print(f"  Mem Util:    avg={summary['active_period_metrics']['mem_util_pct_avg']}% max={summary['active_period_metrics']['mem_util_pct_max']}%")
    print()
    print(f"  Report: {summary_path}")
    print(f"  GPU CSV: {GPU_METRICS_CSV}")


if __name__ == "__main__":
    main()
