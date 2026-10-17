"""One tempo map for every part of a piece, so the whole ensemble slows, holds
and moves on together. Score positions are in quarter notes; the map turns
them into seconds.

  intro_bars  bars the accompaniment plays alone first: the score's first full
              bars (from entry_q), with a pickup landing at the end of the
              intro the way it leads into those bars in the song
  entry_q     the first bar line at or after the first sung note (0 without a
              pickup)
  rubato      a slight lean at the end of each four-bar phrase, and a
              broadening ritardando over the last two bars
  swing       eighths swung: an offbeat eighth (or the sixteenth after a dotted
              eighth, the way swing charts write it) lands on the third of the
              beat's triplet; triplets stay as written
  holds       {score position: seconds} of time added there (a breath after a
              fermata): a note ending there ends before it, one starting there
              starts after it
  fermatas    [(start, end)] of each fermata note, read as a chorale is sung
              (instead of rubato): a little slowing over the beat into each,
              the note held FERMATA times as long, and the last one broader,
              slowing over the whole last bar and held FINAL times as long

score_parts.py writes the map into the parts file.
"""
import math

class TempoMap:
    STEP = 1 / 48  # quarters per integration step
    FERMATA, FINAL = 1.5, 3.0           # a fermata note's length, as a multiple of its written length (a closing quarter rings as a dotted half)
    CADENCE, CADENCE_SLOW = 1.0, 0.12   # quarters of slowing into a fermata, and how much by the end of them
    FINAL_SLOW = 0.25                   # ...into the last one, over its whole bar

    def __init__(self, bpm, bar_q, total_q, intro_bars=0, rubato=False, holds=None, entry_q=0.0, swing=False, fermatas=None):
        self.bpm, self.bar_q, self.total_q, self.entry_q, self.swing = bpm, bar_q, total_q, entry_q, swing
        self.intro_bars, self.rubato = intro_bars, rubato
        self.holds = {float(k): v for k, v in (holds or {}).items()}
        self.fermatas = sorted((float(a), float(b)) for a, b in (fermatas or []))
        n = int(math.ceil(total_q / self.STEP)) + 1
        self._t = [0.0]
        for i in range(n):
            q = (i + 0.5) * self.STEP
            self._t.append(self._t[-1] + self.STEP * 60 / (bpm * self.speed(q)))

    def speed(self, q):
        """Tempo factor at score position q (1 = as marked)."""
        if self.fermatas: return self._chorale(q)
        if not self.rubato: return 1.0
        f = 1.0
        phrase = 4 * self.bar_q
        into = (q % phrase) / phrase
        if into > 0.85: f *= 1 - 0.10 * (into - 0.85) / 0.15   # lean into the phrase's end
        rit = self.total_q - 2 * self.bar_q
        if q > rit: f *= 1 - 0.32 * ((q - rit) / (2 * self.bar_q)) ** 1.5  # broaden to the end
        return max(0.5, f)

    def _chorale(self, q):
        for k, (a, b) in enumerate(self.fermatas):
            last = k == len(self.fermatas) - 1
            if a - 1e-9 <= q < b:
                return 1 / (self.FINAL if last else self.FERMATA)
            lead, slow = (self.bar_q, self.FINAL_SLOW) if last else (self.CADENCE, self.CADENCE_SLOW)
            if a - lead <= q < a:
                return 1 - slow * ((q - (a - lead)) / lead) ** 2
        return 1.0

    def _swung(self, q):
        if not self.swing: return q
        beat = math.floor(q + 1e-9)
        f = q - beat
        for straight, swung in ((0.5, 2 / 3), (0.75, 2 / 3), (0.25, 1 / 3)):
            if abs(f - straight) < 1e-6: return beat + swung
        return q

    def _at(self, q):
        q = self._swung(q)
        i = min(len(self._t) - 2, max(0, int(q / self.STEP)))
        frac = q / self.STEP - i
        return self._t[i] + (self._t[i + 1] - self._t[i]) * frac

    @property
    def intro_s(self):
        """How long the intro runs before the song's own beat 0 (a pickup bar
        overlaps the intro's last bar)."""
        if not self.intro_bars: return 0.0
        e = self.entry_q
        return self._at(e + self.intro_bars * self.bar_q) - 2 * self._at(e)

    def start(self, q):
        """When something starting at q starts (holds at q already taken)."""
        return self.intro_s + self._at(q) + sum(v for k, v in self.holds.items() if k <= q + 1e-6)

    def end(self, q):
        """When something ending at q ends (before a hold at q)."""
        return self.intro_s + self._at(q) + sum(v for k, v in self.holds.items() if k < q - 1e-6)

    def intro(self, q):
        """When something in the intro's bars (entry_q on) plays during the intro."""
        return self._at(q) - self._at(self.entry_q)

    def to_json(self):
        return {'bpm': self.bpm, 'bar_q': self.bar_q, 'total_q': self.total_q, 'intro_bars': self.intro_bars,
                'rubato': self.rubato, 'holds': self.holds, 'entry_q': self.entry_q, 'swing': self.swing,
                'fermatas': self.fermatas}

    @classmethod
    def from_json(cls, d):
        return cls(d['bpm'], d['bar_q'], d['total_q'], d['intro_bars'], d['rubato'], d['holds'], d.get('entry_q', 0.0),
                   d.get('swing', False), d.get('fermatas'))
