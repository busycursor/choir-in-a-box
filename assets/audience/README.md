# Audience sounds

ElevenLabs sound effects (eleven_text_to_sound_v2), generated from the prompts in
`chorale/audience.py` and kept only after being picked by ear. Each kind is
`<kind>_a.mp3`, `<kind>_b.mp3`, ...; the mix draws one at random each time.

- `false_start_*` are for programmes of several pieces (not used yet).
  `false_start_b` runs long: trim it to its first ~2.5 s. `false_start_c` works
  best with the next piece starting while it's still trailing off.
- `applause_*` is the normal ending; `applause_hesitant_*` starts slowly, as
  after a sacred piece; `applause_finale_*` has cheering, for a last piece.
