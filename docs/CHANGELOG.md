# 0.2.1

- Preserve display aspect ratio for anamorphic sources in cover/contain filters.
- Validate WAV payload length, not only its header; report malformed/truncated containers clearly.
- Resolve relative FFmpeg executable paths before worker subprocesses change directory.
- Ignore cover-art video streams and reject ambiguous multiple-primary-video inputs.
- Reject boolean and overflowing process timeouts without leaking a traceback.
- Anchor AE manifest-relative paths and consistently normalize native executable paths.
- Stage native aerender output so failures leave no partially published destination.
- Prepare handoff before master publication and verify source hashes again afterward.
- Atomically preserve competing writers when overwrite was not requested.
- Upgrade cached decode verification and reject handoff clip-count mismatches.
- Invalidate old renderer caches through the patch version; use current SPDX package metadata.
- Expand local tests from 28 to 43, including real anamorphic and failure-path renders.

# 0.2.0

- Name the source launcher `run_autofx.py` so it does not mask the installed `autofx` package; cover editable-style import lookup in subprocess regression tests.

- Validate saved JSON plans explicitly, including NaN/Infinity, booleans used as numbers, large integers, source boundaries, gaps and overlaps.
- Track full media hashes and include music identity in render state.
- Normalize video to an integer-frame timeline and handle source/output frame-rate differences.
- Render per-clip audio as exact-length PCM, independently from video; encode AAC once in the final master.
- Generate SFX in bounded blocks and align impact onset to cuts.
- Use exclusive output locks and staged master replacement.
- Reuse complete validated cache entries and rebuild damaged or incomplete clips.
- Cancel active subprocesses and pending tasks on render failure or interruption.
- Export separate editable video cuts and finished stereo audio through FCP7 XML.
- Generate escaped AE scripts, preserve existing nonempty projects and acknowledge import via a status file.
- Require installed presets for native Resolve/aerender output and report adapter failures.
- Provide a source launcher, installable package, tests, machine-readable validation reports and a three-platform CI matrix.
