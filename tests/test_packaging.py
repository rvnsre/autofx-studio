"""Exercise checkout imports without relying on a prepended source PYTHONPATH."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

from autofx import __version__

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_checkout_does_not_mask_the_package(self):
        # Append, rather than prepend: this reproduces editable-install lookup order.
        code = ("import sys; sys.path.append(" + repr(str(ROOT / "src")) + "); "
                "import autofx.media; from autofx import __version__; print(__version__)")
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), __version__)

    def test_source_launcher_from_checkout(self):
        result = subprocess.run([sys.executable, "run_autofx.py", "--version"], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), __version__)


if __name__ == "__main__":
    unittest.main()
