import numpy as np

from chorale import breathing

# A long line: twelve two-second held notes, no rests (24 s of singing)
ROWS = [[60, 2.0, 'la', '', 2, 0, 1] for _ in range(12)]


def test_a_soloist_breathes_only_at_rests():
    assert breathing.plan(ROWS, 1, offset=0.5) == [[]]


def test_section_singers_breathe_through_a_long_line():
    gaps = breathing.plan(ROWS, 5, offset=0.5, seed=1)
    assert all(len(g) >= 2 for g in gaps)          # everyone breathes in 24 s of singing
    for g in gaps:
        for a, b in zip(g, g[1:]):
            assert b[0] - a[1] >= breathing.AIR[0] - 2.0   # and not again straight away


def test_neighbours_never_breathe_together_and_never_too_many():
    gaps = breathing.plan(ROWS, 5, offset=0.5, seed=1)
    overlap = lambda x, y: x[0] < y[1] and y[0] < x[1]
    for k in range(4):
        assert not any(overlap(x, y) for x in gaps[k] for y in gaps[k + 1])
    for t in np.arange(0, 25, 0.01):
        assert sum(any(a <= t < b for a, b in g) for g in gaps) <= max(1, int(5 * breathing.AT_ONCE))


def test_breaths_fall_inside_notes_never_on_a_word_start():
    gaps = breathing.plan(ROWS, 5, offset=0.5, seed=1)
    starts = [0.5 + 2.0 * i for i in range(12)]
    for g in gaps:
        for a, b in g:
            assert all(not (a - 0.1 <= s <= b + 0.1) for s in starts)


def test_rests_refill_everyones_air():
    rows = [[60, 3.0, 'la', '', 2, 0, 1], [None, 0.5, None, None, 1, None, None]] * 6
    assert all(g == [] for g in breathing.plan(rows, 5, offset=0.0, seed=1))


def test_apply_fades_out_and_back_in():
    sr = 1000
    out = breathing.apply(np.ones(3 * sr), [(1.0, 1.3)], sr)
    assert out[int(1.1 * sr)] == 0 and out[int(0.5 * sr)] == 1 and out[int(2.0 * sr)] == 1
    assert np.abs(np.diff(out)).max() < 0.05
