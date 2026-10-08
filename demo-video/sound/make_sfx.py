"""Make every sound in the reel, from nothing but arithmetic.

    python demo-video/sound/make_sfx.py

Writes 48 kHz, 16-bit stereo WAVs into demo-video/public/sfx/. No sound here is recorded
or downloaded, and the same run always writes the same files. They are meant to feel like
a well-made interface: soft, clean and short, with nothing harsh in them.

Each sound is made at its own level and none is raised to full scale afterwards: how loud
a sound is in the film is set where it is cued (src/Sound.tsx), not here.
"""

import sys
import wave
from pathlib import Path

import numpy as np

RATE = 48_000
OUT = Path(__file__).resolve().parent.parent / "public" / "sfx"
#: How long the room tone is: the film's length, 710 frames at 30 a second.
FILM = 710 / 30


def seconds(length):
    return np.arange(int(RATE * length)) / RATE


def noise(length, low, high, seed):
    """Noise holding only the pitches between `low` and `high`, with soft edges."""
    count = int(RATE * length)
    spectrum = np.fft.rfft(np.random.default_rng(seed).standard_normal(count))
    pitch = np.fft.rfftfreq(count, 1 / RATE)
    keep = 1 / (1 + (low / np.maximum(pitch, 1e-6)) ** 6) / (1 + (pitch / high) ** 6)
    shaped = np.fft.irfft(spectrum * keep, count)
    return shaped / np.max(np.abs(shaped))


def tone(pitch):
    """A sine whose pitch may change along the way: `pitch` is in hertz, a value a sample."""
    return np.sin(2 * np.pi * np.cumsum(pitch) / RATE)


def fall(t, time):
    """Dies away, to about a third in `time` seconds."""
    return np.exp(-t / time)


def edges(t, attack, release):
    """Rises over `attack` seconds at the start and falls over `release` at the end, so
    that no sound starts or stops with a click."""
    end = t[-1]
    return np.clip(t / attack, 0, 1) * np.clip((end - t) / release, 0, 1)


def glide(t, start, end, bend=1.0):
    """A pitch going from `start` to `end` over the whole sound."""
    return start + (end - start) * (t / t[-1]) ** bend


def save(name, left, right=None, peak=0.5):
    """Write one sound with its loudest sample at `peak`."""
    right = left if right is None else right
    both = np.stack([left, right], axis=1)
    both = both / np.max(np.abs(both)) * peak
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as file:
        file.setnchannels(2)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes((both * 32767).astype("<i2").tobytes())
    sys.stdout.write(f"{name:10s} {len(left) / RATE:6.2f} s  peak {peak:.2f}\n")


def room():
    """A barely audible tone under the whole film: two slow low notes a fifth apart over
    a trace of low air. Different in each ear, so it has width."""
    t = seconds(FILM)
    shape = edges(t, 1.2, 1.5)
    sides = []
    for seed in (11, 12):
        # Almost all of it is the two notes. The air is low and faint: any more of it, or
        # any of it higher up, and the tone is heard as hiss or rain.
        air = noise(FILM, 60, 260, seed) * 0.1
        notes = 0.6 * np.sin(2 * np.pi * 110 * t) + 0.35 * np.sin(2 * np.pi * 165 * t + seed)
        swell = 1 + 0.15 * np.sin(2 * np.pi * t / 7.3 + seed)
        sides.append((air + notes) * swell * shape)
    save("room", sides[0], sides[1], peak=0.2)


def tick():
    """Very soft, 20 ms. Five of them, each at a slightly different pitch."""
    t = seconds(0.02)
    for i, pitch in enumerate((2050, 2200, 2360, 2120, 2280)):
        body = tone(np.full(t.size, pitch)) + 0.3 * tone(np.full(t.size, pitch * 2.01))
        save(f"tick-{i}", body * fall(t, 0.004) * edges(t, 0.0006, 0.004), peak=0.3)


def sweep():
    """Air passing: about 0.8 s, going from the left ear to the right with the line."""
    length = 0.8
    t = seconds(length)
    along = t / length
    air = noise(length, 700, 5200, 21) * 0.8 + noise(length, 4000, 11000, 22) * 0.3 * along
    air *= np.sin(np.pi * along) ** 1.4
    save("sweep", air * np.cos(along * np.pi / 2), air * np.sin(along * np.pi / 2), peak=0.4)


def shimmer():
    """A soft rising tone, about 1.5 s, with a slow waver so it is not a plain whistle."""
    t = seconds(1.5)
    pitch = glide(t, 392, 784, 1.3)
    body = (
        tone(pitch)
        + 0.45 * tone(pitch * 1.5)
        + 0.2 * tone(pitch * 2.005)
        + 0.1 * tone(pitch * 3.01)
    )
    body *= 1 + 0.18 * np.sin(2 * np.pi * 5.5 * t)
    shape = np.sin(np.pi * (t / t[-1]) ** 0.8) ** 1.5
    save("shimmer", body * shape, peak=0.3)


