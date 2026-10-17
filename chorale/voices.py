"""The voice library: one SoulX prompt per voice (engine/voices/<name>/
prompt.wav + prompt.json) and a committed description of it (voices/<name>.json:
where it came from and the range it sings in, measured from the clip).

A clip is a few seconds long, so its measured range is narrower than the
singer's: within MARGIN semitones of it is comfortable, and a voice may be
cast up to REACH semitones beyond it (the audition marks those "stretch")."""
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / 'voices'
PROMPTS = ROOT / 'engine' / 'voices'
MARGIN = 3
REACH = 5
CEILING = 77   # F5: above it SoulX can't follow these prompts (they top out at D5); every soprano sang a canon's G5s 3-5 semitones flat
NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


class RangeError(ValueError):
    pass


@dataclass
class Voice:
    name: str
    lang: str
    low: int     # MIDI, 5th percentile of the clip's sung pitch
    high: int    # MIDI, 95th percentile
    median: int
    source: str
    dir: str     # the prompt dir
    sex: str = ''              # 'F' or 'M', where the source says
    type: str = ''             # voice type, where the source says (soprano, tenor, ...)
    reach: int | None = None   # semitones it may be cast beyond low/high (default REACH)


def note_name(midi: int) -> str:
    return f'{NAMES[midi % 12]}{midi // 12 - 1}'


def save(v: Voice) -> None:
    INDEX.mkdir(parents=True, exist_ok=True)
    d = asdict(v)
    if Path(d['dir']).is_absolute() and Path(d['dir']).is_relative_to(ROOT):
        d['dir'] = str(Path(d['dir']).relative_to(ROOT))
    (INDEX / f'{v.name}.json').write_text(json.dumps(d, indent=1) + '\n')


def load(name: str) -> Voice:
    path = INDEX / f'{name}.json'
    if not path.exists():
        raise KeyError(f'no voice {name!r} in {INDEX}')
    v = Voice(**json.loads(path.read_text()))
    v.dir = str(ROOT / v.dir) if not Path(v.dir).is_absolute() else v.dir   # stored relative to the repository
    return v


def all_voices() -> list[Voice]:
    return [load(p.stem) for p in sorted(INDEX.glob('*.json'))]


def check_range(v: Voice, midis: list[int]) -> int:
    """The octave shift (0, then -12/+12) that keeps every note within the
    voice's range; RangeError naming the notes if none does."""
    reach = REACH if v.reach is None else v.reach
    lo, hi = v.low - reach, min(v.high + reach, CEILING)
    notes = sorted(set(midis))
    for shift in (0, -12, 12):
        if all(lo <= m + shift <= hi for m in notes):
            return shift
    out = [note_name(m) for m in notes if not lo <= m <= hi]
    raise RangeError(f'{v.name} sings {note_name(v.low)}-{note_name(v.high)}; out of range: {" ".join(out)}')
