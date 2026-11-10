"""Terminal entry point. Progress goes to stderr; results are JSON on stdout."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import platform
import sys

from . import __version__
from .assets import cube
from .media import FXError, ffmpeg, read_json, run, write_json
from .native import aerender, after_effects, resolve_import
from .plan import PRESETS, create
from .render import ENCODERS, render


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="autofx", description="Automatic editing, SFX, LUTs and NLE handoff")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--verbose", action="store_true")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Inspect the local runtime and FFmpeg build")
    for name in ("auto", "plan"):
        p = commands.add_parser(name)
        p.add_argument("inputs", type=Path, nargs="+")
        p.add_argument("-o", "--output", type=Path, required=True)
        p.add_argument("--preset", choices=PRESETS, default="hype")
        p.add_argument("--duration", type=float, default=15)
        p.add_argument("--fps", type=int, default=30)
        p.add_argument("--width", type=int, default=1080)
        p.add_argument("--height", type=int, default=1920)
        p.add_argument("--fit", choices=("cover", "contain"), default="cover")
        p.add_argument("--music", type=Path)
        p.add_argument("--no-analyze", action="store_true")
    renderer = commands.add_parser("render", help="Render a saved, editable JSON plan")
    renderer.add_argument("plan", type=Path)
    renderer.add_argument("-o", "--output", type=Path, required=True)
    for p in (commands.choices["auto"], renderer):
        p.add_argument("--jobs", type=int, default=2)
        p.add_argument("--encoder", choices=ENCODERS, default="cpu")
        p.add_argument("--overwrite", action="store_true")
        p.add_argument("--skip-decode-check", action="store_true",
                       help="Faster; frame counts and media identities are still checked")
    p = commands.add_parser("lut")
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--preset", choices=PRESETS, default="hype")
    p.add_argument("--size", type=int, default=33)
    p = commands.add_parser("resolve")
    p.add_argument("xml", type=Path)
    p.add_argument("--render-dir", type=Path)
    p.add_argument("--render-preset")
    p.add_argument("--timeout", type=int, default=1800)
    p = commands.add_parser("after-effects")
    p.add_argument("manifest", type=Path)
    p.add_argument("--exe", type=Path, required=True)
    p.add_argument("--project", type=Path)
    p.add_argument("--timeout", type=int, default=120)
    p = commands.add_parser("aerender")
    p.add_argument("project", type=Path)
    p.add_argument("--exe", type=Path, required=True)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--template", required=True)
    p.add_argument("--comp", default="AutoFX")
    p.add_argument("--timeout", type=int, default=1800)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    try:
        if args.command == "doctor":
            exe = ffmpeg()
            encoders = run([exe, "-hide_banner", "-encoders"]).decode("utf-8", "replace")
            result = {"version": __version__, "platform": platform.platform(),
                      "python": platform.python_version(), "ffmpeg": exe,
                      "ffmpeg_version": run([exe, "-version"]).decode().splitlines()[0],
                      "compiled_encoders": {k: v[1] in encoders for k, v in ENCODERS.items()},
                      "native_adobe_platform": sys.platform in ("win32", "darwin"),
                      "note": "Compiled GPU encoders do not prove a compatible GPU/driver is available."}
        elif args.command in ("auto", "plan"):
            plan = create(args.inputs, duration=args.duration, fps=args.fps,
                          width=args.width, height=args.height, preset=args.preset,
                          music=args.music, analyze=not args.no_analyze, fit=args.fit)
            if args.command == "plan":
                if args.output.exists():
                    raise FXError("Plan output exists; choose another filename")
                write_json(args.output, plan)
                result = {"plan": str(args.output.resolve()), "frames": plan["frames"]}
            else:
                result = render(plan, args.output, jobs=args.jobs, encoder=args.encoder,
                                overwrite=args.overwrite, verify_decode=not args.skip_decode_check)
        elif args.command == "render":
            result = render(read_json(args.plan), args.output, jobs=args.jobs, encoder=args.encoder,
                            overwrite=args.overwrite, verify_decode=not args.skip_decode_check)
        elif args.command == "lut":
            if args.output.exists():
                raise FXError("LUT output exists; choose another filename")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            cube(args.output, args.preset, args.size)
            result = {"lut": str(args.output.resolve())}
        elif args.command == "resolve":
            result = {"resolve_project": resolve_import(
                args.xml, render_dir=args.render_dir, render_preset=args.render_preset,
                timeout=args.timeout)}
        elif args.command == "after-effects":
            result = {"aep": str(after_effects(args.manifest, args.exe,
                                               project=args.project, timeout=args.timeout))}
        else:
            result = {"native_render": str(aerender(args.exe, args.project, args.output,
                                                    args.template, args.comp, args.timeout))}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (FXError, OSError, ValueError) as exc:
        print(f"autofx: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("autofx: interrupted; completed cache clips can be reused", file=sys.stderr)
        return 130
