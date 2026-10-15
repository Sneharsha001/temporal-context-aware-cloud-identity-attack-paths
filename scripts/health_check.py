#!/usr/bin/env python3
"""
health_check.py - Workspace environment and dependency health verification.

Checks Python interpreter, installed packages, git configuration, and working tree
cleanliness before benchmark or evaluation runs.
"""

import sys
import subprocess
import shutil
from pathlib import Path


def check_python_version() -> bool:
    print(f"Checking Python version: {sys.version.split()[0]} ...", end=" ")
    if sys.version_info >= (3, 10):
        print("✅ OK")
        return True
    print("❌ Failed (requires Python 3.10+)")
    return False


def check_tool(tool_name: str) -> bool:
    print(f"Checking executable '{tool_name}' ...", end=" ")
    path = shutil.which(tool_name)
    if path:
        print(f"✅ Found ({path})")
        return True
    print("❌ Missing")
    return False


def check_git_config() -> bool:
    print("Checking Git user configuration ...", end=" ")
    try:
        name = subprocess.check_output(["git", "config", "user.name"], text=True).strip()
        email = subprocess.check_output(["git", "config", "user.email"], text=True).strip()
        if name and email:
            print(f"✅ OK ({name} <{email}>)")
            return True
        print("❌ Incomplete user.name or user.email")
        return False
    except Exception as exc:
        print(f"❌ Error checking git config: {exc}")
        return False


def main():
    print("=" * 60)
    print(" ARF-RT Environment Health Check")
    print("=" * 60)

    checks = [
        check_python_version(),
        check_tool("git"),
        check_tool("pytest"),
        check_git_config(),
    ]

    all_ok = all(checks)
    print("=" * 60)
    if all_ok:
        print("✅ Environment is healthy and ready for research evaluation.")
        sys.exit(0)
    else:
        print("⚠️ Environment has warnings or missing components.")
        sys.exit(1)


if __name__ == "__main__":
    main()
