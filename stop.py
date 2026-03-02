#!/usr/bin/env python3
"""
Mini-RAG stop helper for Linux environments.
"""
import subprocess
import sys


def stop_server() -> None:
    print("=" * 50)
    print("Stopping Mini-RAG")
    print("=" * 50)

    try:
        result = subprocess.run(
            ["pkill", "-f", "python.*run.py|uvicorn"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("pkill is not available on this system.")
        sys.exit(1)
    except Exception as exc:
        print(f"Failed to stop server: {exc}")
        sys.exit(1)

    if result.returncode == 0:
        print("Mini-RAG stopped.")
        return

    if result.returncode == 1:
        print("No running Mini-RAG process was found.")
        return

    stderr = result.stderr.strip()
    print(f"Failed to stop server: {stderr or 'unknown error'}")
    sys.exit(1)


if __name__ == "__main__":
    stop_server()
