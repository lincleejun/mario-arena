"""The player contract. Anything that implements it can play: code, Jev, an LLM, a script, a human.

    class MyPlayer:
        name = "my-player"                      # shows up in results
        info = {"model": "...", "notes": "..."}   # optional, copied into run.json
        frames = 8                              # optional, turn-based default frames per step

        def reset(self, level: str) -> None: ...          # a level (or a retry of it) starts
        def act(self, obs: Observation) -> Instruction: ... # see below

An instruction is a macro name from arena.actions.MACROS, or (macro, frames), or
{"macro": ..., "frames": ...}. None keeps the current instruction. In real-time mode `act`
runs in its own thread and `frames` is ignored; in turn-based mode the emulator waits for
`act` and then runs the instruction for `frames` frames.

Loading: `--player NAME` for a registered player, `--player path/to/file.py` for a module
that defines `PLAYER = MyPlayer`, or `--player package.module:ClassName`. Constructor
keyword arguments come from `--arg key=value`.
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from typing import Any, Protocol

from arena.ram import Observation

Instruction = str | tuple[str, int] | dict[str, Any] | None


class Player(Protocol):
    name: str

    def reset(self, level: str) -> None: ...

    def act(self, obs: Observation) -> Instruction: ...


REGISTRY = {
    "runner": "arena.players.runner:RunnerPlayer",
    "reflex": "arena.players.reflex:ReflexPlayer",
    "script": "arena.players.script:ScriptPlayer",
    "manual": "arena.players.manual:ManualPlayer",
}


def load(spec: str, **kwargs: Any) -> Player:
    spec = REGISTRY.get(spec, spec)
    if spec.endswith(".py"):
        path = Path(spec)
        module_spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        cls = getattr(module, "PLAYER", None)
        if cls is None:
            raise SystemExit(f"{spec} must define PLAYER = <player class>")
    elif ":" in spec:
        module_name, attr = spec.split(":", 1)
        cls = getattr(importlib.import_module(module_name), attr)
    else:
        raise SystemExit(f"unknown player {spec!r}; registered: {', '.join(REGISTRY)}")
    return cls(**kwargs)
