"""Optional native-app adapters. Desktop applications and licenses are not bundled."""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from .handoff import build_jsx
from .media import FXError, Runner, absolute_path, atomic_bytes, read_json
from .plan import integer, number


def resolve_import(xml: Path, *, render_dir: Path | None = None,
                   render_preset: str | None = None, timeout: int = 1800) -> str:
    number(timeout, .1, 86400, "Timeout")
    xml = absolute_path(xml, strict=True)
    if render_dir and not render_preset:
        raise FXError("Native Resolve rendering requires --render-preset from your installed presets")
    paths = [os.environ.get("RESOLVE_SCRIPT_API", "")]
    if sys.platform == "win32":
        paths += [str(Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) /
                      "Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting"),
                  "C:/Program Files/Blackmagic Design/DaVinci Resolve/ResolvePython/lib/modules"]
    elif sys.platform == "darwin":
        paths += ["/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"]
    else:
        paths += ["/opt/resolve/Developer/Scripting"]
    for base in paths:
        if base:
            sys.path.extend([base, str(Path(base) / "Modules")])
    try:
        module = importlib.import_module("DaVinciResolveScript")
        resolve = module.scriptapp("Resolve")
    except (ImportError, OSError) as exc:
        raise FXError("Resolve API unavailable. Set RESOLVE_SCRIPT_API/LIB and use a supported installation.") from exc
    if not resolve:
        raise FXError("Start Resolve and enable Local external scripting in a supported edition")
    manager = resolve.GetProjectManager()
    if not manager:
        raise FXError("Resolve project manager is unavailable")
    name = "AutoFX_" + uuid.uuid4().hex[:12]
    project = manager.CreateProject(name)
    if not project:
        raise FXError("Resolve could not create a new project; close modal dialogs and retry")
    pool = project.GetMediaPool()
    if not pool:
        raise FXError(f"Resolve media pool is unavailable in {name}")
    timeline = pool.ImportTimelineFromFile(str(xml))
    if not timeline or not manager.SaveProject():
        raise FXError(f"Resolve import/save failed in new project {name}")
    if render_dir:
        render_dir.mkdir(parents=True, exist_ok=True)
        if not project.LoadRenderPreset(render_preset):
            raise FXError(f"Resolve render preset not found: {render_preset}")
        if not project.SetRenderSettings({"TargetDir": str(render_dir.resolve()),
                                          "CustomName": name, "SelectAllFrames": True}):
            raise FXError("Resolve rejected render settings")
        job = project.AddRenderJob()
        if not job or not project.StartRendering(job):
            raise FXError("Resolve could not start the render job")
        deadline = time.monotonic() + timeout
        try:
            while project.IsRenderingInProgress():
                if time.monotonic() > deadline:
                    raise FXError("Resolve render exceeded the timeout")
                time.sleep(.25)
        except BaseException:
            project.StopRendering()
            raise
        status = project.GetRenderJobStatus(job)
        if not isinstance(status, dict) or status.get("JobStatus") != "Complete":
            raise FXError(f"Resolve render failed: {status}")
    return name


def after_effects(manifest: Path, executable: Path, *, project: Path | None = None,
                  timeout: float = 120) -> Path:
    number(timeout, .1, 86400, "Timeout")
    if sys.platform not in ("win32", "darwin"):
        raise FXError("Native After Effects is supported on Windows and macOS only")
    payload = read_json(manifest)
    for key in ("master", "project", "clips", "fps", "width", "height", "duration", "name"):
        if key not in payload:
            raise FXError(f"AE manifest is missing: {key}")
    for key in ("master", "project"):
        if not isinstance(payload[key], str) or not payload[key]:
            raise FXError(f"AE {key} path must be a nonempty string")
    if not isinstance(payload["name"], str) or not payload["name"]:
        raise FXError("AE composition name must be a nonempty string")
    number(payload["duration"], .01, 600, "AE duration")
    number(payload["fps"], 1, 120, "AE FPS")
    for key in ("width", "height"):
        integer(payload[key], 64, 4096, f"AE {key}")
    if not isinstance(payload["clips"], list) or not 1 <= len(payload["clips"]) <= 4096:
        raise FXError("AE manifest must contain 1–4096 clips")
    absolute_path(Path(payload["master"]), strict=True)
    for clip in payload["clips"]:
        if not isinstance(clip, dict) or not isinstance(clip.get("path"), str):
            raise FXError("Invalid AE clip")
        absolute_path(Path(clip["path"]), strict=True)
        number(clip.get("start"), 0, payload["duration"], "AE clip start")
        length = number(clip.get("duration"), .001, 600, "AE clip duration")
        if clip["start"] + length > payload["duration"] + .000001:
            raise FXError("AE clip extends beyond the composition")
    if project:
        payload["project"] = str(project.resolve())
    target = Path(payload["project"])
    if target.suffix.lower() != ".aep" or target.exists():
        raise FXError("Choose a new .aep output path")
    target.parent.mkdir(parents=True, exist_ok=True)
    executable = executable.resolve(strict=True)
    token = uuid.uuid4().hex
    folder = manifest.resolve().parent
    status_file = folder / f"ae_status_{token}.txt"
    script = folder / f"ae_launch_{token}.jsx"
    atomic_bytes(script, build_jsx(payload, status_file).encode("utf-8"))
    # AfterFX is a GUI application. Do not wait for its lifetime to end.
    child = subprocess.Popen([str(executable), "-r", str(script)], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if status_file.exists():
            status = status_file.read_text(encoding="utf-8-sig")
            if status.startswith("OK\n") and target.is_file():
                return target
            if status.startswith("ERROR\n"):
                raise FXError(status[6:])
        if child.poll() not in (None, 0):
            raise FXError(f"AfterFX launcher exited with {child.returncode}")
        time.sleep(.2)
    raise FXError("AE did not acknowledge the script. Check modal dialogs and scripting file access settings.")


def aerender(executable: Path, project: Path, output: Path, template: str,
             comp: str = "AutoFX", timeout: int = 1800) -> Path:
    number(timeout, .1, 86400, "Timeout")
    if not isinstance(template, str) or not template.strip():
        raise FXError("An installed output-module template name is required")
    if sys.platform not in ("win32", "darwin"):
        raise FXError("Native Adobe rendering requires Windows or macOS")
    if output.exists():
        raise FXError("Adobe output exists; select a new filename")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    Runner()([str(executable.resolve(strict=True)), "-project", str(project.resolve(strict=True)),
              "-comp", comp, "-OMtemplate", template, "-output", str(output)], timeout=timeout)
    if not output.is_file() or output.stat().st_size == 0:
        raise FXError("aerender returned without a nonempty output file")
    return output
