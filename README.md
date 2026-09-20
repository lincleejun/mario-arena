# mario-arena

A harness that lets anything play Super Mario Bros. from RAM state: a rule engine, a script,
a human at the keyboard, Jev, an LLM. No pixels are read anywhere. Players only decide; the
harness owns the emulator, pacing, frame-precise button presses, retries, level progression
and results, so every player is compared on the same terms. Design notes: `docs/DESIGN.md`.
Brief for agents writing a player: `task.md`.

```bash
uv sync   # once; every `uv run` below keeps the env in sync
uv run arena actions                                          # the macro vocabulary
uv run play --player reflex --levels 1-1                # real time, 60 fps
uv run play --player reflex --levels all --fps 0        # real time, unpaced
uv run play --player reflex --turn-based --frames 4     # step mode: waits for the player
uv run play --player players/mine.py --record           # any file with PLAYER = ...
uv run play --player script --arg path=steps.json --turn-based
uv run play --player manual --turn-based                # type macros yourself
uv run arena replay runs/<id> --record                        # re-run a run from its trace
uv run arena compare runs/<a> runs/<b>                        # side by side
```

The pip package `gym-super-mario-bros` ships the game data; check that its use is lawful for you.

## Two paces

- **Real time** (default): the emulator runs at `--fps` (0 = unpaced). `act` runs in its own
  thread; a fast player sees every frame, a slow one sees fewer and its last instruction
  stays in effect. Measures the player including its latency.
- **Turn based** (`--turn-based`): the emulator waits for `act`, runs the instruction for
  `frames` frames (`--frames`, or the player's own `frames` attribute, or the instruction's),
  then asks again. Latency-free and reproducible.

`compare` refuses to line up runs whose harness settings differ.

## The player contract

```python
class MyPlayer:
    name = "my-player"
    info = {"author": "...", "approach": "..."}   # copied into run.json
    frames = 8                                    # turn-based default frames per step

    def reset(self, level: str) -> None: ...      # a level (or a retry of it) starts
    def act(self, obs: Observation) -> str | tuple[str, int] | dict | None: ...
```

Copy `players/TEMPLATE.py`. Return a macro name from `arena actions`, `(macro, frames)`,
`{"macro": ..., "frames": ...}`, or `None` to keep the current instruction. Load with
`--player NAME` (registered), `--player path/file.py` (defines `PLAYER = MyPlayer`) or
`--player module:Class`; constructor arguments via `--arg key=value`.

`obs` is an `arena.ram.Observation`: level, frame, time left, Mario (world x, tile col/row,
speed, grounded, size, lives), enemies (kind, world x, row, dx to Mario, hostile) and the
accumulated `WorldMap` of every tile column seen so far. `obs.view()` gives an ascii window
with `M`, `E` and `?` for unseen columns; `obs.to_dict()` gives JSON.

Jumps are committed by the harness: `*_jump_short` holds A for 6 frames (~2 tiles),
`*_jump_long` until landing. Until landing, later instructions only steer. The harness inserts
the release frame a fresh press needs. Sending a jump macro again after landing starts a new jump.

## Every run is a directory

```
runs/<id>/
  run.json                       harness settings, player info, per-level results
  levels/1-1/attempt-1/
    trace.jsonl                  one line per instruction: frame, x, y, enemies, macro, frames, reason
    result.json                  outcome and cause
    video.mp4                    with --record
```

`arena replay runs/<id>` feeds the trace back through the `script` player and reproduces the
run frame for frame (the emulator is deterministic). `ARENA_TRACE=<frame>` prints one line per
frame from that frame on: position, speed, buttons, enemies.

## Players so far

- `runner`: hold run-right. The floor; dies at the first goomba.
- `reflex`: rules with priorities pit > wall > enemy > run, tuned offline. Clears 1-1 in both
  paces; reaches 1241 on 1-2, fails the first big gap of 1-3 and the first lava pit of 1-4.
- `script`: replays a JSON list or a trace.jsonl. No intelligence; proves the loop runs without AI.
- `manual`: a human, one instruction per step, turn-based.

## Tuning without a model or an API

`scripts/tune.py NAME v1 v2 ... [--set NAME=VALUE] [--level 1-1]` grid-searches a reflex
constant unpaced, about one second per run.
