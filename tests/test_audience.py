import numpy as np

from chorale import audience

SR = audience.SR


def music(secs=20.0):
    t = np.arange(int(secs * SR)) / SR
    x = 0.1 * np.sin(2 * np.pi * 220 * t)
    return np.stack([x, x], 1)


def sounds(tmp_path):
    import soundfile as sf
    chosen = {}
    for kind in audience.LEVEL:
        f = tmp_path / f'{kind}.wav'
        secs = 8.0 if kind.startswith('applause') else 1.0     # applause runs on, the rest are short
        sf.write(f, 0.2 * np.random.default_rng(len(kind)).standard_normal(int(secs * SR)), SR)
        chosen[kind] = [f]
    return chosen


PHRASES = [[0.0, 4.0], [5.0, 9.0], [10.0, 14.0], [15.0, 19.0]]


def test_the_stage_settles_just_before_and_applause_after(tmp_path):
    out = audience.live(music(), PHRASES, 0.5, sounds(tmp_path))
    before = out[:int(audience.PRE * SR)]
    calm = audience.live(music(), PHRASES, 0.5, sounds(tmp_path), liveliness=0.0)[:int(audience.PRE * SR)]
    rms = lambda x: np.sqrt(np.mean(x ** 2))
    assert rms(before) > 2 * rms(calm)                  # the stage settling, softly, over the room
    after = out[int((audience.PRE + 0.5 + 19 + 1.0) * SR):]
    assert np.abs(after).max() > 0.01                   # applause


def test_nobody_is_only_the_room(tmp_path):
    m = music()
    out = audience.live(m, PHRASES, 0.5, sounds(tmp_path), liveliness=0.0)
    n = len(out)
    room_only = audience.room_air(n) + audience.hiss(n)
    assert np.allclose(out[:int(audience.PRE * SR)], room_only[:int(audience.PRE * SR)], atol=1e-6)   # air alone


def test_livelier_is_busier(tmp_path):
    m = music(60.0)
    phrases = [[a, a + 4.0] for a in np.arange(0.0, 56.0, 5.0)]
    calm = audience.live(m, phrases, 0.5, sounds(tmp_path), seed=2, liveliness=0.2)
    rowdy = audience.live(m, phrases, 0.5, sounds(tmp_path), seed=2, liveliness=0.9)
    gaps = lambda x: sum(np.abs(x[int((audience.PRE + 0.5 + b + 0.2) * SR):int((audience.PRE + 0.5 + b + 0.8) * SR)]).max() for _, b in phrases[:-1])
    assert gaps(rowdy) > gaps(calm)


def test_room_air_is_quiet_and_stereo():
    air = audience.room_air(5 * SR)
    assert air.shape == (5 * SR, 2)
    assert abs(np.corrcoef(air[:, 0], air[:, 1])[0, 1]) < 0.5
    assert np.abs(air).max() < 0.02


def test_a_conductor_intro_comes_before_the_music(tmp_path):
    import soundfile as sf
    take = tmp_path / 'line.wav'
    t = np.arange(int(2.0 * SR)) / SR
    sf.write(take, 0.2 * np.sin(2 * np.pi * 150 * t) * (1 + np.sin(2 * np.pi * 3 * t)), SR)
    m = music()
    plain = audience.live(m, PHRASES, 0.5, sounds(tmp_path), seed=4)
    spoken = audience.live(m, PHRASES, 0.5, sounds(tmp_path), seed=4, intro=take)
    assert len(spoken) - len(plain) > 2.0 * SR          # the intro extends the start by at least his line
    lead = audience.INTRO_IN + 2.0
    rms = lambda x: np.sqrt(np.mean(x ** 2))
    assert rms(spoken[int(audience.INTRO_IN * SR):int(lead * SR)]) > 3 * rms(spoken[:int(0.8 * SR)])   # he's heard


