import numpy as np

from chorale import organ
from chorale.accompany import Note

SR = organ.SR


def peak_hz(x):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return f[np.argmax(spec * (f > 30))]


def test_an_8ft_pipe_sounds_at_pitch_and_a_4ft_an_octave_up():
    p8 = organ.pipe(organ.GREAT['Principal 8'], 57, 1.0, seed=1)
    flute4 = organ.pipe(organ.SWELL['Flute 4'], 57, 1.0, seed=1)
    assert abs(peak_hz(p8[SR // 4:SR]) - 220) < 3
    assert abs(peak_hz(flute4[SR // 4:SR]) - 440) < 5


def test_a_stopped_flute_is_mostly_odd_harmonics():
    x = organ.pipe(organ.SWELL['Gedackt 8'], 45, 1.0, seed=1)[SR // 4:SR]
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))); f = np.fft.rfftfreq(len(x), 1 / SR)
    at = lambda hz: spec[np.argmin(abs(f - hz))]
    assert at(330) > 3 * at(220)       # the third harmonic over the second


def test_the_same_seed_is_the_same_organ():
    notes = [Note(0.0, 0.5, 60, voice='great'), Note(0.0, 0.5, 48, voice='pedal')]
    a = organ.play(notes, organ.REGISTRATIONS['chorale'], seed=3)
    b = organ.play(notes, organ.REGISTRATIONS['chorale'], seed=3)
    assert np.array_equal(a, b)


def test_closing_the_swell_box_makes_it_quieter_and_darker():
    x = np.random.default_rng(0).standard_normal((SR, 2))
    rms = lambda y: np.sqrt(np.mean(y ** 2))
    shut, half, open_ = (organ.swell_box(x, o) for o in (0.0, 0.5, 1.0))
    assert rms(shut) < rms(half) < rms(open_)


def test_a_coupler_adds_the_other_divisions_stops():
    notes = [Note(0.0, 0.5, 60, voice='great')]
    plain = organ.Registration(great=('Principal 8',), swell=('Oboe 8',))
    coupled = organ.Registration(great=('Principal 8',), swell=('Oboe 8',), swell_to_great=True)
    rms = lambda y: np.sqrt(np.mean(y ** 2))
    a, b = organ.play(notes, plain), organ.play(notes, coupled)
    assert not np.allclose(a, b)          # the oboe now sounds with the principal
