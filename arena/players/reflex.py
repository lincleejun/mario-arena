"""First real player: a rule-based engine on the accumulated map. No model, no pixels.

Priorities, highest first: pits, walls, enemies, then run. Every LEFT checks the ground behind.
Timing constants were measured offline in SMB 1-1 (see typesafe-mario/scripts/tune.py).
"""

from __future__ import annotations

from typing import ClassVar

from arena.ram import MAP_ROWS, TILE, Enemy, Observation, WorldMap

APPROACH_TILES = 8
NARROW_PIT_TILES = 2
LANDING_ZONE_PX = 56
WAIT_MAX_FRAMES = 150
STALL_VX = 8  # RAM speed units; walking is ~28, running ~48
RETREAT_TO_TILES = 5
RETREAT_MAX_FRAMES = 90
ENEMY_VISIBLE_PX = 128
# Enemies are cleared by a running jump over them, issued at this distance. Tuned offline on
# 1-1 (scripts/tune.py): 32 and 48 clear, 40 does not; stomping in place needed 26 with a long
# jump and was slower. A per-kind override is the knob for taller enemies.
ENEMY_JUMP_PX: dict[str, int] = {}
ENEMY_JUMP_DEFAULT_PX = 32
ENEMY_JUMP_MACRO = "run_right_jump_long"
BEHIND_MACRO = "jump_long"  # an enemy walking up from behind: jump in place, it passes under
ENEMY_BEHIND_PX = 48
STATIONARY_FRAMES = 60


