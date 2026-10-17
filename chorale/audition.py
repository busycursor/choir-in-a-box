"""Audition every voice that can sing each part, on the chorale's first phrase.

Each part is cut at the soprano's first rest, and every voice whose range
covers that part at written pitch sings it. "Stretch" marks a voice that
reaches it only within voices.REACH semitones of its clip's range rather
than voices.MARGIN. The model loads once for every take. Writes
engine/renders/audition/<id>/<part>/<voice>.wav and an index.html to listen from.

Usage: python -m chorale.audition <ref> [--parts=Soprano,Bass] [--choir=<name>] [--steps=64]
--choir auditions only that choir's singers, each on the part they're seated in.
"""
import html, json, os, subprocess, sys
from pathlib import Path

from chorale import choir, pipeline, scores, voices
from chorale import sing_parts


def first_phrase(parts: dict) -> dict:
    """Every part cut at the time the soprano first rests."""
    t, cut = 0.0, None
    for midi, secs, *_ in parts['Soprano']:
        if midi is None and t > 0:
            cut = t; break
        t += secs
    out = {}
    for name, notes in parts.items():
        t, kept = 0.0, []
        for n in notes:
            if t >= cut: break
            kept.append([n[0], min(n[1], cut - t), *n[2:]])
            t += n[1]
        out[name] = kept
    return out


def candidates(notes: list, pool: list[voices.Voice]) -> list[tuple[voices.Voice, bool]]:
    """(voice, stretch) for each voice that sings these notes at written pitch."""
    midis = [n[0] for n in notes if n[0] is not None]
    found = []
    for v in pool:
        reach = voices.REACH if v.reach is None else v.reach
        for margin, stretch in ((min(voices.MARGIN, reach), False), (reach, True)):
            if all(v.low - margin <= m <= v.high + margin for m in midis):
                found.append((v, stretch)); break
    return found


def main(ref: str, only: list[str] | None, steps: int, choir_name: str | None = None) -> Path:
    score = scores.resolve(ref)
    id = score.id
    out = voices.ROOT / 'engine' / 'renders' / 'audition' / id
    parts = first_phrase(pipeline.build_parts(score.path, out / 'parts.json')['parts'])
    pool = voices.all_voices()
    seats = choir.load_choir(choir_name) if choir_name else None
    jobs, rows = [], []
    for part, notes in parts.items():
        if only and part not in only: continue
        (out / part).mkdir(parents=True, exist_ok=True)
        target = out / part / 'target.json'
        target.write_text(json.dumps(sing_parts.target(notes, 0), ensure_ascii=False))
        for v, stretch in candidates(notes, seats.get(part, []) if seats else pool):
            wav = out / part / f'{v.name}.wav'
            jobs.append({'prompt_wav': f'{v.dir}/prompt.wav', 'prompt_meta': f'{v.dir}/prompt.json',
                         'target_meta': str(target), 'out': str(wav), 'n_steps': steps})
            rows.append((part, v, stretch, wav))
    (out / 'jobs.json').write_text(json.dumps(jobs))
    print(f'{len(jobs)} takes', flush=True)
    subprocess.run([str(pipeline.PYTHON), str(pipeline.HERE / 'soulx_render.py'), str(out / 'jobs.json')],
                   cwd=sing_parts.ENGINE, env={**os.environ, 'PYTHONPATH': sing_parts.ENGINE, 'PYTORCH_ENABLE_MPS_FALLBACK': '1'},
                   check=True)
    write_index(out, id, rows)
    return out / 'index.html'


def write_index(out: Path, id: str, rows: list) -> None:
    body, last = [], None
    for part, v, stretch, wav in rows:
        if part != last:
            body.append(f'<h2>{part}</h2>'); last = part
        rng = f'{voices.note_name(v.low)}–{voices.note_name(v.high)}'
        body.append(f'<div class="take"><code>{html.escape(v.name)}</code> <span>{rng}{" · stretch" if stretch else ""}</span>'
                    f'<audio controls preload="none" src="{part}/{wav.name}"></audio></div>')
    (out / 'index.html').write_text(f'''<!doctype html><meta charset="utf-8"><title>Audition {id}</title>
<style>body{{font:15px system-ui;margin:2em;max-width:44em}} .take{{display:flex;gap:1em;align-items:center;margin:.3em 0}}
code{{width:8em}} span{{width:9em;color:#666}}</style>
<h1>Audition: {id}, first phrase</h1>{"".join(body)}''')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    opt = dict(a[2:].split('=', 1) for a in sys.argv[1:] if a.startswith('--') and '=' in a)
    print(main(args[0], opt['parts'].split(',') if 'parts' in opt else None, int(opt.get('steps', 64)), opt.get('choir')))
