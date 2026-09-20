"""Baseline: hold run-right forever. Dies at the first goomba; every real player must beat it."""

from __future__ import annotations

from arena.ram import Observation


class RunnerPlayer:
    name = "runner"

    def reset(self, level: str) -> None:
        pass

    def act(self, obs: Observation) -> str | None:
        return "run_right"
