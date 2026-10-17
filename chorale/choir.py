"""Who sings which part (choirs/<name>.json: part -> voice names) and how
fast (tempos.json: chorale id -> bpm, for chorales whose data has none)."""
import json
from pathlib import Path

from chorale import voices

CHOIRS = voices.ROOT / 'choirs'
TEMPOS = voices.ROOT / 'tempos.json'
DEFAULT_BPM = 72  # score_parts.py's default


def load_choir(name: str) -> dict[str, list[voices.Voice]]:
    cast = json.loads((CHOIRS / f'{name}.json').read_text())
    return {part: [voices.load(n) for n in names] for part, names in cast.items()}


def tempo(id: str, cli_bpm: float | None, data_bpm: float | None = None) -> float:
    if cli_bpm:
        return cli_bpm
    table = json.loads(TEMPOS.read_text()) if TEMPOS.exists() else {}
    return table.get(id) or data_bpm or DEFAULT_BPM


def cast(choir: dict[str, list[voices.Voice]], parts: dict, sitting_out: list[str] | None = None) -> dict[str, list[tuple[str, int]]]:
    """part -> [(prompt dir, octave shift)] for every part the score has. In a
    section, a singer the line doesn't fit sits this one out (named in
    sitting_out), and so does one who could only sing it an octave off, unless
    nobody can sing it as written; RangeError naming the part if nobody in it
    can sing it at all."""
    out = {}
    for part, notes in parts.items():
        if part not in choir:
            raise KeyError(f'the choir has no {part}')
        midis = [n[0] for n in notes if n[0] is not None]
        singers, errors = [], []
        for v in choir[part]:
            try:
                singers.append((v.dir, voices.check_range(v, midis)))
            except voices.RangeError as e:
                errors.append(str(e))
                if sitting_out is not None: sitting_out.append(f'{part}: {e}')
        if not singers:
            raise voices.RangeError(f'{part}: ' + '; '.join(errors))
        as_written = [s for s in singers if s[1] == 0]
        if as_written and len(as_written) < len(singers) and sitting_out is not None:
            names = {v.dir: v.name for v in choir[part]}
            sitting_out += [f'{part}: {names[d]} only an octave off ({sh:+d})' for d, sh in singers if sh]
        out[part] = as_written or singers
    return out
