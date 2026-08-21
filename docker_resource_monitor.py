#!/usr/bin/env python3
"""Docker resource monitor: memory, network, disk I/O via docker stats."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from pathlib import Path


def parse_docker_bytes(s: str) -> float:
    """Parse Docker stats byte strings: B/kB/KB/MB/GB/TB/KiB/MiB/GiB/TiB."""
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


def get_docker_stats(container_name: str) -> dict:
    result = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", container_name],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout.strip().splitlines()[0])
    except (json.JSONDecodeError, IndexError):
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container-name", required=True)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "container_resource_samples.csv"

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "mem_usage_bytes", "mem_limit_bytes",
            "mem_percent", "cpu_percent", "net_input_bytes", "net_output_bytes",
            "block_read_bytes", "block_write_bytes", "pids",
        ])

    while True:
        now = time.time()
        stats = get_docker_stats(args.container_name)
        if stats:
            mem_usage, mem_limit = stats.get("MemUsage", "/").split("/")
            mem_percent = parse_docker_bytes(stats.get("MemPerc", "0%").replace("%", "").strip())
            cpu_percent = stats.get("CPUPerc", "0%").replace("%", "").strip()
            net_in, net_out = stats.get("NetIO", "/").split("/")
            blk_read, blk_write = stats.get("BlockIO", "/").split("/")
            pids = stats.get("PIDs", "0")

            with open(csv_path, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    f"{now:.6f}",
                    parse_docker_bytes(mem_usage.strip()),
                    parse_docker_bytes(mem_limit.strip()),
                    mem_percent, cpu_percent,
                    parse_docker_bytes(net_in.strip()),
                    parse_docker_bytes(net_out.strip()),
                    parse_docker_bytes(blk_read.strip()),
                    parse_docker_bytes(blk_write.strip()),
                    pids,
                ])
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
