"""Original procedural audio and display-referred creative LUT generation."""
from __future__ import annotations

from pathlib import Path
import wave

import numpy as np


def cube(path: Path, look: str = "hype", size: int = 33) -> None:
    if look not in ("clean", "hype", "cinematic") or type(size) is not int or not 2 <= size <= 65:
        raise ValueError("Invalid look or LUT size")
    with path.open("w", encoding="ascii", newline="\n") as out:
        out.write(f'TITLE "AutoFX {look} Rec709 creative"\nLUT_3D_SIZE {size}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n')
        for b in np.linspace(0, 1, size):
            for g in np.linspace(0, 1, size):
                for r in np.linspace(0, 1, size):
                    color = np.array([r, g, b])
                    if look != "clean":
                        luma = float(color @ [0.2126, 0.7152, 0.0722])
                        color = luma + (color - luma) * (1.12 if look == "hype" else .92)
                        color = (color - .5) * 1.08 + .5
                        color += np.array([-.015, .005, .025]) * (1 - luma)
                        color += np.array([.025, .008, -.012]) * luma
                    out.write(" ".join(f"{v:.7f}" for v in np.clip(color, 0, 1)) + "\n")


def sfx(path: Path, plan: dict, rate: int = 48000) -> None:
    """Write in bounded blocks rather than allocating a ten-minute float stem."""
    if rate != 48000:
        raise ValueError("SFX sample rate must be 48000")
    length = round(plan["frames"] / plan["fps"] * rate)
    rng = np.random.default_rng(42)
    count = round(.24 * rate)
    t = np.arange(count) / rate
    whoosh = rng.normal(0, 1, count) * np.sin(np.pi * np.arange(count) / count) ** 2 * .065
    impact = np.sin(2 * np.pi * (90 * t - 70 * t * t)) * np.exp(-24 * t) * .18
    events = []
    for clip in plan["clips"][1:]:
        boundary = round(clip["timeline_frame"] / plan["fps"] * rate)
        events.extend(((boundary - count // 2, whoosh), (boundary, impact)))
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        for start in range(0, length, 16384):
            stop = min(length, start + 16384)
            block = np.zeros(stop - start, dtype=np.float32)
            for offset, values in events:
                lo, hi = max(start, offset), min(stop, offset + count)
                if hi > lo:
                    block[lo - start:hi - start] += values[lo - offset:hi - offset]
            out.writeframesraw((np.clip(block, -.8, .8) * 32767).astype("<i2").tobytes())
