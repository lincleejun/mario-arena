"""Grid-search a reflex constant offline, unpaced. No API, ~1 s per run.

.venv/bin/python scripts/tune.py ENEMY_JUMP_DEFAULT_PX 24 32 40 48
.venv/bin/python scripts/tune.py ENEMY_JUMP_DEFAULT_PX 26 30 --set ENEMY_JUMP_MACRO=jump_long --level 1-2
"""

from __future__ import annotations

import argparse
import contextlib
import io

from arena.harness import Harness
from arena.players import reflex
from arena.players.reflex import ReflexPlayer

parser = argparse.ArgumentParser()
parser.add_argument("name")
parser.add_argument("values", nargs="+")
parser.add_argument("--level", default="1-1")
parser.add_argument("--set", action="append", default=[], help="NAME=VALUE preset, repeatable")
args = parser.parse_args()
for preset in args.set:
    name, raw = preset.split("=", 1)
    setattr(reflex, name, int(raw) if raw.lstrip("-").isdigit() else raw)
for raw in args.values:
    value = int(raw) if raw.lstrip("-").isdigit() else raw
    setattr(reflex, args.name, value)
    with contextlib.redirect_stdout(io.StringIO()):
        result = Harness(ReflexPlayer(), [args.level], fps=0, retries=1).play_level(args.level)
    print(
        f"{args.name}={value!s:<12} {'CLEAR' if result['cleared'] else 'x=' + str(result['best_x']):<9}"
        f" time_left={result['time_left']} last={result['last_reason']}"
    )
