"""Replay a fixed list of instructions. No intelligence: proves the harness runs without AI.

    arena play --player script --arg path=scripts/1-1-opening.json --turn-based
    arena play --player script --arg path=runs/<id>/levels/1-1/attempt-1/trace.jsonl

The file is a JSON list of {"macro": ..., "frames": ...} or a trace.jsonl written by the
harness (one such object per line). Frames are counted from the start of the level, so the
same file works in real time and turn based. After the last entry the last macro is kept.
"""

from __future__ import annotations

import json
from pathlib import Path

from arena.ram import Observation


class ScriptPlayer:
    name = "script"

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        text = self.path.read_text()
        entries = (
            [json.loads(line) for line in text.splitlines() if line.strip()]
            if self.path.suffix == ".jsonl"
            else json.loads(text)
        )
        self.steps: list[tuple[int, str, int]] = []  # (start_frame, macro, frames)
        start = 0
        for entry in entries:
            frames = int(entry.get("frames", 8))
            start = int(entry.get("frame", start))
            self.steps.append((start, entry["macro"], frames))
            start += frames
        self.info = {"path": str(self.path), "steps": len(self.steps)}
        self.index = 0
        self.sent = -1  # each entry is sent once; re-sending a jump after landing would re-jump
        self.reason = ""

    def reset(self, level: str) -> None:
        self.index = 0
        self.sent = -1

    def act(self, obs: Observation) -> tuple[str, int] | None:
        while self.index + 1 < len(self.steps) and self.steps[self.index + 1][0] <= obs.frame:
            self.index += 1
        start, macro, frames = self.steps[self.index]
        if obs.frame < start or self.sent == self.index:
            return None
        self.sent = self.index
        self.reason = f"step {self.index + 1}/{len(self.steps)}"
        return macro, max(1, start + frames - obs.frame)
