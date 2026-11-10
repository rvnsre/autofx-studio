"""Portable process execution, bounded analysis and media identity."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

import cv2
import numpy as np


class FXError(RuntimeError):
    """An expected failure which the CLI displays without a traceback."""


def absolute_path(path: Path, *, strict: bool = False) -> Path:
    """Canonicalize when allowed; some Windows sandboxes deny final-path queries.

    The fallback still uses ordinary OS stat/open permissions; it grants no access.
    """
    path = path.expanduser().absolute()
    if strict:
        path.stat()
    try:
        return path.resolve(strict=strict)
    except PermissionError:
        return path


@contextmanager
def temporary_directory(parent: Path | None = None):
    """Stage under a chosen parent and preserve inherited Windows ACLs."""
    parent = absolute_path(parent or Path(tempfile.gettempdir()))
    path = parent / ("autofx-" + uuid.uuid4().hex)
    path.mkdir(mode=0o777 if os.name == "nt" else 0o700)
    try:
        yield path
    finally:
        if path.parent != parent or not path.name.startswith("autofx-"):
            raise FXError("Refusing cleanup outside the temporary parent")
        shutil.rmtree(path)


def ffmpeg() -> str:
    override = os.environ.get("AUTOFX_FFMPEG")
    if override:
        candidate = shutil.which(override)
        if not candidate and Path(override).is_file():
            candidate = str(absolute_path(Path(override)))
        if not candidate:
            raise FXError("AUTOFX_FFMPEG must identify an existing executable")
        return str(absolute_path(Path(candidate)))
    system = shutil.which("ffmpeg")
    if system:
        return str(absolute_path(Path(system)))
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise FXError("Install FFmpeg or install this package with pip") from exc


class Runner:
    """Poll children so cancellation works inside render worker threads, too."""

    def __init__(self) -> None:
        self.cancelled = threading.Event()

    def cancel(self) -> None:
        self.cancelled.set()

    def __call__(self, args: list[str], *, cwd: Path | None = None,
                 timeout: float = 1800, check: bool = True) -> tuple[bytes, bytes]:
        try:
            valid_timeout = type(timeout) in (int, float) and math.isfinite(timeout) and timeout > 0
        except OverflowError:
            valid_timeout = False
        if not args or isinstance(args, (str, bytes)) or not valid_timeout:
            raise FXError("Process arguments and a positive finite timeout are required")
        if self.cancelled.is_set():
            raise FXError("Operation cancelled")
        started = time.monotonic()
        try:
            with subprocess.Popen(
                [str(a) for a in args], cwd=cwd, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            ) as child:
                try:
                    while True:
                        if self.cancelled.is_set():
                            raise FXError("Operation cancelled")
                        remaining = timeout - (time.monotonic() - started)
                        if remaining <= 0:
                            raise FXError(f"Process timed out after {timeout:g}s: {args[0]}")
                        try:
                            stdout, stderr = child.communicate(timeout=min(.2, remaining))
                            break
                        except subprocess.TimeoutExpired:
                            continue
                except BaseException:
                    child.kill()
                    child.communicate()
                    raise
                if check and child.returncode:
                    tail = stderr.decode("utf-8", "replace")[-8000:]
                    raise FXError(f"Process exited with {child.returncode}: {tail}")
                return stdout, stderr
        except OSError as exc:
            raise FXError(f"Cannot start {args[0]}: {exc}") from exc


def run(args: list[str], **kwargs) -> bytes:
    return Runner()(args, **kwargs)[0]


def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / (".autofx-" + uuid.uuid4().hex + ".tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                         0o666 if os.name == "nt" else 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def publish_file(staged: Path, target: Path, *, overwrite: bool = False) -> None:
    """Atomically publish on the destination filesystem, without a check/replace race.

    POSIX rename replaces existing files, so use an exclusive hard link there.
    Windows rename already fails when its destination exists. Staging must be on
    the same filesystem; callers put it under the destination parent.
    """
    try:
        if overwrite:
            os.replace(staged, target)
        elif os.name == "nt":
            os.rename(staged, target)
        else:
            os.link(staged, target)
            staged.unlink()
    except FileExistsError as exc:
        raise FXError(f"Output already exists; preserved: {target}") from exc


def write_json(path: Path, value: object) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, ensure_ascii=False,
                                  allow_nan=False) + "\n").encode("utf-8"))


def read_json(path: Path, limit: int = 16_000_000) -> dict:
    if path.stat().st_size > limit:
        raise FXError(f"JSON file is too large: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise FXError("JSON root must be an object")
    return data


def sha256(path: Path) -> str:
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise FXError(f"File changed while being read: {path}")
    return digest.hexdigest()


def fingerprint(path: Path) -> dict:
    path = absolute_path(path, strict=True)
    stat = path.stat()
    result = {"path": str(path), "size": stat.st_size,
              "mtime_ns": stat.st_mtime_ns, "sha256": sha256(path)}
    if path.stat().st_mtime_ns != stat.st_mtime_ns:
        raise FXError(f"File changed while being inspected: {path}")
    return result


def verify_identity(record: dict) -> None:
    current = fingerprint(Path(record["path"]))
    if any(current[k] != record[k] for k in ("size", "mtime_ns", "sha256")):
        raise FXError(f"Source changed; regenerate the plan: {record['path']}")


def stream_details(path: Path) -> dict:
    # No output is supplied: the nonzero FFmpeg exit is intentional. ffprobe is optional.
    _, stderr = Runner()([ffmpeg(), "-hide_banner", "-nostdin", "-i", str(path)],
                         timeout=60, check=False)
    text = stderr.decode("utf-8", "replace")
    videos = [(int(match.group(1)), line) for line in text.splitlines()
              if (match := re.search(r"Stream #0:(\d+)[^\n]*: Video:", line))
              and "attached pic" not in line.lower()]
    audios = re.findall(r"Stream #0:(\d+)[^\n]*: Audio:", text)
    if len(videos) > 1:
        raise FXError("Multiple video streams are unsupported; remux the chosen track first")
    return {"video_stream": videos[0][0] if videos else None,
            "audio_stream": int(audios[0]) if audios else None,
            "hdr": bool(videos and re.search(r"smpte2084|arib-std-b67", videos[0][1]))}


def inspect(path: Path, *, identity: bool = True) -> dict:
    path = absolute_path(path, strict=True)
    details = stream_details(path)
    if details["video_stream"] is None:
        raise FXError(f"No primary video stream found: {path}")
    cap = cv2.VideoCapture(str(path))
    try:
        fps, count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if (not cap.isOpened() or not math.isfinite(fps) or not math.isfinite(count)
                or fps <= 0 or count <= 0 or width < 1 or height < 1):
            raise FXError(f"Cannot inspect a finite video: {path}")
        result = {"path": str(path), "fps": fps, "frames": round(count),
                  "duration": count / fps, "width": width, "height": height}
    finally:
        cap.release()
    result.update(details)
    if identity:
        result.update(fingerprint(path))
    return result


def audio_present(path: Path) -> bool:
    return stream_details(path)["audio_stream"] is not None


def scene_points(path: Path, duration: float, threshold: float = .32) -> list[float]:
    """Coarse scene candidates, bounded to 2400 small frames."""
    cap = cv2.VideoCapture(str(path))
    previous = None
    result = []
    step = max(.25, duration / 2400)
    try:
        for seconds in np.arange(0, duration, step):
            cap.set(cv2.CAP_PROP_POS_MSEC, float(seconds * 1000))
            ok, frame = cap.read()
            if not ok:
                continue
            hsv = cv2.cvtColor(cv2.resize(frame, (96, 54)), cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
            cv2.normalize(hist, hist, norm_type=cv2.NORM_L1)
            if (previous is not None and
                    cv2.compareHist(previous, hist, cv2.HISTCMP_BHATTACHARYYA) > threshold):
                result.append(round(float(seconds), 6))
            previous = hist
    finally:
        cap.release()
    return result


def onsets(path: Path, duration: float) -> list[float]:
    """Energy-rise peaks, not semantic beat or downbeat recognition."""
    if not audio_present(path):
        return []
    raw = run([ffmpeg(), "-v", "error", "-nostdin", "-i", str(path),
               "-t", str(min(duration, 600)), "-vn", "-ac", "1", "-ar", "8000",
               "-f", "f32le", "-"])
    samples = np.frombuffer(raw, dtype="<f4")
    length = len(samples) // 160 * 160
    if length < 800:
        return []
    energy = np.sqrt(np.mean(samples[:length].reshape(-1, 160) ** 2, axis=1))
    flux = np.maximum(0, np.diff(energy, prepend=energy[0]))
    threshold = max(float(np.percentile(flux, 90)), .005)
    peaks = []
    for i in range(1, len(flux) - 1):
        seconds = i * .02
        if flux[i] > threshold and flux[i] >= max(flux[i - 1], flux[i + 1]):
            if not peaks or seconds - peaks[-1] >= .25:
                peaks.append(round(seconds, 6))
    return peaks


def decode_check(path: Path, runner: Runner | None = None) -> None:
    (runner or Runner())([ffmpeg(), "-v", "error", "-xerror", "-nostdin",
                          "-i", str(path), "-map", "0:v:0", "-map", "0:a:0?",
                          "-f", "null", "-"], timeout=1800)
