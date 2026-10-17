"""Discover trusted, opt-in ai_interfaces workbenches from read-only roots."""
import importlib.util
import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from ai_interfaces import BaseVisionModel

ROOT = Path(os.environ.get("TRAINING_WORKSPACES_ROOT", "/workspaces"))
MARKER = "ai-workbench.json"
KEY = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
SKIP = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
_CACHE = {}
_CACHE_LOCK = threading.Lock()
_SCAN_LOCK = threading.Lock()
INSPECTION_TIMEOUT = max(1, float(os.getenv("TRAINING_WORKBENCH_INSPECTION_TIMEOUT", "30")))
CACHE_SECONDS = max(1, float(os.getenv("TRAINING_WORKBENCH_CACHE_SECONDS", "300")))

INSPECTOR = r'''
import importlib.util, inspect, json, sys
from dataclasses import asdict
from pathlib import Path
from ai_interfaces import BaseModelConfig, BaseVisionModel
file, symbol = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(file.parent))
spec = importlib.util.spec_from_file_location("ai_workbench_inspection", file)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
model = getattr(module, symbol)
if not inspect.isclass(model) or not issubclass(model, BaseVisionModel) or model is BaseVisionModel:
    raise TypeError("entrypoint must export a BaseVisionModel subclass")
if inspect.isabstract(model): raise TypeError("model class has unimplemented abstract methods")
config = getattr(model, "config_type", None)
if not inspect.isclass(config) or not issubclass(config, BaseModelConfig):
    raise TypeError("model must declare a BaseModelConfig subclass as config_type")
print(json.dumps({"descriptor": asdict(model.descriptor()), "config_schema": config.model_json_schema()}))
'''


def _manifest(directory):
    marker = directory / MARKER
    try:
        if marker.stat().st_size > 16 * 1024: raise ValueError("workbench marker exceeds 16 KiB")
        data = json.loads(marker.read_text())
        entrypoint = data.get("entrypoint", "ai_workbench.py:MODEL_CLASS")
        filename, symbol = entrypoint.split(":", 1)
        if Path(filename).name != filename or not filename.endswith(".py") or not KEY.fullmatch(symbol):
            raise ValueError("entrypoint must look like ai_workbench.py:MODEL_CLASS")
        source = (directory / filename).resolve()
        source.relative_to(directory.resolve())
        if not source.is_file(): raise ValueError(f"entrypoint file {filename} does not exist")
        result = subprocess.run([sys.executable, "-I", "-c", INSPECTOR, str(source), symbol],
                                capture_output=True, text=True, timeout=INSPECTION_TIMEOUT, cwd=directory)
        if result.returncode: raise ValueError((result.stderr.strip().splitlines() or ["inspection failed"])[-1])
        inspected = json.loads(result.stdout)
        descriptor = inspected["descriptor"]
        if descriptor.get("task") not in {"image_classification", "object_detection", "anomaly_detection"}:
            raise ValueError("descriptor task must be image_classification, object_detection, or anomaly_detection")
        identity = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:12]
        key = f"workspace:{identity}:{descriptor['key']}"
        return {**descriptor, "key": key, "workspace": directory.name, "path": str(directory),
                "entrypoint": entrypoint, "config_schema": inspected["config_schema"], "available": True}
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        if isinstance(exc, subprocess.TimeoutExpired):
            exc = ValueError(f'Workbench inspection exceeded {INSPECTION_TIMEOUT:g}s; increase TRAINING_WORKBENCH_INSPECTION_TIMEOUT for slow imports')
        return {"key": f"invalid:{directory.name}", "name": directory.name, "task": "unknown",
                "description": "Workbench could not be loaded", "workspace": directory.name,
                "path": str(directory), "available": False, "reason": str(exc)[:500], "config_schema": {}}


def discover_workbenches(root=ROOT, refresh=False):
    # A capability request must not launch another set of heavy model importers
    # while a preceding request is still refreshing the same catalog.
    with _SCAN_LOCK:
        return _discover_workbenches(root, refresh)


def _discover_workbenches(root=ROOT, refresh=False):
    root = Path(root).resolve()
    if not root.is_dir(): return []
    cache_key = str(root)
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and not refresh and time.monotonic() - cached[0] < CACHE_SECONDS: return cached[1]
    markers = []
    for current, directories, files in os.walk(root):
        relative = Path(current).relative_to(root)
        depth = len(relative.parts)
        directories[:] = [] if depth >= 6 else [item for item in directories if item not in SKIP and not item.startswith(".")]
        if MARKER in files: markers.append(Path(current) / MARKER)
        if len(markers) >= 100: break
    markers.sort()
    results = [_manifest(marker.parent) for marker in markers]
    with _CACHE_LOCK: _CACHE[cache_key] = (time.monotonic(), results)
    return results


def load_model(workbench):
    """Load a previously discovered, root-contained workbench for an explicit run."""
    directory = Path(workbench["path"]).resolve(); directory.relative_to(ROOT.resolve())
    filename, symbol = workbench["entrypoint"].split(":", 1)
    source = (directory / filename).resolve(); source.relative_to(directory)
    spec = importlib.util.spec_from_file_location(f"ai_workbench_{directory.name}", source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    model = getattr(module, symbol)
    if not inspect.isclass(model) or not issubclass(model, BaseVisionModel) or inspect.isabstract(model):
        raise TypeError("Workbench model no longer satisfies ai_interfaces")
    return model


def find_workbench(key):
    return next((item for item in discover_workbenches() if item["key"] == key and item["available"]), None)