def test_a_short_line_hardly_moves_a_speech_wanders():
    from chorale import conductor
    tone_ = lambda secs: 0.2 * np.sin(2 * np.pi * 150 * np.arange(int(secs * SR)) / SR)
    swing = lambda x: np.ptp(20 * np.log10(np.convolve(np.abs(x[:, 0]) + np.abs(x[:, 1]), np.ones(SR // 10) / (SR // 10), 'valid') + 1e-9))
    short = conductor.staged(tone_(2.0), seed=5)
    speech = conductor.staged(tone_(20.0), seed=5)
    assert swing(short) < swing(speech)


def test_below_a_rowdy_audience_nothing_starts_while_they_sing(tmp_path):
    events = []
    audience.live(music(), PHRASES, 0.5, sounds(tmp_path), seed=3, liveliness=0.5, events=events)
    singing = [(audience.PRE + 0.5 + a + 0.1, audience.PRE + 0.5 + b - 0.1) for a, b in PHRASES]
    for at, kind in events:
        if 'under the music' in kind:
            continue   # the audience's own background, carrying on as they settle
        assert not any(a < at < b for a, b in singing), (at, kind)


def test_a_rowdy_audience_coughs_while_they_sing(tmp_path):
    events = []
    phrases = [[a, a + 9.5] for a in np.arange(0.0, 110.0, 10.0)]
    audience.live(music(120.0), phrases, 0.5, sounds(tmp_path), seed=3, liveliness=0.95, events=events)
    assert any(kind == 'cough (while they sing)' for _, kind in events)


def test_people_settle_over_seconds_not_at_the_first_note(tmp_path):
    rms = lambda x: np.sqrt(np.mean(x ** 2))
    m = music(30.0) * 0
    out = audience.live(m, [[0.0, 29.0]], 0.5, sounds(tmp_path), seed=6, liveliness=0.6)
    hall = out - (audience.room_air(len(out)) + audience.hiss(len(out)))   # the audience alone, the room's air taken out
    start = audience.PRE + 0.5
    just_after = hall[int(start * SR):int((start + 2) * SR)]
    later = hall[int((start + 15) * SR):int((start + 17) * SR)]
    assert rms(just_after) > 0                      # still there after the first note
    assert rms(later) < rms(just_after)             # and quieter once they've settled


def test_held_sounds_are_let_go_as_it_ends(tmp_path):
    events = []
    audience.live(music(), PHRASES, 0.5, sounds(tmp_path), seed=6, liveliness=0.7, events=events)
    assert any('let go' in k for _, k in events)


def test_the_audience_only_settles_once_it_hears_the_choir():
    r = lambda t: audience.restlessness(t, baton_up=4.0, start=5.0, last_end=60.0)
    assert r(3.0) == 1.0                                     # before the baton: nobody knows
    assert r(4.5) == audience.AT_BATON >= 0.7                # baton up: a few hush, a little
    assert r(5.0 + audience.REACT_S / 2) == audience.AT_BATON  # the first note: nobody's reacted yet
    assert r(5.0 + audience.REACT_S + 1.0) < audience.AT_BATON
    assert r(20.0) < 0.3                                     # settled, but never silent
    after = lambda t: audience.restlessness(t, baton_up=4.0, start=5.0, last_end=60.0, clap_at=61.0)
    assert after(60.5) == audience.SETTLED                   # still, in the silence after the last chord
    assert after(61.0 + audience.LET_GO_S) == 1.0            # at ease once the applause is going


def test_the_audience_is_still_going_as_the_choir_comes_in(tmp_path):
    rms = lambda x: np.sqrt(np.mean(x ** 2))
    out = audience.live(music() * 0, PHRASES, 0.5, sounds(tmp_path), seed=6, liveliness=0.6)
    hall = out - (audience.room_air(len(out)) + audience.hiss(len(out)))
    start = audience.PRE + 0.5
    assert rms(hall[int((start - 0.5) * SR):int(start * SR)]) > 0


def test_nobody_moves_in_the_silence_before_the_applause(tmp_path):
    for seed in range(5):
        events = []
        audience.live(music(), PHRASES, 0.5, sounds(tmp_path), seed=seed, liveliness=0.8, events=events)
        clap = next(at for at, k in events if k == 'applause')
        let_go = sorted(at for at, k in events if 'let go' in k)
        assert all(at > clap for at in let_go)                                   # only once the clapping starts
        assert all(b - a >= audience.RELEASE_GAP for a, b in zip(let_go, let_go[1:]))   # spread out


def test_the_track_ends_with_the_applause(tmp_path):
    for seed in range(4):
        events = []
        out = audience.live(music(), PHRASES, 0.5, sounds(tmp_path), seed=seed, liveliness=0.9, events=events)
        clap = next(at for at, k in events if k == 'applause')
        end = clap + 8.0                    # the fixture's applause: eight seconds of noise
        assert all(at < end - 0.9 for at, k in events if 'let go' in k)      # nothing after the clapping
        assert len(out) / SR <= end + audience.TAIL_S + 0.05                 # and that's the end of the track


def test_the_conductor_is_found_or_designed(monkeypatch):
    from chorale import conductor
    calls = []
    def api(path, body=None):
        calls.append(path)
        if path.startswith('/v2/voices'):
            return {'voices': voices}
        if path == '/v1/text-to-voice/design':
            assert body['voice_description'] == conductor.DESCRIPTION
            return {'previews': [{'generated_voice_id': 'g1'}]}
        return {'voice_id': 'new'}
    monkeypatch.setattr(conductor, '_api', api)
    monkeypatch.delenv('CONDUCTOR_VOICE_ID', raising=False)
    voices = [{'name': 'Conductor', 'voice_id': 'mine'}]
    assert conductor.voice_id() == 'mine' and len(calls) == 1          # an account that has him uses him
    voices = []
    assert conductor.voice_id() == 'new' and calls[-1] == '/v1/text-to-voice'   # one that doesn't designs him from the brief
    monkeypatch.setenv('CONDUCTOR_VOICE_ID', 'chosen')
    assert conductor.voice_id() == 'chosen'