class ReflexPlayer:
    name = "reflex"
    info: ClassVar[dict] = {"approach": "rules: pit > wall > enemy > run, tuned offline on 1-1"}
    frames = 1  # turn-based: decide every frame; its timing is frame-precise

    def __init__(self) -> None:
        self.reset("")

    def reset(self, level: str) -> None:
        self.jump_frame = -100  # frame of the last jump macro; the harness commits it
        self.jump_reason = ""
        self.retreat = 0
        self.wait = 0
        self.stationary = 0
        self.last_enemy_dx: int | None = None
        self.reason = ""

    # ------------------------------------------------------------------ act
    def act(self, obs: Observation) -> str | None:
        macro = self._decide(obs)
        if macro is not None and macro.endswith(("jump_short", "jump_long")):
            self.jump_frame, self.jump_reason = obs.frame, self.reason
        return macro

    def _decide(self, obs: Observation) -> str | None:
        m, world = obs.mario, obs.world
        pit = self._pit_distance(world, m.col, m.row)
        if not m.grounded:
            past_pit = pit is None and self._supported(world, m.col, m.row)
            if self.jump_reason == "gap" and past_pit:
                self.reason = "air-brake"
                return "left"  # pit cleared: land right past the edge, never in the unknown
            self.reason = "air"
            return None
        if obs.frame - self.jump_frame < 4:
            return None  # takeoff in progress; RAM still says grounded for a frame or two

        wall, height = self._wall(world, m.col, m.row)
        enemy = self._nearest(obs.enemies, m.row)

        # P1: pits (unless a wall is closer, e.g. a staircase step before the gap)
        if pit is not None and pit <= APPROACH_TILES and not (wall is not None and wall < pit):
            width = self._pit_width(world, m.col, m.row)
            narrow = width <= NARROW_PIT_TILES
            if pit <= 1:
                zone = (width + 1) * TILE + LANDING_ZONE_PX
                if enemy is not None and 0 <= enemy.dx <= zone and self.wait < WAIT_MAX_FRAMES:
                    self.wait += 1
                    self.reason = "wait:landing-zone"
                    return "noop"
                self.wait = 0
                self.reason = "gap"
                return "right_jump_long" if narrow else "run_right_jump_long"
            self.reason = "walk-up" if narrow else "sprint"
            return "right" if narrow else "run_right"

        # P2: walls
        if self.retreat:
            self.retreat -= 1
            if enemy is not None and -ENEMY_BEHIND_PX <= enemy.dx < 0:
                self.reason = "retreat:behind"
                return BEHIND_MACRO
            if (
                wall is not None
                and wall < RETREAT_TO_TILES
                and self.retreat
                and self._ground_behind(world, m.col, m.row)
            ):
                self.reason = "retreat"
                return "left"
            self.retreat = 0
        if wall is not None:
            small = height <= 1 or (pit is not None and pit <= APPROACH_TILES)
            if wall <= 1 and abs(m.vx) < STALL_VX and not small:
                if self._ground_behind(world, m.col, m.row):
                    self.retreat = RETREAT_MAX_FRAMES
                    self.reason = "retreat"
                    return "left"
                self.reason = "obstacle:no-runup"
                return "run_right_jump_long"
            if wall <= max(1, min(height - 1, 3)):
                self.reason = "obstacle"
                if height <= 1:
                    return "right_jump_short"
                return "right_jump_long" if small else "run_right_jump_long"

        # P3: enemies: stop, let them come, stomp in place; jump over the ones that never come
        if enemy is not None and 0 <= enemy.dx <= ENEMY_VISIBLE_PX:
            approaching = self.last_enemy_dx is not None and enemy.dx < self.last_enemy_dx
            self.stationary = 0 if approaching else self.stationary + 1
            self.last_enemy_dx = enemy.dx
            if enemy.dx <= ENEMY_JUMP_PX.get(enemy.kind, ENEMY_JUMP_DEFAULT_PX):
                self.reason = f"over:{enemy.kind}"
                return ENEMY_JUMP_MACRO
            if self.stationary >= STATIONARY_FRAMES:
                self.reason = f"over-still:{enemy.kind}"
                return ENEMY_JUMP_MACRO
            self.reason = f"wait:{enemy.kind}"
            return "noop"
        self.last_enemy_dx = None
        self.stationary = 0
        if enemy is not None and -ENEMY_BEHIND_PX <= enemy.dx < 0:
            self.reason = f"behind:{enemy.kind}"
            return BEHIND_MACRO

        # P4: sprint at walls, otherwise run
        self.reason = "sprint" if wall is not None and wall <= APPROACH_TILES else "run"
        return "run_right"

    # -------------------------------------------------------------- terrain
    @staticmethod
    def _supported(world: WorldMap, col: int, row: int) -> bool:
        return any(world.solid(col, r) for r in range(row + 1, MAP_ROWS))

    def _pit_distance(self, world: WorldMap, col: int, row: int) -> int | None:
        for c in range(col + 1, col + APPROACH_TILES + 1):
            if not world.known(c):
                return None
            if not self._supported(world, c, row):
                return c - col
        return None

    def _pit_width(self, world: WorldMap, col: int, row: int) -> int:
        width = 0
        for c in range(col + 1, col + APPROACH_TILES + 9):
            supported = self._supported(world, c, row) or not world.known(c)
            if supported and width:
                break
            if not supported:
                width += 1
        return width

    def _wall(self, world: WorldMap, col: int, row: int) -> tuple[int | None, int]:
        """Distance and height of the first solid tile at Mario's row or above, ahead."""
        ground = next((r for r in range(row + 1, MAP_ROWS) if world.solid(col, r)), MAP_ROWS)
        for c in range(col + 1, col + APPROACH_TILES + 1):
            height = 0
            r = ground - 1
            while r >= 0 and world.solid(c, r):
                height += 1
                r -= 1
            if height:
                return c - col, height
        return None, 0

    def _ground_behind(self, world: WorldMap, col: int, row: int) -> bool:
        return all(self._supported(world, c, row) for c in (col - 1, col - 2))

    @staticmethod
    def _nearest(enemies: list[Enemy], row: int) -> Enemy | None:
        live = [e for e in enemies if e.hostile and abs(e.row - row) <= 1]
        ahead = [e for e in live if e.dx >= 0]
        if ahead:
            return min(ahead, key=lambda e: e.dx)
        behind = [e for e in live if e.dx < 0]
        return max(behind, key=lambda e: e.dx) if behind else None
