"""A sung render finished: mixed in its venue (room.py), heard live if asked
(audience.py, with the conductor's introduction if asked), and written as an
MP3 named for what it is, e.g.
  BWV 14.5 - Wär Gott nicht mit uns diese Zeit (full choir, large church, live).mp3
"""
import json, re, subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from chorale import audience, room
from chorale.sing_parts import LEAD_IN

MP3_RATE, MP3_KBPS = 44100, 192


def title_of(render: dict, parts: dict) -> tuple[str, str, str]:
    """(work, title, composer): "BWV 14.5" and its title for a Bach chorale, else what the score says."""
    work = render.get('id', '')
    m = re.match(r'bwv(\d+(?:\.\d+)?)(.*)', work)
    if m:
        return f'BWV {m.group(1)}{m.group(2)}', parts.get('title') or work, 'Johann Sebastian Bach'
    return '', parts.get('title') or work, parts.get('composer') or ''


CHOIRS = {'full': 'full choir', 'quartet': 'quartet', 'six': 'six-part choir'}


def name_of(work: str, title: str, choir: str, venue: str, live: bool, composer: str = '') -> str:
    what = ', '.join([CHOIRS.get(choir, choir), venue.replace('_', ' ')] + (['live'] if live else []))
    stem = f'{work} - {title}' if work else (f'{composer.split()[-1]} - {title}' if composer else title)
    name = re.sub(r'[?*"]', '', f'{stem} ({what})')     # not allowed in file names: dropped
    return re.sub(r'[/\\:<>|]', '-', name)                # or, where they separate things, a dash


def mp3(wav: np.ndarray, sr: int, path: Path, tags: dict) -> Path:
    """The mix as an MP3 at 44.1 kHz, tagged."""
    meta = [a for k, v in tags.items() if v for a in ('-metadata', f'{k}={v}')]
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'f32le', '-ar', str(sr), '-ac', '2', '-i', '-',
                    '-ar', str(MP3_RATE), '-c:a', 'libmp3lame', '-b:a', f'{MP3_KBPS}k', *meta, str(path)],
                   input=wav.astype(np.float32).tobytes(), check=True)
    return path


def finish(render_dir: Path, venue: str = 'large_church', liveliness: float | None = None, applause: str = 'applause',
           conductor_line: str | None = None, seed: int = 0) -> Path:
    """Mix a render in its venue (live at `liveliness` if given) and write the MP3; returns its path."""
    render = json.loads((render_dir / 'render.json').read_text())
    parts = json.loads((render_dir / 'parts.json').read_text())
    name, crowd = room.VENUES[venue]
    music = room.mix(room.stems_of(render_dir), room.ROOMS[name], parts.get('phrases'), LEAD_IN, parts['parts'])
    out = music
    if liveliness is not None:
        intro = None
        if conductor_line is not None:
            from chorale import conductor
            intro = audience.conductor_take(conductor_line)
            if intro is None:
                intro = conductor.say(conductor_line, takes=1)[0]
                print(f'conductor: made {intro.name}; listen, and pick it in {conductor.LINES / "picks.json"}')
        out = audience.live(music, parts.get('phrases') or [], LEAD_IN, audience.picks(), seed=seed,
                            liveliness=liveliness, applause_kind=applause, room_name=name, intro=intro, crowd=crowd)
    work, title, composer = title_of(render, parts)
    file = render_dir / f'{name_of(work, title, render.get("choir", "full"), venue, liveliness is not None, composer)}.mp3'
    return mp3(out, room.SR, file, {'title': f'{work} {title}'.strip(), 'composer': composer, 'artist': 'choir-in-a-box',
                                     'comment': ', '.join(v for vs in render.get('voices', {}).values() for v in vs)})
