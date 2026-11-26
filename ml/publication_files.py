"""Commit a complete local artifact under an immutable filename."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def commit_exclusive(destination, payload):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=destination.parent, prefix=".staged-", delete=False) as handle:
        staged = Path(handle.name)
    try:
        staged.write_text(payload, encoding="utf8")
        os.link(staged, destination)
    finally:
        staged.unlink()
