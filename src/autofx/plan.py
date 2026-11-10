"""Deterministic editorial planning; no assert-based production validation."""
from __future__ import annotations

import math
from pathlib import Path
import re

from .media import FXError, audio_present, fingerprint, inspect, onsets, scene_points

PRESETS = {
    "clean": {"cut": 1.8, "speed": 1.0, "zoom": .02, "flash": False},
    "hype": {"cut": .65, "speed": 1.15, "zoom": .10, "flash": True},
    "cinematic": {"cut": 2.5, "speed": .85, "zoom": .04, "flash": False},
}
FPS = (24, 25, 30, 50, 60)


def number(value, low: float, high: float, label: str) -> float:
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and low <= value <= high
    except OverflowError:
        valid = False
    if not valid:
        raise FXError(f"{label} must be a finite number between {low} and {high}")
    return float(value)


def integer(value, low: int, high: int, label: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise FXError(f"{label} must be an integer between {low} and {high}")
    return value


def identity(record: dict) -> None:
    if not isinstance(record, dict) or not isinstance(record.get("path"), str):
        raise FXError("Media identity must contain an absolute path")
    if not Path(record["path"]).is_absolute():
        raise FXError("Media paths must be absolute")
    integer(record.get("size"), 1, 10**15, "Media size")
    integer(record.get("mtime_ns"), 0, 10**25, "Media modification time")
    if not re.fullmatch(r"[a-f0-9]{64}", str(record.get("sha256", ""))):
        raise FXError("Media identity must contain a SHA-256 digest")


def validate(plan: dict) -> None:
    if not isinstance(plan, dict):
        raise FXError("Plan must be a JSON object")
    try:
        if type(plan["schema"]) is not int or plan["schema"] != 2:
            raise FXError("Unsupported plan schema; regenerate with AutoFX 0.2")
        if plan["preset"] not in PRESETS or plan["fit"] not in ("cover", "contain"):
            raise FXError("Unknown preset or fit mode")
        fps = integer(plan["fps"], 24, 60, "FPS")
        if fps not in FPS:
            raise FXError(f"FPS must be one of {FPS}")
        for key in ("width", "height"):
            if integer(plan[key], 64, 4096, key) % 2:
                raise FXError(f"{key} must be even")
        total = integer(plan["frames"], 1, 600 * fps, "Frame count")
        if not isinstance(plan["sources"], list) or not 1 <= len(plan["sources"]) <= 128:
            raise FXError("Provide between 1 and 128 sources")
        for source in plan["sources"]:
            identity(source)
            number(source["duration"], .2, 7 * 86400, "Source duration")
            integer(source["video_stream"], 0, 1024, "Video stream")
            if source["audio_stream"] is not None:
                integer(source["audio_stream"], 0, 1024, "Audio stream")
            if source.get("hdr"):
                raise FXError("HDR input requires a separate color-managed SDR conversion")
        if plan["music"] is not None:
            identity(plan["music"])
        if not isinstance(plan["clips"], list) or not 1 <= len(plan["clips"]) <= 4096:
            raise FXError("Invalid clip count")
        cursor = 0
        for clip in plan["clips"]:
            index = integer(clip["source"], 0, len(plan["sources"]) - 1, "Source index")
            count = integer(clip["frames"], 1, total, "Clip frames")
            if integer(clip["timeline_frame"], 0, total, "Clip start") != cursor:
                raise FXError("Timeline has a gap or overlap")
            speed = number(clip["speed"], .01, 16, "Speed")
            start = number(clip["in"], 0, 7 * 86400, "Source in point")
            number(clip["zoom"], 0, .5, "Zoom")
            if type(clip["flash"]) is not bool:
                raise FXError("Flash must be a boolean")
            if start + count / fps * speed > plan["sources"][index]["duration"] + .001:
                raise FXError("A clip extends past its source")
            cursor += count
        if cursor != total:
            raise FXError("Timeline frame total does not match clips")
    except (KeyError, TypeError, IndexError) as exc:
        raise FXError(f"Malformed plan: {exc}") from exc


def create(paths: list[Path], *, duration: float = 15, fps: int = 30,
           width: int = 1080, height: int = 1920, preset: str = "hype",
           music: Path | None = None, analyze: bool = True, fit: str = "cover") -> dict:
    number(duration, .2, 600, "Duration")
    if preset not in PRESETS or fit not in ("cover", "contain"):
        raise FXError("Unknown preset or fit mode")
    if type(fps) is not int or fps not in FPS:
        raise FXError(f"FPS must be one of {FPS}")
    for key, value in (("width", width), ("height", height)):
        if integer(value, 64, 4096, key) % 2:
            raise FXError(f"{key} must be even")
    if not 1 <= len(paths) <= 128:
        raise FXError("Provide between 1 and 128 videos")
    sources = [inspect(path) for path in paths]
    if any(source["duration"] < .2 for source in sources):
        raise FXError("Sources must be at least 0.2 seconds long")
    music_record = None
    if music:
        if not audio_present(music):
            raise FXError("Music file has no readable audio stream")
        music_record = fingerprint(music)
    style = PRESETS[preset]
    scenes = [scene_points(Path(s["path"]), s["duration"]) if analyze else [] for s in sources]
    peaks = onsets(music, duration) if analyze and music else []
    frames = round(duration * fps)
    boundaries = [0]
    while boundaries[-1] < frames:
        target = boundaries[-1] / fps + style["cut"]
        nearby = [peak for peak in peaks if abs(peak - target) < style["cut"] * .3]
        seconds = min(nearby, key=lambda peak: abs(peak - target)) if nearby else target
        boundary = min(frames, max(boundaries[-1] + 1, round(seconds * fps)))
        if 0 < frames - boundary < max(2, round(.12 * fps)):
            boundary = frames
        boundaries.append(boundary)
    clips = []
    for i, (a, b) in enumerate(zip(boundaries, boundaries[1:])):
        index = i % len(sources)
        source = sources[index]
        speed = style["speed"] if i % 3 == 1 else 1.0
        speed = min(speed, (source["duration"] - .05) / ((b - a) / fps))
        room = max(0., source["duration"] - (b - a) / fps * speed - .05)
        choices = [point for point in scenes[index] if point <= room]
        start = choices[(i // len(sources)) % len(choices)] if choices else (i * 1.731) % max(room, .000001)
        clips.append({"source": index, "in": start, "frames": b - a,
                      "timeline_frame": a, "speed": speed, "zoom": style["zoom"],
                      "flash": bool(style["flash"] and i > 0)})
    result = {"schema": 2, "preset": preset, "fit": fit, "fps": fps,
              "width": width, "height": height, "frames": frames,
              "sources": sources, "clips": clips, "music": music_record,
              "analysis": {"scene_points": scenes, "music_onsets": peaks}}
    validate(result)
    return result
