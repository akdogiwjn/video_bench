#!/usr/bin/env python3
"""Docker resource monitor: memory, network, disk I/O via docker stats."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from pathlib import Path


def get_docker_stats(container_name: str) -> dict:
    result = subprocess.run(
        ["docker", "stats", "--no-stream", "--format",
         "{{json .}}", container_name],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        data = json.loads(result.stdout.strip().splitlines()[0])
        return data
    except (json.JSONDecodeError, IndexError):
        return {}


def parse_mem(mem_str: str) -> float:
    if not mem_str:
        return 0.0
    mem_str = mem_str.lower().strip()
    try:
        if mem_str.endswith("gib"):
            return float(mem_str[:-3]) * 1024 * 1024 * 1024
        elif mem_str.endswith("mib"):
            return float(mem_str[:-3]) * 1024 * 1024
        elif mem_str.endswith("kib"):
            return float(mem_str[:-3]) * 1024
        elif mem_str.endswith("b"):
            return float(mem_str[:-1])
        return float(mem_str)
    except (ValueError, IndexError):
        return 0.0


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

    with open(output_dir / "docker_resource_monitor.log", "w") as log:
        log.write(f"started_at={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
        log.write(f"container_name={args.container_name}\n")
        log.write(f"interval={args.interval}\n")

        while True:
            now = time.time()
            stats = get_docker_stats(args.container_name)
            if stats:
                mem_usage, mem_limit = stats.get("MemUsage", "/").split("/")
                mem_percent = parse_mem(stats.get("MemPerc", "0%").replace("%", ""))
                cpu_percent = stats.get("CPUPerc", "0%").replace("%", "")
                net_in, net_out = stats.get("NetIO", "/").split("/")
                blk_read, blk_write = stats.get("BlockIO", "/").split("/")
                pids = stats.get("PIDs", "0")

                with open(csv_path, "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        f"{now:.6f}",
                        parse_mem(mem_usage.strip()), parse_mem(mem_limit.strip()),
                        mem_percent, cpu_percent,
                        parse_mem(net_in.strip()), parse_mem(net_out.strip()),
                        parse_mem(blk_read.strip()), parse_mem(blk_write.strip()),
                        pids,
                    ])
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
