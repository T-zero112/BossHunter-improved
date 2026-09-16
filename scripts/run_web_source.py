from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
os.chdir(ROOT)

from bosshunter.web.server import run_server, set_base_dir  # noqa: E402


set_base_dir(ROOT)
run_server(host="127.0.0.1", port=8686, open_browser=False)
