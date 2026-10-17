"""The song pipeline's two stages, run as the CLIs they are: score_parts.py
(score -> parts.json) and sing_parts.py (parts.json + one prompt per part ->
<part>.wav and mix.wav, the model loaded once for every part)."""
import json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / 'engine' / 'soulx' / '.venv' / 'bin' / 'python'
HERE = Path(__file__).resolve().parent


def build_parts(score: Path, out: Path, bpm: float | None = None, lang: str | None = None, literal: bool = False,
                stop: str | None = None, transpose: int | None = None) -> dict:
    cmd = [str(PYTHON), str(HERE / 'score_parts.py'), str(score), str(out)] + (['--literal'] if literal else [])
    if stop: cmd.append(f'--stop={stop}')
    if transpose: cmd.append(f'--transpose={transpose}')
    if bpm: cmd.append(f'--bpm={bpm:g}')
    if lang: cmd.append(f'--lang={lang}')
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    return json.loads(out.read_text())


def sing(parts_json: Path, out_dir: Path, cast: dict[str, list[tuple[str, int]]], steps: int | None = None, cfg: float | None = None) -> None:
    """cast: part -> [(prompt dir, semitone shift)], one per singer in the section."""
    cmd = [str(PYTHON), str(HERE / 'sing_parts.py'), str(parts_json), str(out_dir)]
    cmd += [f'{part}=' + ','.join(f'{prompt}:{shift}' for prompt, shift in singers) for part, singers in cast.items()]
    if steps: cmd.append(f'--steps={steps}')
    if cfg: cmd.append(f'--cfg={cfg:g}')
    subprocess.run(cmd, check=True)
