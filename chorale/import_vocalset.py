"""Voices from VocalSet (Wilkins et al. 2018, zenodo 1442513): 20 professional
singers (f1-f9, m1-m11), each singing three excerpts, "Caro mio ben",
"Dona nobis pacem" and "Row, Row, Row Your Boat", in straight tone and with
vibrato. Annotated-VocalSet (Faghih & Timoney 2022, zenodo 7061507) gives
every note its start, end, written pitch and syllable, so an excerpt becomes
a SoulX prompt directly: a Transition row (the glide between notes) belongs
to the note before it, and a sung note without a syllable carries the last
one on (a melisma). Italian and the Latin of "Dona nobis" go through
espeak-ng's Italian (church Latin is sung that way: "pacem" is pa-chem), then
into SoulX's English phonemes the way German does; English through CMUdict.

Each prompt is the excerpt's opening, cut at a rest near WINDOW seconds.
Everyone sang the excerpts in the same key (the men an octave down), so the
annotation's pitches say nothing about range. Each singer's range is instead
the usual range of the voice type VocalSet's readme gives them, and they are
cast at most REACH semitones beyond it.

Usage: python -m chorale.import_vocalset [<dataset dir>]
Names: vs-<singer>-<excerpt>-<straight|vibrato>, e.g. vs-f3-dona-straight.
"""
import csv, io, json, subprocess, sys
from functools import cache
from pathlib import Path

import librosa, numpy as np, pyworld, soundfile as sf

from chorale import prompt, sing_parts, voices

DATASET = voices.ROOT / 'engine' / 'datasets' / 'vocalset'
NOTES = 'Annotated VocalSet/extended 1/with file header'
WINDOW, LONGEST = 10.0, 14.0
REACH = 2
LANG = {'caro': 'it', 'dona': 'it', 'row': 'en'}
# readme-anon.txt (its question marks kept as given)
TYPES = {'f1': 'soprano', 'f2': 'soprano', 'f3': 'soprano', 'f4': 'soprano', 'f5': 'mezzo-soprano',
         'f6': 'soprano', 'f7': 'soprano', 'f8': 'mezzo-soprano', 'f9': 'soprano',
         'm1': 'baritone', 'm2': 'tenor', 'm3': 'tenor', 'm4': 'bass(?)', 'm5': 'baritone', 'm6': 'baritone',
         'm7': 'tenor(?)', 'm8': 'bass', 'm9': 'countertenor', 'm10': 'bass-baritone', 'm11': 'tenor'}
# a trained choral singer's usual range for each type, MIDI (low, high)
RANGES = {'soprano': (60, 81), 'mezzo-soprano': (57, 77), 'countertenor': (55, 74), 'tenor': (48, 69),
          'baritone': (45, 65), 'bass-baritone': (41, 64), 'bass': (40, 62)}


@cache
def phonemes(syllable: str, lang: str) -> str:
    if lang == 'en':
        return prompt.arpabet(syllable)
    ipa = subprocess.run(['espeak-ng', '-v', lang, '-q', '--ipa', syllable], capture_output=True, text=True).stdout
    return sing_parts.arpabet(ipa.strip().replace(' ', ''))


def rows(text: str) -> list[dict]:
    lines = text.splitlines()
    head = next(i for i, l in enumerate(lines) if l.startswith('Sequence'))
    return [{k.strip(): v.strip() for k, v in r.items() if k}
            for r in csv.DictReader(io.StringIO('\n'.join(lines[head:])))]


