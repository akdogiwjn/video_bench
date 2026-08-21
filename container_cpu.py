#!/usr/bin/env python3
"""Container CPU monitor via cgroup. Samples CPU usage for a named Docker container."""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from pathlib import Path


def get_container_cgroup_path(container_name: str) -> str | None:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.Id}}", container_name],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    container_id = result.stdout.strip()
    for base in ["/sys/fs/cgroup", "/sys/fs/cgroup/docker"]:
        path = f"{base}/{container_id}"
        if os.path.exists(path):
            return path
        path = f"{base}/docker/{container_id}"
        if os.path.exists(path):
            return path
    short_id = container_id[:12]
    for base in ["/sys/fs/cgroup", "/sys/fs/cgroup/docker"]:
        path = f"{base}/{short_id}"
        if os.path.exists(path):
            return path
        path = f"{base}/docker/{short_id}"
        if os.path.exists(path):
            return path
    return None


def read_cgroup_cpu(cgroup_path: str) -> dict:
    usage_usec = 0
    user_usec = 0
    system_usec = 0
    cpu_stat = os.path.join(cgroup_path, "cpu.stat")
    if os.path.exists(cpu_stat):
        with open(cpu_stat) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 2:
                    if parts[0] == "usage_usec":
                        usage_usec = int(parts[1])
                    elif parts[0] == "user_usec":
                        user_usec = int(parts[1])
                    elif parts[0] == "system_usec":
                        system_usec = int(parts[1])
    return {"usage_usec": usage_usec, "user_usec": user_usec, "system_usec": system_usec}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container-name", required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "container_cpu_samples.csv"
    log_path = output_dir / "container_cpu.log"

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "usage_usec", "user_usec", "system_usec", "delta_usage_usec", "cpu_percent"])

    prev_usage = 0
    prev_time = time.time()
    cgroup_path = None

    with open(log_path, "w") as log:
        log.write(f"started_at={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
        log.write(f"container_name={args.container_name}\n")
        log.write(f"interval={args.interval}\n")

        while True:
            if cgroup_path is None:
                cgroup_path = get_container_cgroup_path(args.container_name)
                if cgroup_path is None:
                    time.sleep(args.interval)
                    continue

            now = time.time()
            cpu = read_cgroup_cpu(cgroup_path)
            delta = cpu["usage_usec"] - prev_usage
            elapsed = now - prev_time
            cpu_percent = (delta / 1_000_000) / elapsed * 100 if elapsed > 0 and prev_usage > 0 else 0

            with open(csv_path, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    f"{now:.6f}",
                    cpu["usage_usec"], cpu["user_usec"], cpu["system_usec"],
                    delta, f"{cpu_percent:.2f}",
                ])

            prev_usage = cpu["usage_usec"]
            prev_time = now
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
