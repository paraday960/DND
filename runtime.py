# -*- coding: utf-8 -*-
"""Runtime hardening helpers for phone/Android and desktop runs.

The bot must run in very different environments: normal Linux, Termux, and
Android app sandboxes where paths such as /tmp may be read-only.  This module
centralises writable path selection, environment preparation, and safe
self-diagnostics without exposing secrets.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
from typing import Any, Dict, Iterable, Optional

_RUNTIME: Optional[Dict[str, Any]] = None


def _base_dir(base_dir: Optional[str] = None) -> str:
    return os.path.abspath(base_dir or os.path.dirname(os.path.abspath(__file__)))


def _try_writable_dir(path: str) -> Optional[str]:
    if not path:
        return None
    path = os.path.abspath(os.path.expanduser(path))
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return path
    except Exception:
        return None


def _first_writable(candidates: Iterable[str], fallback_name: str) -> str:
    for candidate in candidates:
        ok = _try_writable_dir(candidate)
        if ok:
            return ok
    # Last resort: current working directory + fallback_name. If this fails, let
    # the exception surface early with a useful path.
    fallback = os.path.abspath(os.path.join(os.getcwd(), fallback_name))
    os.makedirs(fallback, exist_ok=True)
    return fallback


def ensure_runtime(base_dir: Optional[str] = None) -> Dict[str, Any]:
    """Prepare writable data/tmp/log directories and export safe env vars.

    Idempotent: safe to call from config, webapp, tests, and command handlers.
    """
    global _RUNTIME
    base = _base_dir(base_dir)
    home = os.path.expanduser("~")

    data_dir = _first_writable(
        [
            os.environ.get("DND_DATA_DIR", ""),
            os.path.join(base, "data"),
            os.path.join(home, ".dnd", "data"),
            os.path.join(home, "data"),
        ],
        "data",
    )
    tmp_dir = _first_writable(
        [
            os.environ.get("DND_TMP_DIR", ""),
            os.environ.get("TMPDIR", ""),
            os.path.join(data_dir, "tmp"),
            os.path.join(home, "tmp"),
        ],
        "tmp",
    )
    log_dir = _first_writable(
        [
            os.environ.get("DND_LOG_DIR", ""),
            os.path.join(data_dir, "logs"),
            os.path.join(home, "logs"),
        ],
        "logs",
    )

    # Make Python/tempfile and child processes use a writable temp directory.
    for key in ("TMPDIR", "TMP", "TEMP"):
        os.environ[key] = tmp_dir
    tempfile.tempdir = tmp_dir

    os.environ.setdefault("DND_DATA_DIR", data_dir)
    os.environ.setdefault("DND_TMP_DIR", tmp_dir)
    os.environ.setdefault("DND_LOG_DIR", log_dir)

    _RUNTIME = {
        "base_dir": base,
        "data_dir": data_dir,
        "tmp_dir": tmp_dir,
        "log_dir": log_dir,
    }
    return dict(_RUNTIME)


def _read_meminfo() -> Dict[str, int]:
    out: Dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                key, _, rest = line.partition(":")
                if key in {"MemTotal", "MemFree", "MemAvailable", "SwapTotal", "SwapFree"}:
                    out[key] = int(rest.strip().split()[0]) * 1024
    except Exception:
        pass
    return out


def _disk(path: str) -> Dict[str, int]:
    try:
        du = shutil.disk_usage(path)
        return {"total": du.total, "used": du.used, "free": du.free}
    except Exception:
        return {}


def _writable(path: str) -> bool:
    return _try_writable_dir(path) is not None


def diagnostics(base_dir: Optional[str] = None) -> Dict[str, Any]:
    """Return safe, non-secret runtime diagnostics."""
    rt = ensure_runtime(base_dir)
    return {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "cwd": os.getcwd(),
        "base_dir": rt["base_dir"],
        "data_dir": rt["data_dir"],
        "tmp_dir": rt["tmp_dir"],
        "log_dir": rt["log_dir"],
        "writable": {
            "data_dir": _writable(rt["data_dir"]),
            "tmp_dir": _writable(rt["tmp_dir"]),
            "log_dir": _writable(rt["log_dir"]),
        },
        "disk": {
            "data_dir": _disk(rt["data_dir"]),
            "tmp_dir": _disk(rt["tmp_dir"]),
        },
        "memory": _read_meminfo(),
        "tools": {name: shutil.which(name) for name in (
            "python3", "git", "cloudflared", "curl", "bash", "sh"
        )},
    }


def check_runtime(base_dir: Optional[str] = None) -> Dict[str, Any]:
    """Small health check used by /healthz and doctor.py."""
    diag = diagnostics(base_dir)
    problems = []
    for name, ok in diag["writable"].items():
        if not ok:
            problems.append(f"{name} is not writable")
    if diag["disk"].get("data_dir", {}).get("free", 0) < 50 * 1024 * 1024:
        problems.append("less than 50MB free in data_dir")
    return {"ok": not problems, "problems": problems, "diagnostics": diag}
