"""Sing a score: a web page with MusicXML on it, a MusicXML file, or a number
from the chorale site, sung by a choir from choirs/, mixed in a venue and
written as an MP3 (finish.py).

Usage:
  python -m chorale <link|number|file.musicxml> [--choir=full|quartet] [--bpm=N] [--lang=de|en]
                    [--steps=64] [--cfg=3] [--out=engine/renders/<id>] [--literal] [--dry-run]
--literal sings the score exactly as written, rather than as a chorale is sung (timing.py).
--stop=<bar>.<beat> brings everyone to a close together there (a canon that would go round forever).
--transpose=N moves the whole piece N semitones (-2: a tone down), for a top no voice can reach.
Mixing: [--venue=small_church|church|large_church|larger_church] [--audience[=0.35]]
        [--applause=applause|applause_hesitant|applause_finale] [--conductor[="his line"]] [--seed=N]
--mix-only remixes an existing render (no singing) with new mixing options.
  python -m chorale <page> --all [...]   (every score on a page)
Writes <out>/<part>.wav, mix.wav, parts.json and render.json (what it was sung with).
"""
import json, subprocess, sys
from pathlib import Path

from chorale import choir, pipeline, scores, voices


def score_for(ref: str) -> tuple[str, Path]:
    """A score file, a link to one, or a web page with MusicXML on it (scores.py)."""
    s = scores.resolve(ref)
    return s.id, s.path


def git_hash() -> str:
    r = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=voices.ROOT, capture_output=True, text=True)
    return r.stdout.strip()


def sing(ref: str, opt: dict, dry: bool, flags: frozenset = frozenset()) -> Path:
    id, score = score_for(ref)
    out = Path(opt.get('out') or voices.ROOT / 'engine' / 'renders' / id)
    data = json.loads(score.read_text()) if score.suffix == '.json' else {}
    bpm = choir.tempo(id, float(opt['bpm']) if 'bpm' in opt else None, data.get('bpm'))
    if 'mix-only' in flags and (out / 'parts.json').exists():
        parts = json.loads((out / 'parts.json').read_text())   # the parts it was sung from, whatever options made them
    else:
        parts = pipeline.build_parts(score, out / 'parts.json', bpm=bpm, lang=opt.get('lang'), literal='literal' in flags, stop=opt.get('stop'),
                                     transpose=int(opt['transpose']) if 'transpose' in opt else None)
    singers = choir.load_choir(opt.get('choir', 'full'))
    sitting_out = []
    cast = choir.cast(singers, parts['parts'], sitting_out)
    print(f'{id}  {bpm:g} bpm  {parts["lang"]}')
    for part, singing in cast.items():
        names = {v.dir: v.name for v in singers[part]}
        print(f'  {part:8} ' + ', '.join(f'{names[d]}{f" ({s:+d})" if s else ""}' for d, s in singing))
    for line in sitting_out:
        print(f'  sitting out: {line}')
    if dry:
        return out
    if 'mix-only' not in flags:
        sing_it(out, parts, cast, singers, sitting_out, id, score, bpm, opt)
    from chorale.finish import finish
    from chorale import audience, conductor
    live = None if 'audience' not in opt and 'audience' not in flags else float(opt.get('audience', audience.LIVELY))
    line = (opt.get('conductor') or conductor.LINE) if ('conductor' in opt or 'conductor' in flags) else None
    if line is not None and live is None:
        live = audience.LIVELY   # he speaks to an audience
    return finish(out, opt.get('venue', 'large_church' if opt.get('choir', 'full') != 'quartet' else 'church'),
                  live, opt.get('applause', 'applause'), line, int(opt.get('seed', 0)))


def sing_it(out, parts, cast, singers, sitting_out, id, score, bpm, opt):
    steps = int(opt.get('steps', 64))
    cfg = float(opt['cfg']) if 'cfg' in opt else None
    pipeline.sing(out / 'parts.json', out, cast, steps=steps, cfg=cfg)
    (out / 'render.json').write_text(json.dumps({
        'id': id, 'score': str(score), 'bpm': bpm, 'lang': parts['lang'], 'steps': steps, 'cfg': cfg,
        'choir': opt.get('choir', 'full'), 'voices': {p: [v.name for v in singers[p] if v.dir in dict(c)] for p, c in cast.items()},
        'sitting_out': sitting_out,
        'shifts': {p: [s for _, s in c] for p, c in cast.items()}, 'git': git_hash()}, indent=1) + '\n')


def main(argv: list[str]) -> None:
    args = [a for a in argv if not a.startswith('--')]
    opt = dict(a[2:].split('=', 1) for a in argv if a.startswith('--') and '=' in a)
    flags = {a[2:] for a in argv if a.startswith('--') and '=' not in a}
    if 'all' in flags:   # every score on a page
        for s in scores.find(args[0]):
            try:
                print(sing(str(s.path), opt, 'dry-run' in flags, frozenset(flags)), flush=True)
            except (voices.RangeError, KeyError, ValueError) as e:
                print(f'{s.id}: skipped: {e}', flush=True)
        return
    if not args:
        raise SystemExit(__doc__)
    print(sing(args[0], opt, 'dry-run' in flags, frozenset(flags)))


if __name__ == '__main__':
    main(sys.argv[1:])
