# AutoFX Studio 0.2.1

Automatic short-form editing, procedural SFX, creative `.cube` LUTs, and video editor handoff from the terminal.

This project processes videos locally. It does not require a cloud account, subscription, API key, or media upload. The user's reference videos are not included in the source package.

## Features

- Finds cut candidates using scene histograms; analysis is limited to a maximum of 2,400 small frames.
- Detects energy rises in optional background music and aligns cuts with nearby candidates.
- Builds timelines on integer frame boundaries at 24, 25, 30, 50, or 60 FPS.
- Applies zoom/punch-in, short flashes, constant playback-speed changes, and a creative color look.
- Generates whoosh and impact sounds for cuts and saves them as 48 kHz WAV audio.
- Renders video and PCM audio separately; AAC is encoded only in the final master.
- Supports parallel clip rendering, SHA-256 source/cache verification, atomic master publication, and process cancellation.
- Produces an MP4 master, JSON plan/report, `.cube` LUT, WAV audio, FCP7 XML, and AE JSX/manifest files.
- Imports into a separate new Resolve project and can render natively using a selected installed preset.
- Provides an After Effects composition/AEP builder and a separate `aerender` command.

This is a rules-based editing engine. It is not a model that generates arbitrary VFX scenes from text prompts, a speech-aware editor, an automatic rotoscoping system, or a pixel-perfect recreation of a reference. Cuts may interrupt speech. Music analysis is not music-theory-level beat or downbeat detection.

The [audit report](docs/AUDIT.md) documents the issues found in the 0.2.1 audit, their fixes, and before/after test evidence. In addition to source and cache hashes, the engine reads and validates the actual PCM payload and preserves the display aspect ratio of anamorphic video.

## Platforms

| Component | Windows | Linux | macOS |
|---|---|---|---|
| CLI, FFmpeg rendering, LUTs, SFX | Yes | Yes | Yes |
| XML/JSX file generation | Yes | Yes | Yes |
| Native Resolve adapter | Requires an installed API and suitable license | Requires an installed API and suitable license | Requires an installed API and suitable license |
| Native Adobe adapters | Requires an AE installation | No native Adobe version | Requires an AE installation |

Premiere is supported through XML import; direct headless control of Premiere is not claimed. Adobe products unrelated to video editing, such as Photoshop and Illustrator, are outside this project's scope. H.264 import in Resolve on Linux depends on the edition, version, and codec support; creating an FFmpeg master does not depend on it.

## Installation

Install Python 3.10 or newer. From the project directory:

```console
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe run_autofx.py doctor
```

Linux/macOS:

```sh
.venv/bin/python -m pip install -e .
.venv/bin/python run_autofx.py doctor
```

In an activated virtual environment, the `python` examples below and the installed `autofx` command provide the same functionality. The FFmpeg binary supplied by the Python dependency can be used; a separate ffprobe installation is not required. Alternatively, add FFmpeg to your system PATH. To select another binary, set `AUTOFX_FFMPEG` to the executable's full path.

## Render with one command

```console
python run_autofx.py auto "video1.mp4" "video2.mp4" -o "renders/result.mp4" --preset hype --duration 15 --width 1080 --height 1920 --jobs 2
```

Add music and fit the entire image without cropping:

```console
python run_autofx.py auto "video.mp4" -o "renders/music.mp4" --music "music.wav" --fit contain --preset cinematic
```

`cover` crops the edges to fill the frame. `contain` preserves the entire image and fills unused space with black. HDR/PQ/HLG sources are not automatically graded as SDR: first convert them to SDR using a separate, properly color-managed workflow. The generated LUT is a Rec.709/display-referred creative look, not a camera LOG transform.

Cover art is not treated as the primary video. For containers with multiple primary video tracks, remux your chosen track into a separate file first. Such containers are rejected with a clear error to prevent metadata inspection and rendering from selecting different tracks.

## Edit a plan and resume rendering

```console
python run_autofx.py plan "video.mp4" -o "edit.json" --duration 12 --no-analyze
python run_autofx.py render "edit.json" -o "renders/edit.mp4"
```

You can edit `in`, `speed`, `zoom`, and `flash` in the JSON `clips` list. The `timeline_frame` and `frames` values must form a continuous timeline with no gaps or overlaps. Old 0.1 plans are unsupported; regenerate them using schema 2.

Repeating the same command reuses completed clips whose hashes match. Replacing an existing master requires `--overwrite`. If a source changes, regenerate the plan. Remove a stale `.autofx.lock` left by a power failure only after confirming that no render is running for that output. The program does not automatically delete another process's lock.

## Performance and GPU encoding

`--encoder cpu` is the default and most broadly compatible option. You can also select `nvenc`, `qsv`, `amf`, or `videotoolbox`. `doctor` reports whether an encoder is compiled into FFmpeg; it does not prove that a compatible GPU and driver are available. GPU errors are reported rather than hidden, and there is no silent fallback to CPU encoding.

