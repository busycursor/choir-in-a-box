import numpy as np

from chorale import sing_parts

SEGS = [{'time': [0, 2000], 'content': [150, 1850]}, {'time': [2500, 4000], 'content': [2650, 3850]}]


def test_first_singer_sings_as_written():
    assert sing_parts.jittered(SEGS, 'Alto', 0) == SEGS


def test_other_singers_move_a_little_and_repeatably():
    a = sing_parts.jittered(SEGS, 'Alto', 1)
    assert a == sing_parts.jittered(SEGS, 'Alto', 1)
    assert a != sing_parts.jittered(SEGS, 'Alto', 2)
    for s, o in zip(a, SEGS):
        d = s['time'][0] - o['time'][0]
        assert abs(d) <= sing_parts.JITTER_MS and s['time'][0] >= 0
        assert s['content'][0] - o['content'][0] == d


def test_section_keeps_one_singers_loudness():
    t = np.arange(24000) / 24000
    a, b = 0.2 * np.sin(2 * np.pi * 220 * t), 0.2 * np.sin(2 * np.pi * 221 * t)
    out = sing_parts.section([a, b[:20000]])
    rms = lambda x: np.sqrt(np.mean(x ** 2))
    assert len(out) == 24000
    assert abs(rms(out) - np.mean([rms(a), rms(b[:20000])])) < 1e-6
