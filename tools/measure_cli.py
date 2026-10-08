"""Run one CLI process and retain wall time/peak RSS where wait4 is available."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = (
        args.command[1:] if args.command and args.command[0] == "--" else args.command
    )
    start = time.monotonic()
    usage = None
    with args.log.open("w") as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        if hasattr(os, "wait4"):
            _, status, usage = os.wait4(child.pid, 0)
            child.returncode = os.waitstatus_to_exitcode(status)
        else:
            child.wait()
    record = dict(
        command=command,
        returncode=child.returncode,
        elapsed_seconds=time.monotonic() - start,
        peak_rss_native_units=usage.ru_maxrss if usage else None,
        rss_unit="KiB on Linux; bytes on macOS" if usage else "unavailable",
    )
    args.record.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))
    return child.returncode


if __name__ == "__main__":
    raise SystemExit(main())
