import numpy as np

from chorale import pitchcheck

SR = 24000


def tone(midi, secs):
    """A voice-like note: a fundamental and its harmonics, falling off (the
    trackers are built for voices, and read a bare sine as unvoiced)."""
    t = np.arange(int(secs * SR)) / SR
    f = 440 * 2 ** ((midi - 69) / 12)
    return sum(0.3 / k * np.sin(2 * np.pi * k * f * t) for k in range(1, 8))


SEG = {'text': '<SP> la la <SP>', 'duration': '0.2 0.8 0.8 0.2', 'note_pitch': '0 72 71 0'}


def test_on_pitch_is_clean():
    audio = np.concatenate([np.zeros(int(0.2 * SR)), tone(72, 0.8), tone(71, 0.8), np.zeros(int(0.2 * SR))])
    assert pitchcheck.slips(audio, SR, SEG) == []


def test_octave_drop_is_caught():
    audio = np.concatenate([np.zeros(int(0.2 * SR)), tone(72, 0.8), tone(59, 0.8), np.zeros(int(0.2 * SR))])
    assert pitchcheck.slips(audio, SR, SEG) == ['la -12']


def test_wrong_opening_is_caught():
    # f8's alto: the first note opens on the next note's pitch for 180 ms, then settles
    seg = {'text': '<SP> la la <SP>', 'duration': '0.2 0.8 0.8 0.2', 'note_pitch': '0 62 67 0'}
    audio = np.concatenate([np.zeros(int(0.2 * SR)), tone(67, 0.18), tone(62, 0.62), tone(67, 0.8), np.zeros(int(0.2 * SR))])
    assert pitchcheck.slips(audio, SR, seg) == ['la opens +5']


def test_sliding_in_from_the_note_before_is_fine():
    seg = {'text': '<SP> la la <SP>', 'duration': '0.2 0.8 0.8 0.2', 'note_pitch': '0 67 62 0'}
    audio = np.concatenate([np.zeros(int(0.2 * SR)), tone(67, 0.8), tone(66, 0.08), tone(62, 0.72), np.zeros(int(0.2 * SR))])
    assert pitchcheck.slips(audio, SR, seg) == []


def test_glide_down_an_octave_leap_is_fine():
    # "hatten": B-flat 4 to B-flat 3 in one syllable, the voice sliding down for 120 ms
    seg = {'text': '<SP> la la <SP>', 'duration': '0.2 0.8 0.8 0.2', 'note_pitch': '0 70 58 0'}
    t = np.arange(int(0.12 * SR)) / SR
    glide = sum(0.3 / k * np.sin(2 * np.pi * k * np.cumsum(440 * 2 ** ((np.linspace(70, 58, len(t)) - 69) / 12)) / SR) for k in range(1, 8))
    audio = np.concatenate([np.zeros(int(0.2 * SR)), tone(70, 0.8), glide, tone(58, 0.68), np.zeros(int(0.2 * SR))])
    assert pitchcheck.slips(audio, SR, seg) == []


def test_a_phrase_left_out_is_silent_across_its_notes_and_faded():
    audio = np.ones(3 * SR)
    seg = {'content': [1000, 2000]}
    out = pitchcheck.leave_out(audio, SR, seg)
    assert out[int(1.5 * SR)] == 0 and out[int(0.5 * SR)] == 1 and out[int(2.5 * SR)] == 1
    assert np.abs(np.diff(out)).max() < 0.01
