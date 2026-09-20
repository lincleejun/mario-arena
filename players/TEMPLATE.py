"""Copy me to players/<yourname>.py and fill in act(). Run with:

    .venv/bin/arena play --player players/<yourname>.py --levels 1-1 --fps 0
    .venv/bin/arena play --player players/<yourname>.py --levels all --fps 0 --retries 3

Everything you may use is on `obs` (arena.ram.Observation):
    obs.level, obs.frame, obs.time_left
    obs.mario: x, y_screen, col, row, vx, vy, grounded, size, lives
    obs.enemies: list of Enemy(kind, x, row, dx, hostile)
    obs.world: WorldMap with .solid(col, row), .known(col), .rows(col_from, col_to)
    obs.view(back, ahead) -> ascii rows;  obs.to_dict() -> JSON
Return a macro name (see `arena actions`), or (macro, frames), or None to keep going.
"""

from __future__ import annotations

from typing import ClassVar

from arena.ram import Observation


class MyPlayer:
    name = "template"  # change me: it is the column header in `arena compare`
    info: ClassVar[dict] = {"author": "?", "approach": "?"}  # copied into run.json
    frames = 8  # turn-based default: how many frames each instruction runs

    def reset(self, level: str) -> None:
        pass

    def act(self, obs: Observation) -> str | tuple[str, int] | None:
        self.reason = "always run"  # shown in traces and -v output
        return "run_right"


PLAYER = MyPlayer
