#!/usr/bin/env python3
"""MinerU batch inference script - submit PDFs via async API and collect results."""

import os
import sys
import time
import json
import glob
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

API_BASE = os.environ.get("MINERU_API_URL", "http://localhost:8000")
PDF_DIR = os.environ.get("MINERU_PDF_DIR", "/root/mineru/pdf")
OUTPUT_DIR = os.environ.get("MINERU_OUTPUT_DIR", "/root/mineru/output")
MAX_CONCURRENT = 3  # match server concurrency limit
POLL_INTERVAL = 5   # seconds between status checks

def submit_task(pdf_path: str) -> dict:
    """Submit a single PDF parsing task."""
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
    print(f"  [SUBMIT] {filename} -> task_id={task_id}")
    return {"filename": filename, "task_id": task_id, "pdf_path": pdf_path}


def poll_task(task_info: dict) -> dict:
    """Poll a task until completion and save result."""
    task_id = task_info["task_id"]
    filename = task_info["filename"]
    start = time.time()

    while True:
        try:
            resp = requests.get(f"{API_BASE}/tasks/{task_id}", timeout=30)
            data = resp.json()
        except Exception as e:
            print(f"  [POLL ERROR] {filename}: {e}")
            time.sleep(POLL_INTERVAL)
            continue

        status = data.get("status", "unknown")
        elapsed = time.time() - start

        if status in ("completed", "done", "success"):
            print(f"  [DONE] {filename} ({elapsed:.1f}s)")
            # Fetch result
            try:
                result_resp = requests.get(
                    f"{API_BASE}/tasks/{task_id}/result", timeout=60
                )
                save_result(task_info, result_resp)
            except Exception as e:
                print(f"  [SAVE ERROR] {filename}: {e}")
            return {"filename": filename, "status": "completed", "elapsed": elapsed}

        elif status in ("failed", "error"):
            print(f"  [FAILED] {filename} ({elapsed:.1f}s): {data}")
            return {"filename": filename, "status": "failed", "elapsed": elapsed}

        else:
            if int(elapsed) % 30 == 0:
                print(f"  [POLL] {filename} status={status} ({elapsed:.0f}s)")
            time.sleep(POLL_INTERVAL)


def save_result(task_info: dict, resp: requests.Response):
    """Save task result to output directory."""
    filename = task_info["filename"]
    task_id = task_info["task_id"]
    out_dir = os.path.join(OUTPUT_DIR, Path(filename).stem)
    os.makedirs(out_dir, exist_ok=True)

    content_type = resp.headers.get("content-type", "")

    if "zip" in content_type or "octet-stream" in content_type:
        zip_path = os.path.join(out_dir, f"{task_id}.zip")
        with open(zip_path, "wb") as f:
            f.write(resp.content)
        # Extract zip
        import zipfile
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(out_dir)
            os.remove(zip_path)
            print(f"  [SAVE] {filename} -> {out_dir}/ (extracted)")
        except zipfile.BadZipFile:
            print(f"  [SAVE] {filename} -> {zip_path} (raw, not a zip)")
    elif "json" in content_type:
        json_path = os.path.join(out_dir, f"{task_id}.json")
        with open(json_path, "w") as f:
            f.write(resp.text)
        print(f"  [SAVE] {filename} -> {json_path}")
    else:
        raw_path = os.path.join(out_dir, f"{task_id}_result")
        with open(raw_path, "wb") as f:
            f.write(resp.content)
        print(f"  [SAVE] {filename} -> {raw_path}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Collect all PDFs
    pdfs = sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf")))
    if not pdfs:
        print(f"No PDF files found in {PDF_DIR}")
        sys.exit(1)

    print(f"Found {len(pdfs)} PDF files in {PDF_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"API: {API_BASE}")
    print(f"Concurrency: {MAX_CONCURRENT}")
    print("=" * 60)

    # Phase 1: Submit all tasks
    print("\n[Phase 1] Submitting tasks...")
    tasks = []
    for pdf in pdfs:
        try:
            task = submit_task(pdf)
            tasks.append(task)
        except Exception as e:
            print(f"  [SUBMIT ERROR] {os.path.basename(pdf)}: {e}")

    if not tasks:
        print("No tasks submitted successfully.")
        sys.exit(1)

    print(f"\nSubmitted {len(tasks)}/{len(pdfs)} tasks successfully")

    # Phase 2: Poll all tasks concurrently
    print(f"\n[Phase 2] Processing (max {MAX_CONCURRENT} concurrent)...")
    overall_start = time.time()
    results = []

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as executor:
        futures = {executor.submit(poll_task, t): t for t in tasks}
        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                task = futures[future]
                print(f"  [FUTURE ERROR] {task['filename']}: {e}")
                results.append({"filename": task["filename"], "status": "error"})

    # Summary
    total_time = time.time() - overall_start
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] != "completed")

    print("\n" + "=" * 60)
    print(f"[Summary]")
    print(f"  Total:  {len(results)}")
    print(f"  OK:     {completed}")
    print(f"  Failed: {failed}")
    print(f"  Time:   {total_time:.1f}s")
    if completed > 0:
        avg = sum(r["elapsed"] for r in results if r["status"] == "completed") / completed
        print(f"  Avg:    {avg:.1f}s/file")
    print(f"  Output: {OUTPUT_DIR}")

    # Save summary
    summary_path = os.path.join(OUTPUT_DIR, "batch_summary.json")
    with open(summary_path, "w") as f:
        json.dump({
            "total": len(results),
            "completed": completed,
            "failed": failed,
            "total_time": total_time,
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"  Summary: {summary_path}")


if __name__ == "__main__":
    main()
