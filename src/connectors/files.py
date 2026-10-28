"""Bounded, deterministic file enumeration; configured roots are trusted, children are not."""
import fnmatch
import os
from pathlib import Path


def scan_files(root: Path, patterns, max_files: int, max_bytes: int):
    root = root.resolve()
    seen = 0
    if not root.is_dir():
        return
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            seen += 1
            if seen > max_files:
                return
            if name.startswith('.') or not any(fnmatch.fnmatch(name, p) for p in patterns):
                continue
            path = Path(directory) / name
            try:
                if not path.is_symlink() and path.resolve().is_relative_to(root) and path.is_file() and path.stat().st_size <= max_bytes:
                    yield path
            except OSError:
                continue
