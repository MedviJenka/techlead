"""The API image has no CrewAI (MAIN_PLAN §65): importing the API must never load it, even indirectly."""

import subprocess
import sys

from tests.platform.conftest import ROOT

# Runs in a fresh interpreter, with the worker-only packages made unimportable.
_SCRIPT = """
import builtins
import os
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ["LOGFIRE_TOKEN"] = ""
os.environ["LOGFIRE_SEND_TO_LOGFIRE"] = "false"
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split(".")[0] in {"crewai", "boto3", "botocore"}:
        raise ImportError(f"{name} is not installed in the API image")
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
import app.main
"""


def test_api_starts_without_the_worker_dependencies() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=120, check=False
    )
    assert result.returncode == 0, result.stderr[-2000:]
