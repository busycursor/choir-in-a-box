from chorale import choir_skill, ensemble, skill
from chorale.accompany import Note

PHRASES = [(0.5 + 8 * k, 0.5 + 8 * k + 7.5) for k in range(8)]
PARTS = ['Soprano', 'Alto', 'Tenor', 'Bass']
BEAT = 60 / 72


def test_without_an_accompanist_the_choir_falls_on_its_own():
    p = ensemble.plan(0.1, None, PHRASES, PARTS, 0, BEAT)
    assert p['choir'] == choir_skill.collapses(PHRASES, 0.1, 0, PARTS) and p['accompanist'] == []


def test_a_good_accompanist_plays_straight_through_a_collapse():
    p = ensemble.plan(0.1, 0.8, PHRASES, PARTS, 0, BEAT)
    assert p['choir'] and not [e for e in p['accompanist'] if e['kind'] == 'give_up']


def test_a_weaker_one_rallies_gives_up_and_comes_back_by_the_entrance():
    for seed in range(10):
        p = ensemble.plan(0.1, 0.2, PHRASES, PARTS, seed, BEAT)
        for e in p['accompanist']:
            if e['kind'] == 'give_up':
                c = next(c for c in p['choir'] if c['fall'] == e['fall'])
                assert e['rally'] < e['stop'] < e['back'] <= c['cue']


def test_when_the_choir_falls_apart_for_good_the_accompanist_gives_up_after_rallying():
    for seed in range(10):
        p = ensemble.plan(0.0, 0.9, PHRASES, PARTS, seed, BEAT)
        final = next(c for c in p['choir'] if c.get('final'))
        up = [e for e in p['accompanist'] if e['kind'] == 'give_up' and e['fall'] == final['fall']]
        assert len(up) == 1 and 'back' not in up[0]
        assert 0.8 * BEAT < up[0]['stop'] - final['fall'] < 7.5 * BEAT        # a few beats rallying, not a long struggle
        for t0, t1 in up[0]['tries']:                                        # leading in to an entrance the choir then tries
            assert t0 > up[0]['stop'] and final['cues'][0] > t0


def test_a_poor_accompanist_gives_up_on_them_sooner():
    stop = lambda a: next(e['stop'] - e['fall'] for e in ensemble.plan(0.0, a, PHRASES, PARTS, 3, BEAT)['accompanist']
                          if e['kind'] == 'give_up')
    assert stop(0.05) < stop(0.9)


def test_a_weak_choir_falls_with_a_breaking_accompanist_and_a_good_one_sings_on():
    fell = sum(any('falls with it' in line for line in ensemble.plan(0.1, 0.1, PHRASES, PARTS, s, BEAT)['log']) for s in range(20))
    assert fell > 0
    for s in range(20):
        assert ensemble.plan(0.9, 0.1, PHRASES, PARTS, s, BEAT)['choir'] == []


def test_giving_up_keeps_only_the_rally_the_tries_and_the_return():
    notes = [Note(t * 0.5, t * 0.5 + 0.4, 60, 0.6, 'm') for t in range(80)]
    out = skill.given_up(notes, {'rally': 5.0, 'stop': 10.0, 'back': 30.0, 'tries': [(20.0, 22.0)]})
    starts = [n.start for n in out]
    assert all(s < 10 or 20 <= s < 22 or s >= 30 for s in starts)
    assert 15.0 not in starts and 25.0 not in starts and 21.0 in starts and 35.0 in starts
    assert all(n.velocity > 0.6 for n in out if 5 <= n.start < 10)            # playing on harder to rally them


def test_with_a_hopeless_accompanist_it_sometimes_goes_first():
    first = 0
    for seed in range(20):
        p = ensemble.plan(0.0, 0.0, PHRASES, PARTS, seed, BEAT)
        final = next(c for c in p['choir'] if c.get('final'))
        up = next(e for e in p['accompanist'] if e['kind'] == 'give_up' and e['fall'] == final['fall'])
        assert up['stop'] - up['fall'] < 2 * BEAT and not up['tries']        # stops with them, and doesn't try again
        first += up['stop'] < up['fall']
    assert 0 < first < 20


def test_the_audience_hears_the_end_where_the_piece_fell_apart():
    import numpy as np
    from chorale import finish
    from chorale.sing_parts import LEAD_IN
    sr = 24000
    music = np.zeros((int(20 * sr), 2))
    music[:int((LEAD_IN + 9.0) * sr)] = 0.3                                  # it stops 9 s into the score
    phrases = [[0.0, 7.5], [8.0, 15.5], [16.0, 19.0]]
    heard = finish.heard_phrases(music, phrases, {'choir': [{'fall': 8.5, 'final': True}]})
    assert len(heard) == 2 and abs(heard[-1][1] - (9.0 + finish.UNSURE_S)) < 0.1
    assert finish.heard_phrases(music, phrases, {'choir': []}) == phrases     # a piece that ends, ends as written