def notes_from_csv(text: str, lang: str) -> list[tuple]:
    """(text, phonemes, seconds, midi, type) per note: 1 rest, 2 a new syllable, 3 it continues."""
    rs = rows(text)
    notes, last = [], None
    start0 = float(rs[0]['Start time'])
    if start0 > 0.02:
        notes.append(('<SP>', '<SP>', start0, 0, 1))
    for i, r in enumerate(rs):
        end = float(rs[i + 1]['Start time']) if i + 1 < len(rs) else float(r['End time'])
        dur = end - float(r['Start time'])
        kind = r['Type']
        if kind == 'Transition' and notes:
            notes[-1] = (*notes[-1][:2], notes[-1][2] + dur, *notes[-1][3:])
        elif kind == 'Sound':
            midi = int(float(r['Ground Truth MIDI code'] or r['Estimated MIDI code']))
            if r['Lyric']:
                last = (r['Lyric'], phonemes(r['Lyric'].lower(), lang))
                notes.append((*last, dur, midi, 2))
            elif last:
                notes.append((*last, dur, midi, 3))
            else:
                notes.append(('<SP>', '<SP>', dur, 0, 1))
        else:  # a rest, or a glide with nothing before it
            if notes and notes[-1][4] == 1:
                notes[-1] = (*notes[-1][:2], notes[-1][2] + dur, 0, 1)
            else:
                notes.append(('<SP>', '<SP>', dur, 0, 1))
    return notes


def window(notes: list[tuple], target: float = WINDOW, longest: float = LONGEST) -> list[tuple]:
    """The opening notes, cut at the first rest after target seconds (or,
    with no rest by longest, at the end of the syllable sung then)."""
    t = 0.0
    for i, n in enumerate(notes):
        if n[4] == 1 and t >= target:
            return notes[:i]
        t += n[2]
        if t >= longest and (i + 1 == len(notes) or notes[i + 1][4] != 3):
            return notes[:i + 1]
    return notes


def convert(text: str, wav: Path, out_dir: Path, lang: str) -> None:
    notes = window(notes_from_csv(text, lang))
    length = sum(n[2] for n in notes)
    audio, _ = librosa.load(wav, sr=prompt.SR, mono=True)
    audio = audio[:int(round(length * prompt.SR))]
    notes[-1] = (*notes[-1][:2], notes[-1][2] + len(audio) / prompt.SR - length, *notes[-1][3:])  # a clip shorter than its notes
    out_dir.mkdir(parents=True, exist_ok=True)
    sf.write(out_dir / 'prompt.wav', audio, prompt.SR)
    x = audio.astype(np.float64)
    f0, t = pyworld.dio(x, prompt.SR, frame_period=1000 / prompt.FPS)
    f0 = pyworld.stonemask(x, f0, t, prompt.SR)
    json.dump(prompt.meta(out_dir.name, notes, f0), open(out_dir / 'prompt.json', 'w'), indent=1)


def import_all(dataset: Path = DATASET) -> list[voices.Voice]:
    singers = {}
    for csv_path in sorted((dataset / NOTES).glob('*/*.csv')):
        singer, excerpt, style = csv_path.stem.split('_')
        if excerpt in LANG and style in ('straight', 'vibrato'):
            singers.setdefault(singer, []).append((csv_path, excerpt, style))
    out = []
    for singer, takes in singers.items():
        texts = {p: p.read_text(encoding='utf-8', errors='replace') for p, _, _ in takes}
        kind = TYPES[singer]
        low, high = RANGES[kind.rstrip('(?)')]
        folder = ('female' if singer[0] == 'f' else 'male') + singer[1:]
        for p, excerpt, style in takes:
            wav = dataset / 'FULL' / folder / 'excerpts' / style / f'{p.stem}.wav'
            if not wav.exists():
                print('no audio for', p.stem, file=sys.stderr); continue
            name = f'vs-{singer}-{excerpt}-{style}'
            convert(texts[p], wav, voices.PROMPTS / name, LANG[excerpt])
            v = voices.Voice(name, LANG[excerpt], low, high, (low + high) // 2, f'VocalSet {p.stem}',
                             str(voices.PROMPTS / name), sex=singer[0].upper(), type=kind, reach=REACH)
            voices.save(v); out.append(v)
    return out


if __name__ == '__main__':
    for v in import_all(Path(sys.argv[1]) if len(sys.argv) > 1 else DATASET):
        print(f'{v.name:24} {v.type:14} {voices.note_name(v.low)}-{voices.note_name(v.high)}')
