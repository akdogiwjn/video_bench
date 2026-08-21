#!/usr/bin/env python3
"""Summarize a video benchmark run: parse task_window, compute metrics, generate summary JSON."""
from __future__ import annotations

import argparse
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


def compute_cpu_summary(csv_path: Path) -> dict:
    if not csv_path.exists():
        return {}
    rows = []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            rows.append(row)
    if not rows:
        return {}
    cpu_percentages = [float(r.get("cpu_percent", 0)) for r in rows if r.get("cpu_percent")]
    usage_values = [int(r.get("usage_usec", 0)) for r in rows if r.get("usage_usec")]
    return {
        "sample_count": len(rows),
        "avg_cpu_percent": sum(cpu_percentages) / len(cpu_percentages) if cpu_percentages else 0,
        "max_cpu_percent": max(cpu_percentages) if cpu_percentages else 0,
        "total_cpu_time_seconds": (usage_values[-1] - usage_values[0]) / 1_000_000 if len(usage_values) >= 2 else 0,
    }


def compute_resource_summary(csv_path: Path) -> dict:
    if not csv_path.exists():
        return {}
    rows = []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            rows.append(row)
    if not rows:
        return {}
    mem_values = [float(r.get("mem_usage_bytes", 0)) for r in rows if r.get("mem_usage_bytes")]
    net_in_values = [float(r.get("net_input_bytes", 0)) for r in rows if r.get("net_input_bytes")]
    net_out_values = [float(r.get("net_output_bytes", 0)) for r in rows if r.get("net_output_bytes")]
    blk_read_values = [float(r.get("block_read_bytes", 0)) for r in rows if r.get("block_read_bytes")]
    blk_write_values = [float(r.get("block_write_bytes", 0)) for r in rows if r.get("block_write_bytes")]
    return {
        "sample_count": len(rows),
        "peak_memory_bytes": max(mem_values) if mem_values else 0,
        "avg_memory_bytes": sum(mem_values) / len(mem_values) if mem_values else 0,
        "total_net_input_bytes": net_in_values[-1] - net_in_values[0] if len(net_in_values) >= 2 else 0,
        "total_net_output_bytes": net_out_values[-1] - net_out_values[0] if len(net_out_values) >= 2 else 0,
        "total_block_read_bytes": blk_read_values[-1] - blk_read_values[0] if len(blk_read_values) >= 2 else 0,
        "total_block_write_bytes": blk_write_values[-1] - blk_write_values[0] if len(blk_write_values) >= 2 else 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)

    start_epoch = safe_read_float(run_dir / "task_start_epoch.txt")
    end_epoch = safe_read_float(run_dir / "task_end_epoch.txt")
    exit_code = safe_read_float(run_dir / "exit_code.txt")

    verification = safe_read_json(run_dir / "vm_output" / "business_verification.json")
    if not verification:
        verification = safe_read_json(run_dir / "business_verification.json")

    task_window = safe_read_json(run_dir / "vm_output" / "task_window.json")
    if not task_window:
        task_window = safe_read_json(run_dir / "task_window.json")

    cpu_summary = compute_cpu_summary(run_dir / "container_cpu_samples.csv")
    resource_summary = compute_resource_summary(run_dir / "container_resource_samples.csv")

    wall_time = None
    if start_epoch and end_epoch:
        wall_time = round(end_epoch - start_epoch, 3)

    summary = {
        "case_id": args.case_id,
        "run_dir": str(run_dir),
        "wall_time_seconds": wall_time,
        "exit_code": exit_code,
        "verification": verification,
        "task_window": task_window,
        "cpu_summary": cpu_summary,
        "resource_summary": resource_summary,
        "l0_pass": verification.get("L0_pass", False),
        "l1_pass": verification.get("L1_pass", False),
        "hard_pass": verification.get("hard_pass", False),
        "l2_pending": verification.get("L2_pending", True),
    }

    summary_path = run_dir / "run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
