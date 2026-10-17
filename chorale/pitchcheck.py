"""Octave slips: SoulX samples, and now and then one note of a phrase comes
out an octave off ("diese" in BWV 14.5 sang its second syllable an octave
down once in four takes, with nothing different in the score). The renderer
measures each sung note against the score and sings a slipped phrase again.

Octave mistakes are also what pitch trackers get wrong (a harmonic, or a
formant near one, read as the note): pyworld's fast dio read m2's tenor an
octave high on two notes they sang dead on. So a note counts as slipped only
when two trackers built to resist that, harvest and pyin, both say so.

A note can also open on the wrong pitch: f8's first alto note of BWV 14.5
opened for 180 ms on the next note's pitch (a bright G4 for a D4), then
settled. So each note's first OPENING seconds must also be within WRONG
semitones of it, unless that's the singer still coming from the note before:
anywhere between the two notes is a glide (f8 took 120 ms to slide down
"hätten"'s octave leap, B-flat 4 to 3, which is singing, not a fault).
"""
import librosa
import numpy as np
import pyworld

SLIP = 9          # semitones off that count as a slip, not a wobble
MIN_NOTE = 0.15   # notes shorter than this are too short to judge
OPENING = 0.15    # seconds of a note's start checked for a wrong opening pitch
WRONG = 3         # semitones off, in the opening, that count as a wrong start
SLIDE = 2         # ...unless it lies between the note before and this one, give or take this (a glide)


def slips(audio: np.ndarray, sr: int, seg: dict) -> list[str]:
    """The notes of segment seg (a SoulX target, its audio starting at
    seg['time'][0]) whose sung pitch is SLIP or more semitones off."""
    fh, th = pyworld.harvest(audio.astype(np.float64), sr, frame_period=10)
    fp, _, _ = librosa.pyin(audio.astype(np.float32), fmin=60, fmax=1100, sr=sr, frame_length=2048, hop_length=sr // 100)
    tp = np.arange(len(fp)) / 100

    def sung(f0, t, a, b):
        v = f0[(t >= a) & (t < b)]
        v = v[(v > 0) & ~np.isnan(v)]
        return 69 + 12 * np.log2(np.median(v) / 440) if len(v) else None

    off, t0, before = [], 0.0, None
    for word, dur, midi in zip(seg['text'].split(), map(float, seg['duration'].split()), map(int, seg['note_pitch'].split())):
        if midi and dur >= MIN_NOTE:
            a, b = t0 + 0.2 * dur, t0 + 0.8 * dur
            h, p = sung(fh, th, a, b), sung(fp, tp, a, b)
            if h is not None and p is not None and abs(h - midi) >= SLIP and abs(p - midi) >= SLIP:
                off.append(f'{word} {(h + p) / 2 - midi:+.0f}')
            elif dur >= 2 * OPENING:
                end = t0 + OPENING
                h, p = sung(fh, th, t0, end), sung(fp, tp, t0, end)
                if h is not None and p is not None:
                    start = (h + p) / 2
                    gliding = before is not None and min(before, midi) - SLIDE <= start <= max(before, midi) + SLIDE
                    if abs(h - midi) >= WRONG and abs(p - midi) >= WRONG and not gliding:
                        off.append(f'{word} opens {start - midi:+.0f}')
        before = midi or None
        t0 += dur
    return off


def leave_out(audio, sr: int, seg: dict, fade: float = 0.05):
    """A section singer's phrase that still slips after every try, left out (the
    rest of the section carries the line): silenced across its notes, faded."""
    a, b = int(seg['content'][0] / 1000 * sr), int(seg['content'][1] / 1000 * sr)
    k = int(fade * sr)
    a, b = max(0, a - k), min(len(audio), b + k)
    out = audio.copy()
    ramp = np.linspace(1, 0, k)
    out[a:a + k] *= ramp
    out[a + k:b - k] = 0
    out[b - k:b] *= ramp[::-1]
    return out