Filters, histogram analysis, and zoom run on the CPU. Selecting a GPU encoder changes video encoding only. Performance depends on the source codec, storage, frame size, and hardware; consistent real-time performance is not promised. `--jobs` accepts values from 1 to 8; use 1 or 2 at high resolutions to limit memory use. `--skip-decode-check` disables the additional full decode pass; frame counts, PCM lengths, and source hashes are still checked.

## Outputs

The engine creates `result_assets/<hash>/` beside the master:

| File | Purpose |
|---|---|
| `plan.json` | Exact edit plan and source identities |
| `report.json` | Master hash, duration, render time, and output paths |
| `clip_*.mov` | Separate video clips with effects applied |
| `clip_*.wav` | PCM audio with an exact sample count for each clip |
| `source_audio.wav` | Original audio assembled across the cuts |
| `sfx.wav` | Separate whoosh/impact stem |
| `look.cube` | Creative LUT |
| `timeline.xml` | Cut timeline for Premiere/Resolve |
| `after_effects.json` | AE import manifest |
| `build_after_effects.jsx` | AE composition builder script |

XML/AE handoff keeps video clips separate, with effects baked into those clips; effects are not transferred as native, parametric VFX nodes. Timeline audio comes from the completed master. Keep the entire media folder together with the master; moving files may require relinking in your editor. Source identities include absolute file paths. Review media, plans, and reports before adding them to a public repository.

## Resolve

Start Resolve and prepare external scripting support in your installed edition. If needed, configure `RESOLVE_SCRIPT_API` and `RESOLVE_SCRIPT_LIB` according to the vendor's README.

```console
python run_autofx.py resolve "renders/result_assets/HASH/timeline.xml"
python run_autofx.py resolve "renders/result_assets/HASH/timeline.xml" --render-dir "native-render" --render-preset "MyInstalledPreset"
```

A new project with a unique name is created. Native rendering requires the exact name of an installed render preset. The command does not change licensing or application permission settings.

## After Effects

Open an empty AE project. The installed application must already allow scripts to write files. On Windows, for example, supply the executable path for your installed version:

Relative media and project paths in the AE manifest are resolved against the manifest directory. An explicit `--project` output path is resolved against the terminal's current directory. Native `aerender` does not save a partial result under the final output name; the completed staging file is published at the end.

```console
python run_autofx.py after-effects "renders/result_assets/HASH/after_effects.json" --exe "C:/Program Files/Adobe/Adobe After Effects 2025/Support Files/AfterFX.exe" --project "renders/native.aep"
```

On macOS, `--exe` is the path to the appropriate executable inside the application's `.app/Contents/MacOS/` directory. The adapter refuses to modify an AE project that already contains media. An existing `.aep` is not replaced. The adapter waits for the script's acknowledgment instead of waiting for the GUI launcher to exit.

```console
python run_autofx.py aerender "renders/native.aep" --exe "/your/path/to/aerender" -o "renders/native.mov" --template "Your installed output module template"
```

The template name must match your AE installation and language. Choose an output format and extension compatible with that template. Native applications and adapters require separately installed software and suitable licenses.

## Testing

Run the complete test suite and save a machine-readable report with one command:

```console
python tools/check.py --integration --report validation.json
```

Add `--temp-dir ./test-work` to choose a separate temporary directory for tests.

```console
python -m unittest discover -s tests -v
```

To enable real rendering tests that generate synthetic videos:

Windows PowerShell:

```powershell
$env:AUTOFX_INTEGRATION='1'
python -m unittest discover -s tests -v
```

Linux/macOS:

```sh
AUTOFX_INTEGRATION=1 python -m unittest discover -s tests -v
```

Unit tests cover invalid plans, NaN/Infinity, hashes, locks, process timeouts, audio tempo, LUTs, SFX, and XML. Integration tests cover mixed frame rates, silent and audio-bearing sources, Unicode paths and spaces, music, caching, and recovery from a damaged cached clip. CI is configured for three operating systems; the existence of a CI configuration alone does not prove those platforms were tested in the local session. Actual local results are recorded in `VALIDATION.md`.

## Limitations

- Output duration: 0.2-600 seconds; 1-128 sources; at most 4,096 clips.
- The engine provides simple energy analysis, rules-based editing, and constant playback-speed changes. It does not provide generative VFX, semantic editing, or speed-ramp curves.
- HDR, camera LOG, professional multichannel audio, and subframe timecode require a separate suitable workflow.
- Native Resolve/Adobe behavior depends on the installed application version, edition, media codecs, and permissions.
- FFmpeg, NumPy, and OpenCV are separate projects with their own licenses. No FFmpeg binary is included in this source package.

## Official references

- [After Effects scripting](https://developer.adobe.com/after-effects/)
- [Adobe automated rendering](https://helpx.adobe.com/after-effects/desktop/render-and-export/automate-rendering/automated-rendering-network-rendering.html)
- [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html)
- For Resolve scripting, refer to `Developer/Scripting/README.txt` in your installed product.
