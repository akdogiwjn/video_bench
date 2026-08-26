#!/usr/bin/env python3
"""Summarize a video benchmark run: filter resource samples by task_window, compute metrics."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def safe_read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def safe_read_float(path: Path) -> float | None:
    try:
        return float(path.read_text().strip())
    except (OSError, ValueError):
        return None


def parse_docker_bytes(s: str) -> float:
    """Parse Docker stats byte strings: supports B/kB/KB/MB/GB/KiB/MiB/GiB."""
    if not s:
        return 0.0
    s = s.strip()
    units = [
        ("TiB", 1024**4), ("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024),
        ("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("kB", 1e3), ("KB", 1e3),
        ("B", 1.0),
    ]
    for suffix, multiplier in units:
        if s.endswith(suffix):
            try:
                return float(s[:-len(suffix)].strip()) * multiplier
            except ValueError:
                return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def filter_samples_by_window(csv_path: Path, window: dict | None) -> list[dict]:
    """Read CSV samples and keep only those within task_window. Fail-closed: no samples = empty list."""
    if not csv_path.exists():
        return []
    rows = []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            rows.append(row)
    if not rows:
        return []
    if window is None:
        return []  # #5 fix: fail-closed
    start = window.get("start_epoch")
    end = window.get("end_epoch")
    if start is None or end is None:
        return []  # #5 fix: fail-closed
    filtered = []
    for row in rows:
        ts = float(row.get("timestamp", 0))
        if start <= ts <= end:
            filtered.append(row)
    # #1 fix: fail-closed — do NOT fallback to all rows if no samples in window
    return filtered


def compute_cpu_summary(csv_path: Path, window: dict | None) -> dict:
    rows = filter_samples_by_window(csv_path, window)
    if not rows:
        return {"sample_count": 0}
    cpu_pcts = [float(r.get("cpu_percent", 0)) for r in rows if r.get("cpu_percent")]
    usage_vals = [int(r.get("usage_usec", 0)) for r in rows if r.get("usage_usec")]
    total_cpu_time = 0
    if len(usage_vals) >= 2:
        total_cpu_time = (usage_vals[-1] - usage_vals[0]) / 1_000_000
    return {
        "sample_count": len(rows),
        "task_avg_cpu_percent": round(sum(cpu_pcts) / len(cpu_pcts), 2) if cpu_pcts else 0,
        "task_max_cpu_percent": round(max(cpu_pcts), 2) if cpu_pcts else 0,
        "task_cpu_time_seconds": round(total_cpu_time, 3),
    }


def compute_resource_summary(csv_path: Path, window: dict | None) -> dict:
    rows = filter_samples_by_window(csv_path, window)
    if not rows:
        return {"sample_count": 0}
    mem_vals = [parse_docker_bytes(r.get("mem_usage_bytes", "0")) for r in rows]
    net_in = [parse_docker_bytes(r.get("net_input_bytes", "0")) for r in rows]
    net_out = [parse_docker_bytes(r.get("net_output_bytes", "0")) for r in rows]
    blk_read = [parse_docker_bytes(r.get("block_read_bytes", "0")) for r in rows]
    blk_write = [parse_docker_bytes(r.get("block_write_bytes", "0")) for r in rows]
    return {
        "sample_count": len(rows),
        "task_peak_memory_bytes": int(max(mem_vals)) if mem_vals else 0,
        "task_avg_memory_bytes": int(sum(mem_vals) / len(mem_vals)) if mem_vals else 0,
        "task_net_rx_bytes": int(net_in[-1] - net_in[0]) if len(net_in) >= 2 else 0,
        "task_net_tx_bytes": int(net_out[-1] - net_out[0]) if len(net_out) >= 2 else 0,
        "task_disk_read_bytes": int(blk_read[-1] - blk_read[0]) if len(blk_read) >= 2 else 0,
        "task_disk_write_bytes": int(blk_write[-1] - blk_write[0]) if len(blk_write) >= 2 else 0,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)

    task_window = safe_read_json(run_dir / "task_window.json")
    verification = safe_read_json(run_dir / "business_verification.json")
    exit_code = safe_read_float(run_dir / "exit_code.txt")

    cpu_summary = compute_cpu_summary(run_dir / "container_cpu_samples.csv", task_window)
    resource_summary = compute_resource_summary(run_dir / "container_resource_samples.csv", task_window)

    # #1 fix: require minimum sample count for valid performance data
    perf_valid = cpu_summary.get("sample_count", 0) >= 3 and resource_summary.get("sample_count", 0) >= 2

    task_duration = task_window.get("duration_seconds")
    # #8 fix: container_total_wall_time removed (runner no longer generates task_start/end_epoch.txt)

    summary = {
        "case_id": args.case_id,
        "run_dir": str(run_dir),
        "task_wall_time_seconds": task_duration,
        "exit_code": exit_code,
        "l0_pass": verification.get("L0_pass"),
        "l1_pass": verification.get("L1_pass"),
        "hard_pass": verification.get("hard_pass"),
        "cpu_summary": cpu_summary,
        "resource_summary": resource_summary,
        "performance_valid": perf_valid,
    }

    out = run_dir / "run_summary.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
