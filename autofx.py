"""Run the source checkout without installing the CLI entry point."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from autofx.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
