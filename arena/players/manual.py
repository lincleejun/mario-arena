"""A human at the keyboard, one instruction per step. Turn-based only.

    arena play --player manual --turn-based --frames 8

Each step prints the ascii view and reads a line: `run_right`, `right_jump_long 12`,
an empty line to repeat the last instruction, `?` for the vocabulary, `q` to quit.
"""

from __future__ import annotations

from arena.actions import MACROS
from arena.ram import Observation


class ManualPlayer:
    name = "manual"

    def __init__(self) -> None:
        self.last = "noop"
        self.reason = ""

    def reset(self, level: str) -> None:
        print(f"--- {level} ---")

    def act(self, obs: Observation) -> tuple[str, int] | None:
        m = obs.mario
        print("\n".join(obs.view(back=6, ahead=18)))
        print(
            f"frame={obs.frame} x={m.x} vx={m.vx} grounded={m.grounded} time={obs.time_left} "
            f"enemies={[(e.kind, e.dx) for e in obs.enemies]}"
        )
        while True:
            line = input(f"[{self.last}] > ").strip()
            if line == "q":
                raise SystemExit("quit")
            if line == "?":
                for macro in MACROS.values():
                    print(f"  {macro.name:<22} {macro.description}")
                continue
            parts = line.split()
            macro = parts[0] if parts else self.last
            if macro not in MACROS:
                print(f"unknown macro {macro!r} (? lists them)")
                continue
            frames = int(parts[1]) if len(parts) > 1 else 8
            self.last = macro
            self.reason = "human"
            return macro, frames
