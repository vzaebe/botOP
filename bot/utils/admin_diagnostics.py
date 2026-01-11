from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def read_last_lines(path: str, *, max_lines: int = 200, max_bytes: int = 64 * 1024) -> str:
    """
    Read last N lines of a text file efficiently.
    - Bounds by max_bytes to avoid reading huge logs on weak VPS.
    """
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return ""

    size = file_path.stat().st_size
    if size <= 0:
        return ""

    read_size = min(size, max_bytes)
    with file_path.open("rb") as f:
        f.seek(-read_size, os.SEEK_END)
        chunk = f.read(read_size)

    # Decode with replacement to avoid crashing on partial UTF-8 sequences
    text = chunk.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines).strip()


def format_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def try_read_proc_loadavg() -> Optional[str]:
    p = Path("/proc/loadavg")
    try:
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    return None


def try_read_proc_meminfo() -> Optional[str]:
    p = Path("/proc/meminfo")
    try:
        if p.exists():
            # Only a few top lines matter; keep it short.
            lines = p.read_text(encoding="utf-8").splitlines()
            head = []
            for line in lines:
                if line.startswith(("MemTotal:", "MemFree:", "MemAvailable:", "SwapTotal:", "SwapFree:")):
                    head.append(line)
            return "\n".join(head).strip()
    except Exception:
        return None
    return None

