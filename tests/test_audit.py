"""Regression cases found by reviewing failure boundaries, not just happy paths."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import MagicMock, patch
import wave

from autofx.media import FXError, Runner, ffmpeg, temporary_directory, write_json
from autofx.native import aerender, after_effects
from autofx.render import verify_wav


class AuditTests(unittest.TestCase):
    def setUp(self):
        context = temporary_directory()
        self.root = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def test_truncated_pcm_payload_is_rejected_even_with_valid_header(self):
        path = self.root / "truncated.wav"
        with wave.open(str(path), "wb") as stream:
            stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
            stream.writeframes(b"\0" * 48000 * 4)
        path.write_bytes(path.read_bytes()[:-400])
        with self.assertRaises(FXError):
            verify_wav(path, 48000)

    def test_relative_ffmpeg_override_is_resolved_before_worker_changes_directory(self):
        with patch.dict(os.environ, {"AUTOFX_FFMPEG": "relative/ffmpeg.exe"}), \
                patch("autofx.media.shutil.which", return_value="relative/ffmpeg.exe"):
            self.assertTrue(Path(ffmpeg()).is_absolute())

    def test_runner_rejects_boolean_and_unrepresentable_timeouts(self):
        for timeout in (True, False, 10**400):
            with self.subTest(timeout=str(timeout)[:20]), self.assertRaises(FXError):
                Runner()([sys.executable, "-c", "pass"], timeout=timeout)

    def test_ae_relative_media_paths_are_anchored_to_manifest(self):
        for name in ("clip.mov", "master.mp4", "afterfx.exe"):
            (self.root / name).write_bytes(b"fixture")
        payload = {"name": "Test", "width": 320, "height": 180, "fps": 30,
                   "duration": 1., "master": "master.mp4", "project": "native.aep",
                   "clips": [{"path": "clip.mov", "start": 0., "duration": 1.}]}
        manifest = self.root / "after_effects.json"
        write_json(manifest, payload)
        seen = []

        def launch(args, **kwargs):
            script = Path(args[2]).read_text(encoding="utf-8")
            data = json.loads(re.search(r"var d = (.*);", script).group(1))
            seen.append(data)
            Path(data["project"]).write_bytes(b"fake AEP")
            Path(data["status"]).write_text("OK\n" + data["project"], encoding="utf-8")
            return MagicMock(poll=lambda: 0)

        with patch("autofx.native.sys.platform", "win32"), \
                patch("autofx.native.subprocess.Popen", side_effect=launch):
            project = after_effects(manifest, self.root / "afterfx.exe")
        self.assertEqual(project, self.root / "native.aep")
        self.assertEqual(Path(seen[0]["master"]), self.root / "master.mp4")
        self.assertEqual(Path(seen[0]["clips"][0]["path"]), self.root / "clip.mov")

    def test_aerender_failure_does_not_publish_partial_output(self):
        project, executable = self.root / "input.aep", self.root / "aerender.exe"
        project.write_bytes(b"project")
        executable.write_bytes(b"executable fixture")
        output = self.root / "native.mov"

        def fail(args, **kwargs):
            Path(args[args.index("-output") + 1]).write_bytes(b"partial render")
            raise FXError("Renderer failed")

        with patch("autofx.native.sys.platform", "win32"), \
                patch("autofx.native.Runner", return_value=fail), self.assertRaises(FXError):
            aerender(executable, project, output, "Lossless")
        self.assertFalse(output.exists())

    def test_stream_selection_ignores_cover_art(self):
        from autofx.media import stream_details
        stderr = (b"Stream #0:0: Video: mjpeg, yuvj420p, 100x100 (attached pic)\n"
                  b"Stream #0:1: Video: h264, yuv420p, 320x180 (default)\n"
                  b"Stream #0:2: Audio: aac, 48000 Hz, stereo\n")
        with patch("autofx.media.ffmpeg", return_value="ffmpeg"), \
                patch("autofx.media.Runner", return_value=lambda *a, **k: (b"", stderr)):
            details = stream_details(self.root / "input.mp4")
        self.assertEqual(details["video_stream"], 1)

    def test_multiple_primary_video_streams_are_not_silently_mixed(self):
        from autofx.media import stream_details
        stderr = (b"Stream #0:0: Video: h264, 320x180\n"
                  b"Stream #0:1: Video: h264, 640x360 (default)\n")
        with patch("autofx.media.ffmpeg", return_value="ffmpeg"), \
                patch("autofx.media.Runner", return_value=lambda *a, **k: (b"", stderr)), \
                self.assertRaises(FXError):
            stream_details(self.root / "multiple.mp4")

    def test_publication_is_exclusive_and_preserves_competing_writer(self):
        from autofx.media import publish_file
        staged, target = self.root / "staged.mp4", self.root / "target.mp4"
        staged.write_bytes(b"new master")
        target.write_bytes(b"another writer")
        with self.assertRaises(FXError):
            publish_file(staged, target)
        self.assertEqual(target.read_bytes(), b"another writer")
        self.assertEqual(staged.read_bytes(), b"new master")
        publish_file(staged, target, overwrite=True)
        self.assertEqual(target.read_bytes(), b"new master")
        self.assertFalse(staged.exists())

    def test_publication_creates_complete_output(self):
        from autofx.media import publish_file
        staged, target = self.root / "staged.mov", self.root / "target.mov"
        staged.write_bytes(b"complete movie")
        publish_file(staged, target)
        self.assertEqual(target.read_bytes(), b"complete movie")
        self.assertFalse(staged.exists())

    def test_aerender_success_publishes_staged_file(self):
        project, executable = self.root / "input.aep", self.root / "aerender.exe"
        project.write_bytes(b"project")
        executable.write_bytes(b"executable fixture")
        output = self.root / "native.mov"
        seen = []

        def complete(args, **kwargs):
            staged = Path(args[args.index("-output") + 1])
            self.assertNotEqual(staged, output)
            self.assertEqual(staged.suffix, ".mov")
            staged.write_bytes(b"completed render")
            seen.append(staged)
            return b"", b""

        with patch("autofx.native.sys.platform", "win32"), \
                patch("autofx.native.Runner", return_value=complete):
            result = aerender(executable, project, output, "Lossless")
        self.assertEqual(result, output)
        self.assertEqual(output.read_bytes(), b"completed render")
        self.assertFalse(seen[0].exists())

    def test_handoff_refuses_missing_clip_instead_of_truncating_zip(self):
        from autofx.handoff import export
        from test_unit import fixture
        plan = fixture(self.root)
        with self.assertRaises(FXError):
            export(plan, [], self.root, self.root / "master.mp4")


if __name__ == "__main__":
    unittest.main()
