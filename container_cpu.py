#!/usr/bin/env python3
"""Container CPU monitor via cgroup. Uses /proc/PID/cgroup for robust path detection."""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from pathlib import Path


def get_container_pid(container_name: str) -> int | None:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Pid}}", container_name],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def get_cgroup_path_from_pid(pid: int) -> str | None:
    """Read /proc/<PID>/cgroup to find the real cgroup path."""
    cgroup_file = f"/proc/{pid}/cgroup"
    if not os.path.exists(cgroup_file):
        return None
    try:
        with open(cgroup_file) as f:
            for line in f:
                # Format: hierarchy_id:controller:path  or  0::/path (cgroup v2)
                parts = line.strip().split(":")
                if len(parts) == 3:
                    path = parts[2].strip()
                    # Check for cpu v2 path or v1 cpu path
                    if "cpu" in parts[1] or parts[1] == "":
                        full_path = f"/sys/fs/cgroup{path}"
                        if os.path.exists(os.path.join(full_path, "cpu.stat")):
                            return full_path
                        # Try v1 style
                        full_path = f"/sys/fs/cgroup/cpu{path}"
                        if os.path.exists(os.path.join(full_path, "cpu.stat")):
                            return full_path
    except (OSError, IndexError):
        pass
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

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "usage_usec", "user_usec", "system_usec", "delta_usage_usec", "cpu_percent"])

    prev_usage = 0
    prev_time = time.time()
    cgroup_path = None
    pid = None

    while True:
        if cgroup_path is None:
            pid = get_container_pid(args.container_name)
            if pid and pid > 0:
                cgroup_path = get_cgroup_path_from_pid(pid)
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
            writer.writerow([f"{now:.6f}", cpu["usage_usec"], cpu["user_usec"], cpu["system_usec"], delta, f"{cpu_percent:.2f}"])

        prev_usage = cpu["usage_usec"]
        prev_time = now
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
