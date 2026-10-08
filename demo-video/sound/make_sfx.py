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
#: How long the room tone is: the film's length, 900 frames at 30 a second.
FILM = 900 / 30


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


def struck(t, pitch, partials, time, seed=0):
    """Something small and hard being struck: a few partials that are not in tune with
    each other, the higher ones dying sooner, with a very short knock at the front."""
    body = sum(
        level * tone(np.full_like(t, pitch * ratio)) * fall(t, time / (1 + 0.7 * i))
        for i, (ratio, level) in enumerate(partials)
    )
    knock = noise(t[-1] + 1 / RATE, 2500, 9000, seed)[: len(t)] * fall(t, 0.004)
    return body + 0.25 * knock


METAL = ((1.0, 1.0), (2.76, 0.55), (5.4, 0.3), (8.93, 0.14))


def spin():
    """A coin spinning on its edge: a thin ring of metal that flutters, slower and lower
    as the coin loses its speed."""
    t = seconds(0.9)
    flutter = 0.5 + 0.5 * np.sin(2 * np.pi * np.cumsum(glide(t, 34, 9, 0.7)) / RATE)
    ring = tone(glide(t, 3900, 3300)) + 0.5 * tone(glide(t, 6100, 5200))
    air = 0.3 * noise(0.9, 3000, 9000, 31)
    save("spin", (ring * 0.6 + air) * flutter * edges(t, 0.03, 0.25), peak=0.2)


def topple():
    """A coin going over and rolling round its rim: a rattle that quickens as it
    settles, as a dropped coin's does."""
    t = seconds(1.6)
    rate = glide(t, 9, 60, 1.6)
    beat = np.maximum(np.sin(2 * np.pi * np.cumsum(rate) / RATE), 0) ** 6
    ring = tone(np.full_like(t, 2950)) + 0.6 * tone(np.full_like(t, 4720))
    grit = 0.35 * noise(1.6, 2500, 8000, 32)
    save("topple", (ring + grit) * beat * fall(t, 0.55) * edges(t, 0.002, 0.2), peak=0.3)


def clink():
    """A coin landing on glass: soft, metallic, short."""
    t = seconds(0.5)
    save("clink", struck(t, 2350, METAL, 0.12, 33) * edges(t, 0.0008, 0.1), peak=0.6)


def chip():
    """Three chips landing, each a little higher than the one before."""
    t = seconds(0.3)
    for i, pitch in enumerate((1480, 1760, 2090)):
        body = struck(t, pitch, ((1.0, 1.0), (2.3, 0.4), (4.1, 0.15)), 0.06, 40 + i)
        save(f"chip-{i}", body * edges(t, 0.0008, 0.06), peak=0.45)


def flip():
    """A card turning over: a short push of air, and a click as it lands."""
    t = seconds(0.45)
    air = noise(0.45, 300, 2600, 34) * np.sin(np.pi * np.clip(t / 0.32, 0, 1)) ** 2
    at = np.clip(t - 0.3, 0, None)
    click = (tone(np.full_like(t, 1250)) + 0.5 * tone(np.full_like(t, 2900))) * fall(at, 0.012)
    click = click * (t >= 0.3)
    lean = t / t[-1]
    save("flip", (air + 0.6 * click) * (1.3 - lean), (air + 0.6 * click) * (0.3 + lean), peak=0.4)


def bars():
    """Bars rising: soft glassy clicks, one after another, each a little higher, the
    way a row of glasses rings when a finger runs along it."""
    t = seconds(1.3)
    out = np.zeros_like(t)
    steps = 14
    for i in range(steps):
        start = 0.06 * i
        since = np.clip(t - start, 0, None)
        pitch = 880 * 2 ** (i / 7)
        note = tone(np.full_like(t, pitch)) + 0.35 * tone(np.full_like(t, pitch * 2.7))
        out += note * fall(since, 0.07) * (t >= start) * (0.6 + 0.4 * i / steps)
    save("bars", out * edges(t, 0.002, 0.2), peak=0.3)


def slide():
    """A bead sliding along a glass rail and settling."""
    t = seconds(0.35)
    glidey = tone(glide(t, 1500, 2300, 0.6)) + 0.4 * noise(0.35, 2500, 7000, 35)
    save("slide", glidey * np.clip(np.sin(np.pi * t / t[-1]), 0, None) ** 1.5, peak=0.25)


def flap():
    """A split-flap display turning over: a quick clatter of light flaps, slowing."""
    t = seconds(0.7)
    out = np.zeros_like(t)
    start = 0.0
    gap = 0.028
    seed = 50
    while start < 0.6:
        since = np.clip(t - start, 0, None)
        clack = noise(0.7, 900, 5000, seed) * fall(since, 0.006) * (t >= start)
        out += clack * (0.6 + 0.4 * np.cos(seed))
        start += gap
        gap *= 1.09
        seed += 1
    save("flap", out * edges(t, 0.001, 0.05), peak=0.35)


def thunk():
    """Cards locking into place: low, soft and short, like a magnet catching."""
    t = seconds(0.3)
    body = tone(glide(t, 150, 88, 0.5)) * fall(t, 0.07)
    snap = 0.2 * noise(0.3, 600, 2400, 36) * fall(t, 0.008)
    save("thunk", (body + snap) * edges(t, 0.001, 0.08), peak=0.55)


def ping():
    """The radar's ping: one clear note, and a tail that shimmers as it dies away."""
    t = seconds(1.4)
    note = tone(np.full_like(t, 1320)) * fall(t, 0.22)
    shimmer = 1 + 0.5 * np.sin(2 * np.pi * 7 * t)
    tail = (tone(np.full_like(t, 1980)) + 0.6 * tone(np.full_like(t, 2643))) * shimmer
    tail = 0.3 * tail * fall(t, 0.4)
    body = (note + tail) * edges(t, 0.004, 0.4)
    # The tail wanders a little between the two sides.
    lean = 0.5 + 0.2 * np.sin(2 * np.pi * 1.5 * t)
    save("ping", body * (1.2 - lean), body * (0.2 + lean), peak=0.4)


def dive():
    """The camera going into or out of something: a smooth push of air."""
    t = seconds(0.6)
    air = noise(0.6, 120, 1500, 37) * np.sin(np.pi * t / t[-1]) ** 2
    lean = t / t[-1]
    save("dive", air * (1.2 - lean), air * (0.2 + lean), peak=0.4)


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
        spin,
        topple,
        clink,
        chip,
        flip,
        bars,
        slide,
        flap,
        thunk,
        ping,
        dive,
    ):
        make()
