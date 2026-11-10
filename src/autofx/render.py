"""Resumable render engine with independent frame-exact video and PCM audio."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import hashlib
import json
import logging
import os
from pathlib import Path
import time
import uuid
import wave

from . import __version__
from .assets import cube, sfx
from .media import (FXError, Runner, absolute_path, decode_check, ffmpeg, inspect, read_json,
                    publish_file, sha256, temporary_directory, verify_identity, write_json)
from .plan import integer, number, validate

LOG = logging.getLogger(__name__)
ENCODERS = {
    "cpu": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"],
    "nvenc": ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20"],
    "qsv": ["-c:v", "h264_qsv", "-global_quality", "20"],
    "amf": ["-c:v", "h264_amf", "-quality", "balanced", "-b:v", "12M"],
    "videotoolbox": ["-c:v", "h264_videotoolbox", "-b:v", "12M"],
}
RATE = 48000


def tempo(speed: float) -> str:
    number(speed, .01, 16, "Speed")
    filters = []
    while speed < .5:
        filters.append("atempo=0.5")
        speed *= 2
    while speed > 2:
        filters.append("atempo=2")
        speed /= 2
    return ",".join(filters + [f"atempo={speed:.12f}"])


@contextmanager
def output_lock(output: Path):
    lock = output.with_name(output.name + ".autofx.lock")
    token = uuid.uuid4().hex
    payload = {"pid": os.getpid(), "token": token, "output": str(output),
               "created_unix": time.time()}
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise FXError(f"Output is locked: {lock}. If no render is running, remove this stale lock.") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        yield
    finally:
        # Never delete a replacement lock belonging to a different process.
        try:
            if read_json(lock).get("token") == token:
                lock.unlink()
        except (OSError, ValueError, FXError):
            LOG.warning("Could not release output lock: %s", lock)


def verify_wav(path: Path, samples: int) -> None:
    try:
        with wave.open(str(path), "rb") as stream:
            if (stream.getnframes() != samples or stream.getframerate() != RATE
                    or stream.getnchannels() != 2 or stream.getsampwidth() != 2
                    or stream.getcomptype() != "NONE"):
                raise FXError(f"PCM audio validation failed: {path}")
            remaining = samples
            while remaining:
                block = stream.readframes(min(remaining, 65536))
                if not block or len(block) % 4:
                    raise FXError(f"Truncated PCM payload: {path}")
                remaining -= len(block) // 4
    except (wave.Error, EOFError) as exc:
        raise FXError(f"Invalid WAV container: {path}: {exc}") from exc


def video_ok(path: Path, plan: dict, count: int) -> bool:
    metadata = inspect(path, identity=False)
    return (metadata["frames"] == count and abs(metadata["fps"] - plan["fps"]) < .001
            and metadata["width"] == plan["width"] and metadata["height"] == plan["height"])


def video_filter(plan: dict, clip: dict) -> str:
    width, height, fps = plan["width"], plan["height"], plan["fps"]
    result = f"setpts=(PTS-STARTPTS)/{clip['speed']:.12f},fps={fps},"
    if plan["fit"] == "cover":
        result += (f"scale=w='if(gte(dar,{width}/{height}),ceil({height}*dar/2)*2,{width})':"
                   f"h='if(gte(dar,{width}/{height}),{height},ceil({width}/dar/2)*2)',"
                   f"setsar=1,crop={width}:{height},")
    else:
        result += (f"scale=w='if(gte(dar,{width}/{height}),{width},max(2,floor({height}*dar/2)*2))':"
                   f"h='if(gte(dar,{width}/{height}),max(2,floor({width}/dar/2)*2),{height})',"
                   f"setsar=1,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,")
    result += "setsar=1,"
    if clip["zoom"]:
        result += (f"zoompan=z='1+{clip['zoom']}*on/{max(1, clip['frames'] - 1)}':"
                   f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:"
                   f"s={width}x{height}:fps={fps},")
    result += "lut3d=file=look.cube"
    if clip["flash"]:
        result += ",eq=brightness=0.13:enable='lt(t,0.055)'"
    # Protect the final output frame against rounding in variable-frame-rate inputs.
    return result + ",tpad=stop_mode=clone:stop_duration=1,format=yuv420p"


def render(plan: dict, output: Path, *, jobs: int = 2, encoder: str = "cpu",
           overwrite: bool = False, verify_decode: bool = True) -> dict:
    validate(plan)
    integer(jobs, 1, 8, "Jobs")
    if encoder not in ENCODERS:
        raise FXError("Unknown encoder")
    output = absolute_path(output)
    if output.suffix.lower() != ".mp4":
        raise FXError("Master output must end in .mp4")
    records = plan["sources"] + ([plan["music"]] if plan["music"] else [])
    if output in [absolute_path(Path(record["path"])) for record in records]:
        raise FXError("Output cannot overwrite source media")
    output.parent.mkdir(parents=True, exist_ok=True)
    runner = Runner()
    started = time.monotonic()
    with output_lock(output):
        if output.exists() and not overwrite:
            raise FXError("Output exists; choose a new filename or pass --overwrite")
        for record in records:
            verify_identity(record)
        digest = hashlib.sha256(json.dumps(
            {"plan": plan, "encoder": encoder, "version": __version__,
             "ffmpeg": runner([ffmpeg(), "-version"])[0].decode().splitlines()[0]},
            sort_keys=True).encode()).hexdigest()[:24]
        folder = output.parent / (output.stem + "_assets") / digest
        folder.mkdir(parents=True, exist_ok=True)
        cube(folder / "look.cube", plan["preset"])
        sfx(folder / "sfx.wav", plan)
        write_json(folder / "plan.json", plan)
        fps = plan["fps"]
        samples = plan["frames"] * RATE // fps

        def clip_render(index: int) -> tuple[Path, Path]:
            clip = plan["clips"][index]
            video = folder / f"clip_{index:05d}.mov"
            audio = folder / f"clip_{index:05d}.wav"
            marker = folder / f"clip_{index:05d}.json"
            count = clip["frames"] * RATE // fps
            if video.is_file() and audio.is_file() and marker.is_file():
                try:
                    old = read_json(marker)
                    if old["video_sha256"] == sha256(video) and old["audio_sha256"] == sha256(audio):
                        verify_wav(audio, count)
                        if video_ok(video, plan, clip["frames"]):
                            if verify_decode and not old.get("decode_verified", False):
                                decode_check(video, runner)
                                write_json(marker, dict(old, decode_verified=True))
                            LOG.info("Cache %d/%d", index + 1, len(plan["clips"]))
                            return video, audio
                except (OSError, ValueError, KeyError, FXError, wave.Error):
                    LOG.warning("Rebuilding damaged cache for clip %d", index)
            source = plan["sources"][clip["source"]]
            temporary_video = folder / f"clip_{index:05d}.partial.mov"
            temporary_audio = folder / f"clip_{index:05d}.partial.wav"
            filter_file = folder / f"filter_{index:05d}.txt"
            filter_file.write_text(video_filter(plan, clip), encoding="ascii")
            args = [ffmpeg(), "-hide_banner", "-v", "error", "-nostdin", "-y",
                    "-ss", str(clip["in"]), "-i", source["path"]]
            if source["audio_stream"] is None:
                args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                audio_map = "1:a:0"
            else:
                audio_map = f"0:{source['audio_stream']}"
            args += ["-map", f"0:{source['video_stream']}", "-an",
                     "-filter_script:v", filter_file.name, "-frames:v", str(clip["frames"]),
                     "-threads", "2", "-filter_threads", "1", *ENCODERS[encoder],
                     "-video_track_timescale", str(fps * 1024), temporary_video.name,
                     "-map", audio_map, "-vn", "-af",
                     "aresample=48000:async=1:first_pts=0," + tempo(clip["speed"]) +
                     f",apad,atrim=end_sample={count},asetpts=PTS-STARTPTS",
                     "-c:a", "pcm_s16le", "-ar", str(RATE), "-ac", "2",
                     temporary_audio.name]
            runner(args, cwd=folder)
            if not video_ok(temporary_video, plan, clip["frames"]):
                raise FXError(f"Clip {index} failed video validation")
            verify_wav(temporary_audio, count)
            if verify_decode:
                decode_check(temporary_video, runner)
            temporary_video.replace(video)
            temporary_audio.replace(audio)
            write_json(marker, {"video_sha256": sha256(video), "audio_sha256": sha256(audio),
                                "decode_verified": verify_decode})
            LOG.info("Rendered %d/%d", index + 1, len(plan["clips"]))
            return video, audio

        results = [None] * len(plan["clips"])
        pool = ThreadPoolExecutor(max_workers=jobs)
        pending = {}
        try:
            pending = {pool.submit(clip_render, i): i for i in range(len(results))}
            for future in as_completed(pending):
                results[pending[future]] = future.result()
        except BaseException:
            runner.cancel()
            for future in pending:
                future.cancel()
            raise
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        for filename, extension in (("video_concat.txt", ".mov"), ("audio_concat.txt", ".wav")):
            (folder / filename).write_text("".join(
                f"file 'clip_{i:05d}{extension}'\n" for i in range(len(results))), encoding="ascii")
        for manifest, joined in (("video_concat.txt", "joined.mov"),
                                 ("audio_concat.txt", "source_audio.wav")):
            runner([ffmpeg(), "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "1",
                    "-i", manifest, "-c", "copy", joined], cwd=folder)
        verify_wav(folder / "source_audio.wav", samples)
        args = [ffmpeg(), "-v", "error", "-nostdin", "-y", "-i", "joined.mov",
                "-i", "source_audio.wav", "-i", "sfx.wav"]
        graph = "[1:a]volume=0.8[a];[2:a]volume=0.7[b];"
        mix, count = "[a][b]", 2
        if plan["music"]:
            args += ["-stream_loop", "-1", "-i", plan["music"]["path"]]
            graph += "[3:a]aresample=48000,volume=0.25[c];"
            mix, count = "[a][b][c]", 3
        graph += (f"{mix}amix=inputs={count}:duration=first:normalize=0,"
                  f"alimiter=limit=0.95:level=0:latency=1,apad,atrim=end_sample={samples}[out]")
        with temporary_directory(output.parent) as temporary:
            staged = Path(temporary) / "master.mp4"
            runner(args + ["-filter_complex", graph, "-map", "0:v:0", "-map", "[out]",
                           "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", str(RATE),
                           "-ac", "2", "-movflags", "+faststart", str(staged)], cwd=folder)
            if not video_ok(staged, plan, plan["frames"]):
                raise FXError("Master failed frame/dimension validation")
            if verify_decode:
                decode_check(staged, runner)
            # Prepare handoff before replacing a previously valid master.
            from .handoff import export
            handoff = export(plan, [result[0] for result in results], folder, output)
            for record in records:
                verify_identity(record)
            publish_file(staged, output, overwrite=overwrite)
        report = {"version": __version__, "master": str(output), "assets": str(folder),
                  "frames": plan["frames"], "duration": plan["frames"] / fps,
                  "encoder": encoder, "jobs": jobs, "clips": len(results),
                  "elapsed_seconds": round(time.monotonic() - started, 3),
                  "master_sha256": sha256(output), "decode_verified": verify_decode,
                  "lut": str(folder / "look.cube"), "sfx": str(folder / "sfx.wav"), **handoff}
        write_json(folder / "report.json", report)
        return report
