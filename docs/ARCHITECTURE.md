# Architecture

The source of truth is a schema-2 JSON plan. Rendering and native application import are separate operations.

## Modules

| Module | Responsibility |
|---|---|
| `media.py` | FFmpeg resolution, cancellable processes, hashing, bounded analysis, file transactions |
| `plan.py` | Input constraints, deterministic selection, integer-frame timeline, untrusted-plan validation |
| `assets.py` | Display-referred LUT generation and original procedural SFX |
| `render.py` | Output lock, cache integrity, worker orchestration, separate video/PCM rendering and final mix |
| `handoff.py` | FCP7 XML, AE manifest and safely escaped JSX generation |
| `native.py` | Optional Resolve, AfterFX and aerender adapters |
| `cli.py` | CLI parsing, progress, JSON result output and user-facing errors |

## Timeline invariants

- Frame boundaries use integer, non-drop-frame FPS.
- The first clip starts at zero. Each following clip starts at the preceding end.
- The clip-frame sum equals the master-frame count.
- Source ranges are finite, nonnegative and inside the source duration.
- Selected FPS values all divide 48,000, so each clip's PCM sample count is an integer.
- Speed is applied to video timestamps and decomposed audio tempo factors in the supported 0.5–2 range.
- Short source clips reduce playback speed instead of reading past the source.

Source duration/frame rate comes from OpenCV metadata, not an edit decision based on source frame numbers. FFmpeg normalizes output to a constant frame rate, with bounded tail padding to cover decoder rounding. Variable-rate and unusual timestamp sources should be reviewed for creative timing; no frame-accurate source timecode conform is claimed.

## Audio pipeline

Each worker writes two outputs: video-only MOV and stereo 48 kHz PCM WAV. Audio is resampled, time-stretched, padded and trimmed to the exact sample count. Separate concat lists join the video and audio. Original audio, the generated SFX stem and optional looping music are mixed through a limiter. AAC encoding happens once in the final MP4.

This avoids accumulating AAC priming at every editorial cut. Original audio gain is 0.8, SFX gain is 0.7 and music gain is 0.25. The limiter ceiling is 0.95 with its automatic level compensation disabled and latency compensation enabled. These fixed gains are not dialogue-aware ducking or a loudness delivery standard.

## Cache and publication

1. Validate the plan before rendering.
2. Acquire an exclusive lock next to the requested master.
3. Verify full SHA-256, size and modification time of every source and music file.
4. Compute a cache key from the plan, encoder, application version and FFmpeg version.
5. Reuse a clip only when its video and WAV hashes match the completion manifest and media invariants still hold.
6. Rebuild partial or damaged clips. Completion manifests are written after validated outputs are renamed.
7. Assemble the master in a staging directory on the destination filesystem.
8. Validate master frame count/dimensions; decode it unless explicitly disabled.
9. Export handoff metadata before replacing any existing master.
10. Verify the full source/music identities again, including SHA-256.
11. Publish with an atomic exclusive operation unless overwrite was explicitly requested.
12. Save the publication report.

Handoff export failure leaves an existing master untouched. Report writing happens after publication; a disk failure during report writing can still leave a completed master without an updated report. This is not a multi-file filesystem transaction. A subsequent render with `--overwrite` reuses cached clips and retries export/report writing. An OS crash can leave a stale lock or staging directory. The application does not guess that another process is dead and delete its lock.

No-overwrite publication does not use an existence check followed by a replacing rename. Windows uses its non-replacing rename; POSIX uses an exclusive hard link followed by removal of the staging name. The latter requires hard-link support on the destination filesystem. Staging is on that same filesystem. The overwrite path uses atomic replace.

PCM validation reads the declared sample payload in bounded chunks so a valid WAV header cannot conceal truncation. Cache manifests record whether decoding was verified. A later verified render decodes any previously unchecked cached clips and upgrades that record without reencoding valid media.

Worker failures set a shared cancellation event, cancel pending futures and cause running FFmpeg processes to be killed and reaped by their own runner. A keyboard interrupt follows the same path. Processes are launched with argument arrays and no shell; user paths are not interpolated into shell commands or FFmpeg filter strings. Filters refer only to generated simple cache-relative filenames.

## Native adapters

XML carries individually rendered video cuts and the finished stereo master mix. Effects are baked, so editing the original speed/zoom/grade requires changing the JSON plan and rendering again. Importing XML does not apply the LUT a second time.

The Resolve adapter creates a uniquely named new project and checks import/save results. Native rendering requires an explicitly named installed render preset. On timeout/interruption it stops the render it started.

The AE adapter requires an empty existing project, refuses to replace an AEP, and waits for a unique status file produced by JSX rather than waiting for the GUI process to close. JSON serialization escapes path/string data. The app's scripting file-access settings must already permit the operation. The adapter does not change security settings, licenses or permissions.

Relative manifest media/project paths are normalized against the manifest directory before script generation. The explicit CLI project override uses the caller's working directory. Native aerender output is staged with the chosen filename extension and published only after a successful process exit and nonempty-file check.

## Tests and limits of evidence

Unit tests exercise validation, corruption, process failure/timeout, hashes, locks, LUT ordering, SFX sample counts, XML structure and native adapter contracts. Integration tests create both audio-bearing and silent video, use different source/output FPS, mix music, validate output and deliberately damage the cache.

Mocked adapter tests verify the Python contract only. They do not prove media import or rendering in a particular installed Adobe/Resolve version. The three-OS CI matrix must run on its actual hosts before claiming those hosts were tested.
