"""Load the pinned Easel runtime inside CreatorOS without sharing user state."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "vendor" / "easel"
RUNTIME = Path(os.environ.get("CREATOROS_RUNTIME_ROOT", str(ROOT / "runtime"))).resolve()
RUNTIME.mkdir(parents=True, exist_ok=True)
for value in (str(VENDOR), str(VENDOR / "scripts"), str(VENDOR / "skills" / "shared" / "scripts")):
    if value not in sys.path:
        sys.path.insert(0, value)
os.environ.setdefault("CREATOROS_RUNTIME_ROOT", str(RUNTIME))
os.environ["EASEL_OPENCLAW_STATE_DIR"] = str(RUNTIME / "openclaw")
os.environ["OPENCLAW_STATE_DIR"] = str(RUNTIME / "openclaw")
os.environ["OPENCLAW_CONFIG_PATH"] = str(RUNTIME / "openclaw" / "openclaw.json")
os.environ["EASEL_OPENCLAW_WORKSPACE"] = str(RUNTIME / "openclaw" / "workspace")
os.environ["CREATOROS_BROWSER_PROFILES"] = str(RUNTIME / "browser-profiles")
os.environ.setdefault("EASEL_CHAT_TRANSPORT", "http")

_module_path = VENDOR / "web" / "app.py"
_spec = importlib.util.spec_from_file_location("creatoros_vendored_easel_web", _module_path)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"无法加载官方 Easel runtime: {_module_path}")
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
official_app = _module.app
