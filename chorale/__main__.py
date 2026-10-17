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
Accompaniment: [--accompaniment=organ|harpsichord|piano] [--accompaniment-style=continuo|doubling]
        [--registration=continuo|continuo_bright|chorale|soft|plenum|reed]  (organ: one registration throughout,
        instead of changing by section)
Skill: [--choir-skill=1.0] [--accompaniment-skill=1.0] [--skill=N sets both]  (1 the default, 0.6 competent.
        The accompanist: higher ornaments more, lower makes mistakes, very low breaks down and finds its way back.
        The choir: lower goes pitchy, then wrong and hunted-for notes, mispronunciation and missed cues, then losing
        the place, then collapses until one part finds an entrance, and at 0 falls apart for good. All of it
        is sung in (below 0.6 each singer is sung twice: a take, then its pitch curve with the faults);
        an accompaniment chosen with --mix-only reacts to what the choir sang.)
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
        opt = {**opt, 'choir-skill': opt.get('choir-skill', opt.get('skill', '1'))}
        sing_it(out, parts, cast, singers, sitting_out, id, score, bpm, opt, flags)
    from chorale.finish import finish
    from chorale import audience, conductor
    live = None if 'audience' not in opt and 'audience' not in flags else float(opt.get('audience', audience.LIVELY))
    line = (opt.get('conductor') or conductor.LINE) if ('conductor' in opt or 'conductor' in flags) else None
    if line is not None and live is None:
        live = audience.LIVELY   # he speaks to an audience
    return finish(out, opt.get('venue', 'large_church' if opt.get('choir', 'full') != 'quartet' else 'church'),
                  live, opt.get('applause', 'applause'), line, int(opt.get('seed', 0)),
                  opt.get('accompaniment'), opt.get('accompaniment-style'), opt.get('registration'),
                  float(opt.get('accompaniment-skill', opt.get('skill', 1.0))))


def sing_it(out, parts, cast, singers, sitting_out, id, score, bpm, opt, flags=frozenset()):
    steps = int(opt.get('steps', 64))
    cfg = float(opt['cfg']) if 'cfg' in opt else None
    choir_skill = float(opt.get('choir-skill', 1.0))
    seed = int(opt.get('seed', 0))
    # who falls apart where, and how the accompanist (if any) reacts: made now, as the choir sings its part of it
    from chorale import ensemble
    from chorale.sing_parts import LEAD_IN
    playing = float(opt.get('accompaniment-skill', opt.get('skill', 1.0))) if opt.get('accompaniment') else None
    together = ensemble.plan(choir_skill, playing, [(a + LEAD_IN, b + LEAD_IN) for a, b in parts.get('phrases') or []],
                             list(cast), seed, 60 / parts['bpm'])
    out.mkdir(parents=True, exist_ok=True)
    (out / 'plan.json').write_text(json.dumps(together, indent=1) + '\n')
    pipeline.sing(out / 'parts.json', out, cast, steps=steps, cfg=cfg, skill=choir_skill, seed=seed, plan=out / 'plan.json')
    (out / 'render.json').write_text(json.dumps({
        'id': id, 'score': str(score.resolve().relative_to(voices.ROOT.resolve())) if score.resolve().is_relative_to(voices.ROOT.resolve()) else str(score), 'bpm': bpm, 'lang': parts['lang'], 'steps': steps, 'cfg': cfg,
        'choir': opt.get('choir', 'full'), 'voices': {p: [v.name for v in singers[p] if v.dir in dict(c)] for p, c in cast.items()},
        'sitting_out': sitting_out,
        'shifts': {p: [s for _, s in c] for p, c in cast.items()}, 'git': git_hash(),
        'options': {k: opt[k] for k in ('stop', 'transpose') if k in opt} | ({'literal': True} if 'literal' in flags else {})
                   | ({'choir-skill': choir_skill, 'seed': int(opt.get('seed', 0))} if choir_skill < 1 else {})},
        indent=1) + '\n')


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
