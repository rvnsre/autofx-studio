# 0.2.0

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
