"""CLI.

arena play --player reflex --levels 1-1 1-2              real time, 60 fps
arena play --player reflex --levels all --fps 0          real time, unpaced
arena play --player reflex --turn-based --frames 4       step mode: emulator waits for the player
arena play --player players/mine.py --record             any file defining PLAYER = ...
arena play --player script --arg path=steps.json --turn-based
arena play --player manual --turn-based                  you type the macros
arena replay runs/<id> --record                          re-run a run's own trace
arena compare runs/<a> runs/<b>                          side by side (harness must match)
arena actions                                            the macro vocabulary
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from arena.actions import MACROS
from arena.harness import ALL_LEVELS, Harness
from arena.players import load


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arena")
    sub = parser.add_subparsers(dest="cmd", required=True)

    play = sub.add_parser("play")
    play.add_argument("--player", required=True, help="name, path/to/file.py or module:Class")
    play.add_argument("--arg", action="append", default=[], help="key=value for the player")
    play.add_argument("--levels", nargs="+", default=["1-1"])
    play.add_argument("--fps", type=float, default=60.0, help="real time pace; 0 = unpaced")
    play.add_argument("--turn-based", action="store_true", help="emulator waits for the player")
    play.add_argument("--frames", type=int, default=8, help="turn-based: frames per step")
    play.add_argument("--retries", type=int, default=3)
    play.add_argument("--record", action="store_true", help="video.mp4 per attempt")
    play.add_argument("--runs-dir", type=Path, default=Path("runs"))
    play.add_argument("--run-id")
    play.add_argument("-v", "--verbose", action="store_true")

    replay = sub.add_parser("replay")
    replay.add_argument("run", type=Path)
    replay.add_argument("--record", action="store_true")
    replay.add_argument("--fps", type=float, default=0.0)

    cmp = sub.add_parser("compare")
    cmp.add_argument("runs", nargs="+", type=Path)
    sub.add_parser("actions")
    args = parser.parse_args(argv)

    if args.cmd == "actions":
        for macro in MACROS.values():
            print(f"{macro.name:<22} {macro.description}")
        return 0
    if args.cmd == "compare":
        return compare([_load_run(p) for p in args.runs])
    if args.cmd == "replay":
        return replay_run(args.run, record=args.record, fps=args.fps)

    kwargs = dict(item.split("=", 1) for item in args.arg)
    levels = ALL_LEVELS if args.levels == ["all"] else args.levels
    harness = Harness(
        load(args.player, **kwargs),
        levels,
        fps=args.fps,
        turn_based=args.turn_based,
        frames_per_step=args.frames,
        retries=args.retries,
        record=args.record,
        runs_dir=args.runs_dir,
        run_id=args.run_id,
        verbose=args.verbose,
    )
    results = harness.run()
    print(f"cleared {results['cleared']}/{len(levels)} -> {harness.run_dir}")
    return 0


def replay_run(run: Path, *, record: bool, fps: float) -> int:
    """Replay each level's last attempt from its trace, with the same harness settings."""
    meta = _load_run(run)
    from arena.players.script import ScriptPlayer

    for lv in meta["levels"]:
        attempt = run / "levels" / lv["level"] / f"attempt-{lv['attempts']}" / "trace.jsonl"
        player = ScriptPlayer(str(attempt))
        player.name = f"replay-{meta['player']}"
        harness = Harness(
            player,
            [lv["level"]],
            fps=fps,
            turn_based=True,
            frames_per_step=1,
            retries=1,
            record=record,
            runs_dir=run.parent,
            run_id=f"{run.name}-replay",
        )
        harness.run()
    return 0


def compare(runs: list[dict]) -> int:
    keys = ("schema", "vocab_hash", "fps", "turn_based", "frames_per_step", "retries")
    configs = [{k: r["harness"].get(k) for k in keys} for r in runs]
    if any(c != configs[0] for c in configs):
        print("harness settings differ; results are not comparable:")
        for r, c in zip(runs, configs, strict=True):
            print(f"  {r['player']:<16} {c}")
        print()
    levels = sorted({lv["level"] for r in runs for lv in r["levels"]}, key=_level_key)
    print(f"{'level':<7}" + "".join(f"{r['player']:>26}" for r in runs))
    for level in levels:
        cells = []
        for r in runs:
            lv = next((x for x in r["levels"] if x["level"] == level), None)
            if lv is None:
                cells.append("-")
            else:
                outcome = "CLEAR" if lv["cleared"] else f"x={lv['best_x']}"
                cells.append(f"{outcome} ({lv['attempts']}t, {lv['decisions']}d)")
        print(f"{level:<7}" + "".join(f"{c:>26}" for c in cells))
    print(f"{'cleared':<7}" + "".join(f"{r.get('cleared', 0):>26}" for r in runs))
    return 0


def _load_run(path: Path) -> dict:
    return json.loads((path / "run.json" if path.is_dir() else path).read_text())


def _level_key(level: str) -> tuple[int, int]:
    w, s = level.split("-")
    return int(w), int(s)


def play_main() -> int:
    """`uv run play --player reflex ...` == `uv run arena play ...`."""
    return main(["play", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
