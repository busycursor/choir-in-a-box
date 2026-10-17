# Audience sounds

ElevenLabs sound effects (eleven_text_to_sound_v2), generated from the prompts in
`chorale/audience.py` and kept only after being picked by ear. Each kind is
`<kind>_a.mp3`, `<kind>_b.mp3`, ...; the mix draws one at random each time.

- `false_start_*` are for programmes of several pieces (not used yet).
  `false_start_b` runs long: trim it to its first ~2.5 s. `false_start_c` works
  best with the next piece starting while it's still trailing off.
- `applause_*` is the normal ending; `applause_hesitant_*` starts slowly, as
  after a sacred piece; `applause_finale_*` has cheering, for a last piece.
- After a poor performance (`audience.reaction()`, set by the choir's and
  accompanist's skill; never boos): `applause_scattered_*` a few people, out of
  time with each other; `applause_bewildered_*` two or three unsure claps
  trailing off; `applause_one_*` one person clapping alone; `bravo_*` one
  voice shouting "Bravo!" anyway, now and then below 0.2 (spoken by ElevenLabs stock
  voices, not the sound-effects model, which gave a crowd shouting in Spanish).
- `fussing_*` and `crying_*` are babies, heard only in a rowdy hall (liveliness
  0.7 and up), at any moment, music or not.
- Phones aren't kept here: they're whatever ringtones are in
  `engine/audience/ringtones/` (none there, no phone).
