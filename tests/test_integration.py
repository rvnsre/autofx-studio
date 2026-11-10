"""Enable with AUTOFX_INTEGRATION=1. Creates media; no user's files are changed."""
from __future__ import annotations

import os
from pathlib import Path
import unittest
import wave
from unittest.mock import patch

from autofx.media import (FXError, decode_check, ffmpeg, inspect, read_json, run,
                          temporary_directory)
from autofx.plan import create
from autofx.render import render


@unittest.skipUnless(os.environ.get("AUTOFX_INTEGRATION") == "1", "Set AUTOFX_INTEGRATION=1")
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = temporary_directory()
        cls.root = cls.temporary.__enter__() / "spaces and ə"
        cls.addClassCleanup(cls.temporary.__exit__, None, None, None)
        cls.root.mkdir()
        cls.a, cls.b = cls.root / "audio.mp4", cls.root / "silent.mp4"
        common = [ffmpeg(), "-v", "error", "-nostdin", "-y"]
        run(common + ["-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30",
                      "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                      "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                      "-c:a", "aac", str(cls.a)])
        run(common + ["-f", "lavfi", "-i", "testsrc2=size=240x320:rate=25",
                      "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.b)])

    def test_mixed_audio_silent_cache_and_corruption_recovery(self):
        plan = create([self.a, self.b], duration=1.4, width=320, height=180, analyze=False)
        output = self.root / "master.mp4"
        report = render(plan, output, jobs=2)
        metadata = inspect(output, identity=False)
        self.assertEqual(metadata["frames"], 42)
        self.assertIsNotNone(metadata["audio_stream"])
        with wave.open(str(Path(report["assets"]) / "source_audio.wav"), "rb") as stream:
            self.assertEqual(stream.getnframes(), 67200)
        clip = Path(report["assets"]) / "clip_00000.mov"
        before = clip.stat().st_mtime_ns
        with self.assertRaises(FXError):
            render(plan, output)
        render(plan, output, overwrite=True)
        self.assertEqual(clip.stat().st_mtime_ns, before)
        clip.write_bytes(b"corrupt")
        render(plan, output, overwrite=True)
        self.assertGreater(clip.stat().st_size, 100)
        decode_check(output)

    def test_music_onsets_and_contain(self):
        plan = create([self.a, self.b], duration=1.1, width=320, height=180,
                      music=self.a, fit="contain", analyze=True)
        report = render(plan, self.root / "music.mp4", jobs=1)
        self.assertEqual(inspect(Path(report["master"]), identity=False)["frames"], 33)
        self.assertTrue(read_json(Path(report["assets"]) / "report.json")["decode_verified"])

    def test_other_frame_rates_and_silent_only(self):
        for fps in (24, 25, 50, 60):
            with self.subTest(fps=fps):
                plan = create([self.b], duration=.3, width=128, height=128,
                              fps=fps, analyze=False, preset="cinematic")
                report = render(plan, self.root / f"fps{fps}.mp4", jobs=1)
                self.assertEqual(inspect(Path(report["master"]), identity=False)["frames"], round(.3 * fps))

    def test_anamorphic_contain_preserves_display_aspect(self):
        import cv2
        source = self.root / "anamorphic.mp4"
        run([ffmpeg(), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
             "color=c=green:size=100x100:rate=30,drawbox=x=30:y=30:w=40:h=40:color=red:t=fill,setsar=2/1",
             "-t", "1", "-c:v", "libx264", str(source)])
        plan = create([source], duration=.3, width=200, height=200,
                      fit="contain", preset="clean", analyze=False)
        for clip in plan["clips"]:
            clip["zoom"] = 0.
        report = render(plan, self.root / "anamorphic_out.mp4", jobs=1)
        cap = cv2.VideoCapture(report["master"])
        try:
            ok, frame = cap.read()
        finally:
            cap.release()
        self.assertTrue(ok)
        self.assertLess(float(frame[10, 100].mean()), 10., "Expected top letterbox for 2:1 DAR")
        red = (frame[:, :, 2] > 170) & (frame[:, :, 1] < 80)
        ys, xs = red.nonzero()
        self.assertGreater(len(xs), 100)
        self.assertAlmostEqual((xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1), 2., delta=.15)

    def test_handoff_failure_preserves_existing_master(self):
        output = self.root / "export_failure.mp4"
        output.write_bytes(b"previous master")
        plan = create([self.a], duration=.2, width=128, height=128, analyze=False)
        with patch("autofx.handoff.export", side_effect=FXError("Simulated export failure")), \
                self.assertRaises(FXError):
            render(plan, output, jobs=1, overwrite=True)
        self.assertEqual(output.read_bytes(), b"previous master")

    def test_source_mutation_with_restored_timestamp_prevents_publication(self):
        from autofx.handoff import export as real_export
        source = self.root / "mutable.mp4"
        source.write_bytes(self.a.read_bytes())
        plan = create([source], duration=.2, width=128, height=128, analyze=False)
        before = source.stat()
        output = self.root / "mutation.mp4"

        def mutate(*args):
            result = real_export(*args)
            data = bytearray(source.read_bytes())
            data[-1] ^= 1
            source.write_bytes(data)
            os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
            return result

        with patch("autofx.handoff.export", side_effect=mutate), self.assertRaises(FXError):
            render(plan, output, jobs=1)
        self.assertFalse(output.exists())

    def test_cache_decode_verification_is_upgraded_without_reencoding(self):
        plan = create([self.a], duration=.2, width=128, height=128, analyze=False)
        output = self.root / "upgrade.mp4"
        report = render(plan, output, jobs=1, verify_decode=False)
        folder = Path(report["assets"])
        clip = folder / "clip_00000.mov"
        marker = folder / "clip_00000.json"
        before = clip.stat().st_mtime_ns
        self.assertFalse(read_json(marker)["decode_verified"])
        render(plan, output, jobs=1, overwrite=True, verify_decode=True)
        self.assertTrue(read_json(marker)["decode_verified"])
        self.assertEqual(clip.stat().st_mtime_ns, before)


if __name__ == "__main__":
    unittest.main()
