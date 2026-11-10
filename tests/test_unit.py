from __future__ import annotations

import copy
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import wave
import xml.etree.ElementTree as ET

from autofx.assets import cube, sfx
from autofx.cli import main
from autofx.handoff import build_jsx, export
from autofx.media import (FXError, Runner, fingerprint, read_json, temporary_directory,
                          verify_identity, write_json)
from autofx.plan import create, validate
from autofx.render import output_lock, tempo, video_filter


def fixture(root: Path) -> dict:
    path = root / "input.bin"
    path.write_bytes(b"source data")
    source = {**fingerprint(path), "duration": 4., "fps": 30., "frames": 120,
              "width": 320, "height": 180, "video_stream": 0,
              "audio_stream": None, "hdr": False}
    return {"schema": 2, "preset": "hype", "fit": "cover", "fps": 30,
            "width": 320, "height": 180, "frames": 30, "sources": [source],
            "music": None, "analysis": {},
            "clips": [{"source": 0, "in": 0., "frames": 15, "timeline_frame": 0,
                       "speed": 1., "zoom": .1, "flash": False},
                      {"source": 0, "in": 1., "frames": 15, "timeline_frame": 15,
                       "speed": 1.15, "zoom": .1, "flash": True}]}


class UnitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = temporary_directory()
        self.root = self.temporary.__enter__()
        self.addCleanup(self.temporary.__exit__, None, None, None)
        self.plan = fixture(self.root)

    def test_valid_plan(self):
        validate(self.plan)

    def test_reject_corrupt_plans(self):
        edits = [
            ("schema", 1), ("fps", True), ("fps", 29), ("width", 319),
            ("height", 0), ("frames", 31), ("sources", []), ("clips", []),
            ("preset", []), ("music", {"path": "relative"}),
        ]
        for key, value in edits:
            with self.subTest(key=key, value=value):
                plan = copy.deepcopy(self.plan)
                plan[key] = value
                with self.assertRaises(FXError):
                    validate(plan)

    def test_reject_corrupt_clips(self):
        for key, value in [("source", -1), ("source", True), ("frames", 0),
                           ("speed", math.nan), ("speed", math.inf), ("speed", 10**400), ("in", -1),
                           ("in", 3.99), ("zoom", .8), ("flash", 1),
                           ("timeline_frame", 1)]:
            with self.subTest(key=key, value=value):
                plan = copy.deepcopy(self.plan)
                plan["clips"][0][key] = value
                with self.assertRaises(FXError):
                    validate(plan)

    def test_gaps_and_overlaps(self):
        for start in (14, 16):
            self.plan["clips"][1]["timeline_frame"] = start
            with self.assertRaises(FXError):
                validate(self.plan)

    def test_source_hdr_rejected(self):
        self.plan["sources"][0]["hdr"] = True
        with self.assertRaises(FXError):
            validate(self.plan)

    def test_deterministic_planning_and_short_source(self):
        source = self.plan["sources"][0] | {"duration": .2}
        with patch("autofx.plan.inspect", return_value=source):
            first = create([self.root / "input.bin"], duration=4.13,
                           width=320, height=180, analyze=False)
            second = create([self.root / "input.bin"], duration=4.13,
                            width=320, height=180, analyze=False)
        self.assertEqual(first, second)
        self.assertEqual(sum(c["frames"] for c in first["clips"]), round(4.13 * 30))
        validate(first)

    def test_reject_invalid_settings_before_media_io(self):
        for options in ({"duration": math.nan}, {"duration": -1}, {"fps": True},
                        {"width": 321}, {"preset": "unknown"}, {"fit": "stretch"}):
            with self.subTest(options=options), self.assertRaises(FXError):
                create([self.root / "missing"], **options)

    def test_identity_detects_same_size_and_timestamp_mutation(self):
        source = self.plan["sources"][0]
        path = Path(source["path"])
        path.write_bytes(b"changed dat")
        import os
        os.utime(path, ns=(source["mtime_ns"], source["mtime_ns"]))
        with self.assertRaises(FXError):
            verify_identity(source)

    def test_json_atomic_round_trip_and_shape(self):
        path = self.root / "plan.json"
        write_json(path, self.plan)
        self.assertEqual(read_json(path), self.plan)
        self.assertEqual(list(self.root.glob("*.tmp")), [])
        path.write_text("[]")
        with self.assertRaises(FXError):
            read_json(path)

    def test_tempo_decomposition(self):
        for speed in (.01, .1, .5, 1., 2., 8., 16.):
            factors = [float(part.split("=")[1]) for part in tempo(speed).split(",")]
            self.assertTrue(all(.5 <= factor <= 2 for factor in factors))
            self.assertAlmostEqual(math.prod(factors), speed, places=9)
        with self.assertRaises(FXError):
            tempo(0)

    def test_lock_exclusivity_and_cleanup(self):
        output = self.root / "out.mp4"
        with output_lock(output):
            with self.assertRaises(FXError):
                with output_lock(output):
                    self.fail("Must not acquire a second lock")
        self.assertFalse(output.with_name(output.name + ".autofx.lock").exists())

    def test_runner_timeout_and_nonzero(self):
        with self.assertRaises(FXError):
            Runner()([sys.executable, "-c", "import time; time.sleep(5)"], timeout=.1)
        with self.assertRaises(FXError):
            Runner()([sys.executable, "-c", "raise SystemExit(3)"])

    def test_runner_cancel_before_launch(self):
        runner = Runner()
        runner.cancel()
        with self.assertRaises(FXError):
            runner([sys.executable, "-c", "print('should not run')"])

    def test_lut_identity_order_and_size(self):
        path = self.root / "clean.cube"
        cube(path, "clean", 3)
        rows = path.read_text().splitlines()[4:]
        self.assertEqual(len(rows), 27)
        self.assertEqual(rows[0], "0.0000000 0.0000000 0.0000000")
        self.assertEqual(rows[1], "0.5000000 0.0000000 0.0000000")
        self.assertEqual(rows[-1], "1.0000000 1.0000000 1.0000000")
        with self.assertRaises(ValueError):
            cube(path, "clean", 1)

    def test_sfx_exact_samples_repeatability_and_signal(self):
        import numpy as np
        a, b = self.root / "a.wav", self.root / "b.wav"
        sfx(a, self.plan)
        sfx(b, self.plan)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        with wave.open(str(a), "rb") as stream:
            self.assertEqual(stream.getnframes(), 48000)
            self.assertEqual(stream.getframerate(), 48000)
            self.assertGreater(np.max(np.abs(np.frombuffer(stream.readframes(48000), dtype="<i2"))), 0)

    def test_filter_fit_and_flash(self):
        self.assertIn("crop=", video_filter(self.plan, self.plan["clips"][1]))
        self.assertIn("brightness", video_filter(self.plan, self.plan["clips"][1]))
        self.plan["fit"] = "contain"
        self.assertIn("pad=", video_filter(self.plan, self.plan["clips"][0]))

    def test_xml_has_exact_cuts_and_two_audio_channels(self):
        files = [self.root / 'special & "name.mov', self.root / "ə clip.mov"]
        report = export(self.plan, files, self.root, self.root / "master.mp4")
        root = ET.parse(report["xml"]).getroot()
        self.assertEqual(root.findtext("sequence/duration"), "30")
        clips = root.findall("sequence/media/video/track/clipitem")
        self.assertEqual([c.findtext("start") for c in clips], ["0", "15"])
        self.assertEqual(clips[0].findtext("file/name"), files[0].name)
        self.assertEqual(len(root.findall("sequence/media/audio/track")), 2)
        payload = read_json(Path(report["after_effects_manifest"]))
        self.assertEqual(payload["clips"][1]["start"], .5)

    def test_jsx_escapes_paths_and_preserves_existing_projects(self):
        payload = {"project": 'C:/quote"/a.aep', "name": "ə"}
        script = build_jsx(payload)
        self.assertIn('quote\\"', script)
        self.assertIn("app.project.numItems > 0", script)
        self.assertIn("Output AEP already exists", script)

    def test_cli_rejects_bad_lut_size(self):
        self.assertEqual(main(["lut", "-o", str(self.root / "x.cube"), "--size", "1"]), 2)


if __name__ == "__main__":
    unittest.main()
