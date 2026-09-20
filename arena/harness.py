"""The harness: owns the emulator, pacing, level progression, retries, records and results.

Players only decide. Two paces:

- real time (default): the emulator runs at `fps`; `player.act` runs in its own thread and is
  offered the newest World whenever it is free. A slow player sees fewer frames; its last
  instruction stays in effect. `fps=0` removes the pacing (same semantics, fastest possible).
- turn based (`turn_based=True`): the emulator waits for `player.act`, then executes the
  instruction for `frames` frames, then asks again. Latency-free and reproducible.

An instruction is a macro name, or `(macro, frames)`, or `{"macro": ..., "frames": ...}`.
Every run writes `runs/<id>/` with run.json, per-attempt trace.jsonl and result.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arena.actions import BUTTON_COMBOS, MACROS, Executor
from arena.players import Player
from arena.ram import Observation, WorldMap, decode

ARENA_VERSION = "0.1.0"
SCHEMA = "1"
ALL_LEVELS = [f"{w}-{s}" for w in range(1, 9) for s in range(1, 5)]
VOCAB_HASH = hashlib.sha256(",".join(sorted(MACROS)).encode()).hexdigest()[:12]


def make_env(level: str, render: bool):
    warnings.filterwarnings("ignore")
    import gym_super_mario_bros  # noqa: F401  (registers the envs)
    import gymnasium as gym
    from nes_py.wrappers import JoypadSpace

    env = gym.make(f"SuperMarioBros-{level}-v0", render_mode="rgb_array" if render else None)
    return JoypadSpace(env, BUTTON_COMBOS)


def parse_instruction(raw: Any, default_frames: int) -> tuple[str | None, int]:
    """Accept a macro name, (macro, frames) or {"macro", "frames"}; None keeps the current."""
    if raw is None:
        return None, default_frames
    if isinstance(raw, str):
        return raw, default_frames
    if isinstance(raw, (tuple, list)) and len(raw) == 2:
        return str(raw[0]), int(raw[1])
    if isinstance(raw, dict):
        return raw.get("macro"), int(raw.get("frames", default_frames))
    raise ValueError(f"bad instruction {raw!r}")


class PlayerThread:
    """Runs player.act off the emulator thread; the newest instruction is picked up each frame."""

    def __init__(self, player: Player) -> None:
        self.player = player
        self.free = threading.Event()
        self.free.set()
        self.result: Any = None
        self.decisions = 0
        self.errors = 0
        self.act_ms = 0.0
        self._obs: Observation | None = None
        self._go = threading.Event()
        self._stop = False
        threading.Thread(target=self._loop, daemon=True, name=f"player-{player.name}").start()

    def offer(self, obs: Observation) -> None:
        if self.free.is_set():
            self.free.clear()
            self._obs = obs
            self._go.set()

    def take(self) -> Any:
        result, self.result = self.result, None
        return result

    def close(self) -> None:
        self._stop = True
        self._go.set()

    def _loop(self) -> None:
        while not self._stop:
            self._go.wait()
            self._go.clear()
            if self._stop or self._obs is None:
                continue
            started = time.perf_counter()
            try:
                self.result = self.player.act(self._obs)
                self.decisions += 1
            except Exception as exc:  # noqa: BLE001 - a broken player must not stop the arena
                self.errors += 1
                self.result = None
                print(f"player error: {exc!r}")
            self.act_ms += (time.perf_counter() - started) * 1000
            self.free.set()


class Harness:
    def __init__(
        self,
        player: Player,
        levels: list[str],
        *,
        fps: float = 60.0,
        turn_based: bool = False,
        frames_per_step: int = 8,
        retries: int = 3,
        record: bool = False,
        runs_dir: Path = Path("runs"),
        run_id: str | None = None,
        max_frames: int = 60 * 400,
        verbose: bool = False,
    ) -> None:
        self.player, self.levels = player, levels
        self.fps, self.turn_based, self.frames_per_step = fps, turn_based, frames_per_step
        self.retries, self.record, self.max_frames = retries, record, max_frames
        self.verbose = verbose
        self.trace_from = int(os.environ.get("ARENA_TRACE", "0"))  # per-frame stdout log from here
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        self.run_dir = runs_dir / (run_id or f"{stamp}-{player.name}")
        self.config = {
            "schema": SCHEMA,
            "arena_version": ARENA_VERSION,
            "vocab_hash": VOCAB_HASH,
            "fps": fps,
            "turn_based": turn_based,
            "frames_per_step": frames_per_step if turn_based else None,
            "retries": retries,
            "max_frames": max_frames,
        }

    # ------------------------------------------------------------------ run
    def run(self) -> dict[str, Any]:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        results: dict[str, Any] = {
            "run_id": self.run_dir.name,
            "player": self.player.name,
            "player_info": getattr(self.player, "info", {}),
            "harness": self.config,
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "levels": [],
        }
        self._write(self.run_dir / "run.json", results)
        for level in self.levels:
            result = self.play_level(level)
            results["levels"].append(result)
            print(
                f"{level}: {'CLEAR' if result['cleared'] else 'fail'} attempts={result['attempts']} "
                f"best_x={result['best_x']} time_left={result['time_left']} "
                f"decisions={result['decisions']} wall={result['wall_s']:.1f}s"
            )
            self._write(self.run_dir / "run.json", results)
            if not result["cleared"]:
                break
        results["cleared"] = sum(r["cleared"] for r in results["levels"])
        results["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        self._write(self.run_dir / "run.json", results)
        return results

    def play_level(self, level: str) -> dict[str, Any]:
        attempts, best_x, started = 0, 0, time.perf_counter()
        env = make_env(level, render=self.record)
        thread = None if self.turn_based else PlayerThread(self.player)
        decisions = errors = 0
        act_ms = 0.0
        try:
            while attempts < self.retries:
                attempts += 1
                outcome = self._attempt(env, level, attempts, thread)
                best_x = max(best_x, outcome["max_x"])
                decisions += outcome["decisions"]
                errors += outcome["errors"]
                act_ms += outcome["act_ms"]
                if outcome["cleared"]:
                    break
        finally:
            if thread is not None:
                thread.close()
            env.close()
        return {
            "level": level,
            "cleared": outcome["cleared"],
            "attempts": attempts,
            "best_x": best_x,
            "frames": outcome["frames"],
            "time_left": outcome["time_left"],
            "decisions": decisions,
            "player_errors": errors,
            "player_ms_mean": round(act_ms / decisions, 2) if decisions else None,
            "wall_s": round(time.perf_counter() - started, 2),
            "last_reason": outcome["reason"],
        }

    # -------------------------------------------------------------- attempt
    def _attempt(self, env, level: str, attempt: int, thread: PlayerThread | None):
        _, info = env.reset()
        self.player.reset(level)
        world, executor, ram = WorldMap(), Executor(), env.unwrapped.ram
        attempt_dir = self.run_dir / "levels" / level / f"attempt-{attempt}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        writer = self._writer(attempt_dir)
        trace = (attempt_dir / "trace.jsonl").open("w")
        frame, max_x, reason, macro = 0, 0, "", None
        decisions = errors = 0
        act_ms = 0.0
        frame_time = 1.0 / self.fps if self.fps > 0 and not self.turn_based else 0.0
        next_tick = time.perf_counter()
        terminated = truncated = False
        try:
            while frame < self.max_frames and not (terminated or truncated):
                obs = decode(ram, info, world, level, frame)
                max_x = max(max_x, obs.mario.x)
                hold = 1
                if self.turn_based:
                    started = time.perf_counter()
                    try:
                        raw = self.player.act(obs)
                        decisions += 1
                    except Exception as exc:  # noqa: BLE001
                        errors += 1
                        raw = None
                        print(f"player error: {exc!r}")
                    act_ms += (time.perf_counter() - started) * 1000
                    macro, hold = parse_instruction(
                        raw, getattr(self.player, "frames", self.frames_per_step)
                    )
                else:
                    thread.offer(obs)
                    macro, _ = parse_instruction(thread.take(), 1)
                if macro is not None:
                    if macro not in MACROS:
                        print(f"player returned unknown macro {macro!r}; ignored")
                        macro = None
                    else:
                        executor.set(MACROS[macro], obs.mario.grounded)
                        reason = str(getattr(self.player, "reason", "") or macro)
                        self._log(trace, obs, macro, hold, reason)
                for _ in range(hold):
                    grounded = int(ram[0x001D]) == 0
                    index = executor.action_index(grounded)
                    if self.trace_from and frame >= self.trace_from:
                        self._stdout_trace(frame, obs, index, reason)
                    _, _, terminated, truncated, info = env.step(index)
                    frame += 1
                    if writer is not None:
                        writer.append_data(env.render())
                    if terminated or truncated:
                        break
                    if frame_time:
                        next_tick += frame_time
                        delay = next_tick - time.perf_counter()
                        if delay > 0:
                            time.sleep(delay)
        finally:
            trace.close()
            if writer is not None:
                writer.close()
        if thread is not None:
            decisions, errors, act_ms = thread.decisions, thread.errors, thread.act_ms
            thread.decisions = thread.errors = 0
            thread.act_ms = 0.0
        cleared = bool(info.get("flag_get"))
        result = {
            "level": level,
            "attempt": attempt,
            "cleared": cleared,
            "max_x": max_x,
            "frames": frame,
            "time_left": int(info.get("time", 0)),
            "reason": reason,
            "decisions": decisions,
            "errors": errors,
            "act_ms": act_ms,
        }
        self._write(attempt_dir / "result.json", result)
        print(
            f"  attempt {attempt}: {'flag' if cleared else 'lost'} x={max_x} frames={frame} "
            f"time_left={result['time_left']} decisions={decisions} last={reason}"
        )
        return result

    # -------------------------------------------------------------- helpers
    def _log(self, trace, obs: Observation, macro: str, hold: int, reason: str) -> None:
        line = {
            "frame": obs.frame,
            "x": obs.mario.x,
            "y": obs.mario.y_screen,
            "grounded": obs.mario.grounded,
            "enemies": [(e.kind, e.dx) for e in obs.enemies],
            "macro": macro,
            "frames": hold,
            "reason": reason,
        }
        trace.write(json.dumps(line) + "\n")
        if self.verbose:
            print(
                f"f{obs.frame:05d} x={obs.mario.x:04d} {macro} x{hold} ({reason}) {line['enemies']}"
            )

    @staticmethod
    def _stdout_trace(frame: int, obs: Observation, index: int, reason: str) -> None:
        near = [(e.kind, e.dx, e.row - obs.mario.row) for e in obs.enemies]
        print(
            f"t f{frame} x={obs.mario.x} y={obs.mario.y_screen} g={int(obs.mario.grounded)} "
            f"vx={obs.mario.vx} vy={obs.mario.vy} btn={sorted(BUTTON_COMBOS[index])} {reason} {near}"
        )

    def _writer(self, attempt_dir: Path):
        if not self.record:
            return None
        import imageio.v2 as imageio

        return imageio.get_writer(attempt_dir / "video.mp4", fps=60, quality=8, macro_block_size=1)

    @staticmethod
    def _write(path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2))
