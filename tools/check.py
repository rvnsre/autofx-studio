"""Run meaningful tests and optionally write a machine-readable local report."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--integration", action="store_true")
    parser.add_argument("--temp-dir", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.temp_dir:
        args.temp_dir.mkdir(parents=True, exist_ok=True)
        tempfile.tempdir = str(args.temp_dir.absolute())
    os.environ["AUTOFX_INTEGRATION"] = "1" if args.integration else "0"
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"success": result.wasSuccessful(), "tests_run": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors),
              "skipped": [{"test": str(test), "reason": reason} for test, reason in result.skipped],
              "integration_requested": args.integration,
              "elapsed_seconds": round(time.monotonic() - started, 3),
              "python": platform.python_version(), "platform": platform.platform(),
              "native_applications_verified": False}
    import cv2
    import numpy
    from autofx import __version__
    report["dependencies"] = {"opencv": cv2.__version__, "numpy": numpy.__version__,
                              "autofx": __version__}
    if args.integration:
        from autofx.media import ffmpeg, run
        report["ffmpeg_version"] = run([ffmpeg(), "-version"]).decode().splitlines()[0]
    if args.report:
        from autofx.media import write_json
        write_json(args.report, report)
    print(json.dumps(report, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
