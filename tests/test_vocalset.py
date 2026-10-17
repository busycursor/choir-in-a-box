import json

import numpy as np
import pytest
import soundfile as sf

from chorale import import_vocalset

CSV = '''f1_caro_straight
Female
f1
StraightTone
MusicalExcerp_Caro
None

4.0


Sequence, Start time, End time, Duration, Type, Average F0, Median F0, Min F0, Max F0, Standard deviation F0, Average F0 in range of STD, Estimated MIDI code, Ground truth Note name, Ground Truth Frequency, Ground Truth MIDI code, Lyric, Ground Truth Note duration name, Ground Truth note duration, Interval to the previous note, Interval to the following note
1,0,0.5,0.5,Rest,0,0,0,0,0,0,,,0,,,,,,,
2,0.51,1.5,0.99,Sound,587,587,580,590,1,587,74.1,D5,587.33,74,ca,Quarter_note,,,-1,
3,1.51,1.7,0.19,Transition,570,570,560,580,1,570,73.7,,0,,,,,,,
4,1.71,2.2,0.49,Sound,554,554,550,560,1,554,73.0,C#5,554.37,73,ro,Eighth_note,,1,-2,
5,2.21,2.7,0.49,Sound,493,493,490,496,1,493,71.0,B4,493.88,71,,Eighth_note,,2,-2,
6,2.71,4.0,1.29,Rest,0,0,0,0,0,0,,,0,,,,,,,
'''


def test_notes_from_annotation():
    notes = import_vocalset.notes_from_csv(CSV, 'it')
    assert [n[0] for n in notes] == ['<SP>', 'ca', 'ro', 'ro', '<SP>']
    assert [n[4] for n in notes] == [1, 2, 2, 3, 1]          # the unlabeled note carries "ro" on
    assert [n[3] for n in notes] == [0, 74, 73, 71, 0]
    assert notes[1][1] == 'en_K-AA1'
    assert notes[1][2] == pytest.approx(1.71 - 0.51)         # the transition belongs to the note before
    assert sum(n[2] for n in notes) == pytest.approx(4.0)


def test_window_ends_at_a_rest():
    notes = import_vocalset.notes_from_csv(CSV, 'it')
    cut = import_vocalset.window(notes, target=2.0, longest=3.0)
    assert sum(n[2] for n in cut) == pytest.approx(2.71)
    assert cut[-1][0] == 'ro'


def test_every_singer_has_a_typed_range():
    for singer, kind in import_vocalset.TYPES.items():
        assert kind.rstrip('(?)') in import_vocalset.RANGES, singer


def test_convert_writes_a_24k_prompt(tmp_path):
    sr = 44100
    wav = tmp_path / 'f1_caro_straight.wav'
    sf.write(wav, 0.2 * np.sin(2 * np.pi * 587 * np.arange(4 * sr) / sr), sr)
    import_vocalset.convert(CSV, wav, tmp_path / 'v', 'it')
    audio, out_sr = sf.read(tmp_path / 'v' / 'prompt.wav')
    meta = json.loads((tmp_path / 'v' / 'prompt.json').read_text())[0]
    assert out_sr == 24000
    assert sum(map(float, meta['duration'].split())) == pytest.approx(len(audio) / out_sr, abs=0.02)