def whoosh():
    """A low swell of air, about 0.5 s, loudest three fifths of the way through."""
    length = 0.5
    t = seconds(length)
    along = t / length
    shape = np.where(along < 0.6, (along / 0.6) ** 2.2, ((1 - along) / 0.4) ** 1.6)
    air = noise(length, 70, 650, 31) + 0.35 * noise(length, 500, 2400, 32) * along
    lean = 0.5 + 0.2 * np.sin(along * np.pi)
    save("whoosh", air * shape * (1 - lean + 0.5), air * shape * (lean + 0.5), peak=0.5)


def pop():
    """A soft round blip, at three rising pitches."""
    t = seconds(0.16)
    for i, pitch in enumerate((523, 659, 784)):
        bend = pitch * (1 + 0.5 * fall(t, 0.012))
        save(f"pop-{i}", tone(bend) * fall(t, 0.035) * edges(t, 0.002, 0.02), peak=0.4)


def glass():
    """A light tap on glass: a few high notes that do not line up, dying quickly."""
    t = seconds(0.4)
    for i, pitch in enumerate((1760, 1976, 2217)):
        body = sum(
            weight * tone(np.full(t.size, pitch * ratio)) * fall(t, time)
            for ratio, weight, time in (
                (1, 1.0, 0.09),
                (2.76, 0.5, 0.05),
                (5.4, 0.25, 0.03),
                (8.93, 0.1, 0.015),
            )
        )
        save(f"glass-{i}", body * edges(t, 0.0015, 0.05), peak=0.3)


def shink():
    """Bright and clean: a short hiss of the cut, and high notes ringing briefly after."""
    t = seconds(0.6)
    cut = noise(0.6, 5000, 14000, 41) * fall(t, 0.012)
    ring = sum(
        weight * tone(np.full(t.size, pitch)) * fall(t, time)
        for pitch, weight, time in (
            (3136, 1.0, 0.13),
            (4699, 0.6, 0.1),
            (6272, 0.35, 0.07),
            (9397, 0.15, 0.04),
        )
    )
    save("shink", (0.5 * cut + ring) * edges(t, 0.001, 0.08), peak=0.35)


def rise():
    """A soft tone rising for about 1.5 s under the bars as they grow."""
    t = seconds(1.5)
    pitch = glide(t, 196, 587, 1.5)
    body = (
        tone(pitch) + 0.3 * tone(pitch * 2.0) + 0.5 * noise(1.5, 300, 2500, 51) * (t / t[-1]) ** 2
    )
    shape = (t / t[-1]) ** 1.4 * np.clip((t[-1] - t) / 0.22, 0, 1)
    save("rise", body * shape, peak=0.3)


def roll():
    """A counter turning: very soft ticks, close together, climbing a little."""
    length = 0.75
    t = seconds(length)
    out = np.zeros(t.size)
    one = seconds(0.012)
    for i, start in enumerate(np.arange(0, length - 0.02, 0.034)):
        pitch = 1500 + 500 * start / length
        click = tone(np.full(one.size, pitch)) * fall(one, 0.003) * edges(one, 0.0005, 0.003)
        at = int(start * RATE)
        out[at : at + one.size] += click * (0.7 + 0.3 * (i % 2))
    save("roll", out * edges(t, 0.01, 0.1), peak=0.2)


def click():
    """A crisp click with a note in it, at three rising pitches."""
    t = seconds(0.3)
    for i, pitch in enumerate((659, 784, 988)):
        snap = noise(0.3, 2500, 9000, 60 + i) * fall(t, 0.0025)
        note = (tone(np.full(t.size, pitch)) + 0.3 * tone(np.full(t.size, pitch * 2))) * fall(
            t, 0.07
        )
        save(f"click-{i}", (0.6 * snap + note) * edges(t, 0.0008, 0.04), peak=0.4)


def hit():
    """Deep, dry and short."""
    t = seconds(0.3)
    body = tone(60 + 70 * fall(t, 0.02)) * fall(t, 0.07)
    knock = noise(0.3, 150, 1400, 71) * fall(t, 0.008)
    save("hit", (body + 0.35 * knock) * edges(t, 0.001, 0.05), peak=0.6)


def impact():
    """A low impact with a tail that takes two seconds to go."""
    t = seconds(2.2)
    body = tone(46 + 60 * fall(t, 0.03)) * fall(t, 0.45)
    knock = noise(2.2, 120, 1200, 81) * fall(t, 0.012)
    sides = []
    for seed in (82, 83):
        tail = noise(2.2, 60, 500, seed) * fall(t, 0.6) * 0.3
        sides.append((body + 0.3 * knock + tail) * edges(t, 0.0015, 0.5))
    save("impact", sides[0], sides[1], peak=0.7)


if __name__ == "__main__":
    for make in (
        room,
        tick,
        sweep,
        shimmer,
        whoosh,
        pop,
        glass,
        shink,
        rise,
        roll,
        click,
        hit,
        impact,
    ):
        make()
