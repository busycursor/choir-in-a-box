import numpy as np
import pytest

from chorale import room

SR = room.SR


def tone(secs=2.0, f=220):
    t = np.arange(int(secs * SR)) / SR
    return sum(0.2 / k * np.sin(2 * np.pi * k * f * t) for k in range(1, 6))


def test_impulse_is_stereo_decorrelated_and_decays():
    ir = room.impulse(room.ROOMS['church'])
    assert ir.ndim == 2 and ir.shape[1] == 2
    assert abs(len(ir) / SR - (2.4 + 0.03)) < 0.1
    assert abs(np.corrcoef(ir[:, 0], ir[:, 1])[0, 1]) < 0.2
    head, tail = np.abs(ir[:SR // 4]).mean(), np.abs(ir[-SR // 4:]).mean()
    assert tail < head / 20


def test_pan_is_equal_power():
    left, _ = room.place(tone(), room.Seat(-1, room.TYPICAL_DISTANCE))
    assert np.abs(left[:, 1]).max() < 1e-9
    mid, _ = room.place(tone(), room.Seat(0, room.TYPICAL_DISTANCE))
    assert np.allclose(np.abs(mid[:, 0]).max(), np.abs(mid[:, 1]).max())


def test_further_back_is_quieter_with_more_room():
    near, near_send = room.place(tone(), room.Seat(0, 0.3))
    far, far_send = room.place(tone(), room.Seat(0, 0.8))
    assert np.sqrt(np.mean(far ** 2)) < np.sqrt(np.mean(near ** 2))
    assert far_send > near_send


def test_mix_peaks_at_or_below_minus_one_dbfs():
    out = room.mix([(tone(), room.Seat(-0.5, 0.35), 'Soprano'), (tone(f=330), room.Seat(0.5, 0.5), 'Bass')], room.ROOMS['church'])
    assert out.shape[1] == 2
    assert np.abs(out).max() <= room.PEAK + 1e-6
    assert len(out) / SR > 2.0 + 1.0   # the tail rings on past the singing


def test_section_seats_spread_around_its_place():
    s = room.seats('Tenor', 5)
    assert len(s) == 5
    pans = [x.pan for x in s]
    assert pans == sorted(pans) and pans[-1] - pans[0] == pytest.approx(room.SECTION_WIDTH)
    assert np.mean(pans) == pytest.approx(room.SECTIONS['Tenor'].pan)


def test_parts_are_level_matched_then_balanced():
    loud, quiet = 4 * tone(f=262), 0.25 * tone(f=196)
    out = room.balanced([(loud, room.Seat(0, 0.3), 'Tenor'), (quiet, room.Seat(0, 0.3), 'Soprano')])
    tenor, soprano = room.loudness(out[0][0]), room.loudness(out[1][0])
    assert soprano - tenor == pytest.approx(room.BALANCE['Soprano'] - room.BALANCE['Tenor'], abs=0.1)


def test_a_section_is_balanced_as_a_whole():
    a, b = tone(f=196), tone(f=197)
    solo = room.balanced([(a, room.Seat(0, 0.3), 'Bass')])
    pair = room.balanced([(a, room.Seat(0, 0.3), 'Bass'), (b, room.Seat(0.1, 0.3), 'Bass')])
    assert room.loudness(pair[0][0] + pair[1][0]) == pytest.approx(room.loudness(solo[0][0]), abs=0.1)


def test_each_phrase_swells_and_eases_into_its_cadence():
    phrases = [[0.0, 4.0], [4.5, 8.5]]
    g = 20 * np.log10(room.phrasing(10 * SR, phrases, offset=0.5))
    at = lambda t: g[int(t * SR)]
    mid1, end1 = 0.5 + 0.55 * 4, 0.5 + 3.9
    assert at(mid1) > at(0.6) and at(mid1) > at(end1)
    assert at(0.5 + 4.5 + 0.55 * 4) < at(mid1)        # the last phrase a little softer
    assert np.abs(np.diff(g)).max() < 0.01            # smooth: no step anywhere
