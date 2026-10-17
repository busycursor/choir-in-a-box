import json
import subprocess

from chorale import choir, pipeline, voices


def test_dry_run_names_parts_voices_and_tempo(tmp_path):
    from music21 import corpus
    score = tmp_path / 'bwv14.5.musicxml'
    corpus.parse('bach/bwv14.5').write('musicxml', fp=str(score))
    cast = json.loads((choir.CHOIRS / 'full.json').read_text())
    r = subprocess.run([str(pipeline.PYTHON), '-W', 'ignore', '-m', 'chorale', str(score), '--dry-run', f'--out={tmp_path / "out"}'],
                       cwd=voices.ROOT, capture_output=True, text=True, check=True)
    assert 'bwv14.5' in r.stdout and '72 bpm' in r.stdout
    for part, names in cast.items():
        assert part in r.stdout and any(n in r.stdout for n in names)
