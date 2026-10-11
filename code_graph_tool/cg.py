#!/usr/bin/env python
"""Entry point: `python cg.py <command> ...`  (see `python cg.py -h`)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codegraph.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
