"""Claude's player: an arc planner over the accumulated map. No model, no pixels.

Idea: the only thing that kills a rule player is a jump that ends in the wrong place. So this
player never picks a jump by rule of thumb. It carries measured jump arcs (dx, dy per frame for
standing / walking / running takeoffs, short and long A holds), and at every grounded frame it
simulates each candidate against the tile map: a jump is valid only if Mario's body never enters
a solid tile and his feet come down on known solid ground past the hazard. Among valid jumps it
takes the one that lands closest past the hazard (jump only as far as needed), and it chooses the
approach speed that makes such a jump exist. Enemies: wait for them, then jump over them if the
ceiling allows, else stomp in place with a short hop. Every LEFT checks the ground behind.
"""

from __future__ import annotations

from typing import ClassVar

from arena.ram import MAP_ROWS, TILE, Enemy, Observation, WorldMap

# Measured on SMB 1-1 flat ground (scratch script): per frame (dx px, height px) from takeoff to
# landing. Takeoff speed decides the arc; "short" = A held 6 frames, "long" = A until landing.
ARCS: dict[tuple[str, str], list[tuple[int, int]]] = {
    ("stand", "short"): [
        (0, 0),
        (0, 5),
        (0, 10),
        (0, 14),
        (0, 19),
        (1, 23),
        (1, 26),
        (2, 30),
        (2, 33),
        (3, 36),
        (4, 37),
        (4, 38),
        (5, 39),
        (6, 38),
        (7, 37),
        (8, 36),
        (9, 34),
        (10, 31),
        (11, 27),
        (13, 23),
        (14, 18),
        (15, 13),
        (17, 8),
        (18, 3),
        (20, 0),
    ],
    ("stand", "long"): [
        (0, 0),
        (0, 5),
        (0, 10),
        (0, 14),
        (0, 19),
        (1, 23),
        (1, 26),
        (2, 30),
        (2, 34),
        (3, 37),
        (4, 40),
        (4, 43),
        (5, 46),
        (6, 48),
        (7, 51),
        (8, 53),
        (9, 55),
        (10, 57),
        (11, 58),
        (13, 60),
        (14, 61),
        (15, 62),
        (17, 63),
        (18, 63),
        (20, 64),
        (21, 64),
        (23, 64),
        (25, 64),
        (27, 63),
        (28, 62),
        (30, 60),
        (32, 57),
        (34, 54),
        (35, 50),
        (37, 45),
        (39, 40),
        (41, 35),
        (42, 30),
        (44, 25),
        (46, 20),
        (48, 15),
        (49, 10),
        (51, 5),
        (53, 0),
    ],
    ("walk", "short"): [
        (1, 0),
        (3, 5),
        (5, 10),
        (7, 14),
        (8, 19),
        (10, 23),
        (12, 27),
        (14, 30),
        (15, 34),
        (17, 36),
        (19, 38),
        (21, 40),
        (22, 41),
        (24, 41),
        (26, 41),
        (28, 40),
        (29, 39),
        (31, 37),
        (33, 34),
        (35, 31),
        (36, 28),
        (38, 24),
        (40, 19),
        (42, 14),
        (43, 9),
        (45, 4),
        (47, 0),
    ],
    ("walk", "long"): [
        (1, 0),
        (3, 5),
        (5, 10),
        (7, 14),
        (8, 19),
        (10, 23),
        (12, 27),
        (14, 30),
        (15, 34),
        (17, 37),
        (19, 41),
        (21, 44),
        (22, 46),
        (24, 49),
        (26, 52),
        (28, 54),
        (29, 56),
        (31, 58),
        (33, 60),
        (35, 62),
        (36, 63),
        (38, 64),
        (40, 65),
        (42, 66),
        (43, 67),
        (45, 68),
        (47, 68),
        (49, 68),
        (50, 68),
        (52, 68),
        (54, 68),
        (56, 66),
        (57, 64),
        (59, 62),
        (61, 59),
        (63, 56),
        (64, 52),
        (66, 47),
        (68, 42),
        (70, 37),
        (71, 32),
        (73, 27),
        (75, 22),
        (77, 17),
        (78, 12),
        (80, 7),
        (82, 2),
        (84, 0),
    ],
    ("run", "short"): [
        (3, 0),
        (6, 6),
        (9, 12),
        (12, 18),
        (15, 23),
        (18, 28),
        (21, 33),
        (24, 38),
        (27, 42),
        (30, 45),
        (33, 47),
        (36, 49),
        (39, 49),
        (42, 49),
        (45, 48),
        (48, 46),
        (51, 44),
        (54, 40),
        (57, 36),
        (60, 31),
        (63, 26),
        (66, 21),
        (69, 16),
        (72, 11),
        (75, 6),
        (78, 1),
        (81, 0),
    ],
    ("run", "long"): [
        (3, 0),
        (6, 6),
        (9, 12),
        (12, 18),
        (15, 23),
        (18, 28),
        (21, 33),
        (24, 38),
        (27, 42),
        (30, 47),
        (33, 51),
        (36, 54),
        (39, 58),
        (42, 61),
        (45, 65),
        (48, 68),
        (51, 70),
        (54, 73),
        (57, 75),
        (60, 77),
        (63, 79),
        (66, 81),
        (69, 82),
        (72, 83),
        (75, 84),
        (78, 85),
        (81, 85),
        (84, 86),
        (87, 86),
        (90, 86),
        (93, 85),
        (96, 83),
        (99, 80),
        (102, 77),
        (105, 73),
        (108, 68),
        (111, 63),
        (114, 58),
        (117, 53),
        (120, 48),
        (123, 43),
        (126, 38),
        (129, 33),
        (132, 28),
        (135, 23),
        (138, 18),
        (141, 13),
        (144, 8),
        (147, 3),
        (150, 0),
    ],
    ("stand", "up"): [
        (0, 0),
        (0, 5),
        (0, 10),
        (0, 14),
        (0, 19),
        (0, 23),
        (0, 26),
        (0, 30),
        (0, 33),
        (0, 36),
        (0, 37),
        (0, 38),
        (0, 39),
        (0, 38),
        (0, 37),
        (0, 36),
        (0, 34),
        (0, 31),
        (0, 27),
        (0, 23),
        (0, 18),
        (0, 13),
        (0, 8),
        (0, 3),
        (0, 0),
    ],
}

LOOKAHEAD = 8  # tiles of map the planner looks at
WALL_LOOKAHEAD = 4
STAND_VX, WALK_VX = 10, 40  # |vx| below these: standing / walking profile, else running
APPROACH = {"stand": "noop", "walk": "right", "run": "run_right"}  # how to reach each takeoff speed
JUMP = {
    ("stand", "short"): "right_jump_short",
    ("stand", "long"): "right_jump_long",
    ("walk", "short"): "right_jump_short",
    ("walk", "long"): "right_jump_long",
    ("run", "short"): "right_jump_short",
    ("run", "long"): "run_right_jump_long",
    ("stand", "up"): "jump_short",
}
ENEMY_VISIBLE_PX = 128
ENGAGE_PX = 48  # closer than this an approaching enemy gets jumped over or stomped
STOMP_PX = {"koopa": 18, "koopa_red": 18, "paratroopa": 18}  # blind hop thresholds per kind
STOMP_DEFAULT_PX = 16  # a goomba this close walks under a 25-frame hop and gets stomped
FALL_BRAKE_AFTER = 60  # frames since the last jump: only a walk-off fall gets air-braked
TALL = {"koopa", "koopa_red", "paratroopa", "hammer_bro", "piranha_plant"}  # 24 px tall
CONTACT_FRAMES = 2  # collisions predicted this early are already happening; nothing to plan
BEHIND_PX = 40
ENEMY_ROWS = 3  # enemies this many rows up or down still matter (treetop koopas)
DEFAULT_ENEMY_VX = 0.6  # px/frame, goombas and koopas; measured
FOOT_IN = 4  # landing needs solid ground under both x+FOOT_IN and x+15-FOOT_IN
SETTLE_FRAMES = 3  # after landing, vx needs a few grounded frames before it means anything
VELOCITY_WINDOW = 8  # frames of enemy positions averaged for its speed
IGNORED = frozenset({"enemy_1d"})  # firebars: not a body to stomp or jump over; pass by luck


PROFILE_VX = {"stand": 0, "walk": 28, "run": 48}  # the takeoff speeds the arcs were measured at


def profile(vx: int) -> str:
    return "stand" if abs(vx) < STAND_VX else "walk" if abs(vx) < WALK_VX else "run"


def arc_for(vx: int, hold: str) -> list[tuple[int, int]]:
    """Arc at an arbitrary takeoff speed: the nearest measured arc, dx scaled between neighbours."""
    v = min(abs(vx), PROFILE_VX["run"])
    lo, hi = ("stand", "walk") if v <= PROFILE_VX["walk"] else ("walk", "run")
    span = PROFILE_VX[hi] - PROFILE_VX[lo]
    t = (v - PROFILE_VX[lo]) / span
    base = ARCS[(hi if t >= 0.5 else lo, hold)]
    reach = ARCS[(lo, hold)][-1][0] + t * (ARCS[(hi, hold)][-1][0] - ARCS[(lo, hold)][-1][0])
    factor = reach / max(1, base[-1][0])
    return [(round(dx * factor), up) for dx, up in base]


class ClaudePlayer:
    name = "claude"
    info: ClassVar[dict] = {
        "author": "Claude (Claude Code session)",
        "approach": "arc planner: measured jump tables simulated against the tile map and "
        "predicted enemy positions; shortest valid landing wins; approach speed chosen so "
        "that a valid jump exists",
    }
    frames = 1

    def __init__(self) -> None:
        self.reset("")

    def reset(self, level: str) -> None:
        self.plan_frames = 0
        self.jump_frame = -100
        self.planned_until = -1  # frame until which the current jump was simulated safe
        self.tracks: list[tuple[str, list[int]]] = []
        self.enemy_vx: dict[int, float] = {}
        self.streak = 0
        self.reason = ""

    # ------------------------------------------------------------------ act
    def act(self, obs: Observation) -> str | None:
        self._track(obs.enemies)
        self.streak = self.streak + 1 if obs.mario.grounded else 0
        macro = self._decide(obs)
        if macro is not None and "jump" in macro:
            self.jump_frame = obs.frame
            self.planned_until = obs.frame + self.plan_frames
        return macro

    def _decide(self, obs: Observation) -> str | None:
        m, world = obs.mario, obs.world
        if not m.grounded:
            if obs.frame - self.jump_frame <= FALL_BRAKE_AFTER:
                self.reason = "air"
                return None  # a jump in flight: steering would break the simulated arc
            landing_threat = any(
                e.hostile and e.kind not in IGNORED and 0 <= e.dx <= 28 and abs(e.row - m.row) <= 1
                for e in obs.enemies
            )
            self.reason = "air-brake" if landing_threat else "air"
            return "left" if landing_threat else None  # land short of an enemy waiting below
        if obs.frame - self.jump_frame < 4:
            return None  # takeoff in progress; RAM still says grounded for a frame or two

        enemies = self._relevant(obs.enemies, m.row)
        pit = self._pit_distance(world, m.col, m.row)
        wall, wall_height = self._wall_distance(world, m.col, m.row)
        hazard = None
        if pit is not None and pit <= LOOKAHEAD:
            hazard = ("pit", (m.col + pit) * TILE)
        if wall is not None and wall <= WALL_LOOKAHEAD and (pit is None or wall < pit):
            hazard = ("wall", (m.col + wall) * TILE)
        ahead = [e for e in enemies if 0 <= e.dx <= ENEMY_VISIBLE_PX]
        behind = [e for e in enemies if -BEHIND_PX <= e.dx < 0]

        # 1. an enemy close ahead is the most urgent thing on the screen
        if ahead and min(e.dx for e in ahead) <= ENGAGE_PX:
            return self._engage(obs, enemies, hazard)
        # 2. terrain: a pit or wall in sight -> the jump, or the approach that enables one
        if hazard is not None and hazard[0] == "wall" and wall_height == 1:
            # a single step (staircases): walk up to it and hop; simulation adds nothing here
            self.reason = "step:hop" if wall <= 1 else "step:walk"
            return "right_jump_short" if wall <= 1 else "right"
        if hazard is not None:
            kind, hx = hazard
            at_edge = (pit is not None and pit <= 1) or (wall is not None and wall <= 1)
            plan = self._plan(world, m, enemies, hx, profile(m.vx))
            if plan is not None:
                prof, hold, land = plan
                if self.streak < SETTLE_FRAMES and not at_edge:
                    self.reason = f"{kind}:settle@{prof}"
                    return APPROACH[prof]  # just landed: let the speed settle, then re-plan
                self.reason = f"{kind}:{hold}@{prof}->+{land - m.x}"
                return JUMP[(prof, hold)]
            if at_edge:
                self.reason = f"{kind}:best-effort"
                self.plan_frames = 0
                return "run_right_jump_long" if profile(m.vx) == "run" else "right_jump_long"
            prof, takeoff = self._approach_profile(world, m, enemies, hx)
            if prof == "stand":
                # walk to the takeoff spot, then stop there; the standing hop follows
                self.reason = f"{kind}:approach@stand@{takeoff}"
                return "right" if m.x < takeoff - 6 else "noop"
            self.reason = f"{kind}:approach@{prof}"
            return APPROACH[prof]
        # 3. enemies further ahead: wait for the ones coming, follow the ones leaving
        if ahead:
            nearest = min(ahead, key=lambda e: e.dx)
            if self.enemy_vx.get(id(nearest), -DEFAULT_ENEMY_VX) > 0.2:
                self.reason = f"follow:{nearest.kind}"
                return "right"
            self.reason = f"wait:{nearest.kind}"
            return "noop"
        if behind and any(self.enemy_vx.get(id(e), DEFAULT_ENEMY_VX) > 0 for e in behind):
            self.reason = "behind:hop"
            self.plan_frames = 0
            return "jump_short"
        self.reason = "run"
        return "run_right"

    # -------------------------------------------------------------- enemies
    def _engage(self, obs: Observation, enemies: list[Enemy], hazard) -> str:
        """Enemy within ENGAGE_PX: the shortest jump that is safe (over it or onto it)."""
        m, world = obs.mario, obs.world
        prof = profile(m.vx)
        options = [(prof, "short"), (prof, "long")]
        if prof == "stand":
            options.append(("stand", "up"))
        best = None
        for p, hold in options:
            arc = ARCS[(p, hold)] if hold == "up" else arc_for(m.vx, hold)
            result = self._simulate(world, m, enemies, arc)
            if result is None:
                continue
            land, outcome = result
            if outcome == "land":
                continue  # neither over nor onto: a hop that ends among the enemies
            if hazard is not None and hazard[0] == "pit" and land > hazard[1] - TILE:
                continue  # would land in or right at the pit; terrain planning handles that
            key = (0 if outcome == "over" else 1, land)  # clearing beats landing on it
            if best is None or key < best[0]:
                best = (key, p, hold, land, outcome)
        if best is not None:
            _, p, hold, land, outcome = best
            self.reason = f"{outcome}:{hold}@{p}->+{land - m.x}"
            self.plan_frames = len(ARCS[(p, hold)])
            return JUMP[(p, hold)]
        self.plan_frames = 0
        closest = min(enemies, key=lambda e: abs(e.dx), default=None)
        if closest is not None and abs(closest.dx) <= STOMP_PX.get(closest.kind, STOMP_DEFAULT_PX):
            self.reason = f"stomp-blind:{closest.kind}"
            self.plan_frames = 0
            return "jump_short"
        nearest = min((e for e in enemies if e.dx >= 0), key=lambda e: e.dx, default=None)
        if nearest is not None and self.enemy_vx.get(id(nearest), -DEFAULT_ENEMY_VX) > 0.2:
            self.reason = f"follow:{nearest.kind}"
            return "right"  # walking away: close in slowly, a walking jump clears it in time
        self.reason = "hold:enemy"
        return "noop"

    def _track(self, enemies: list[Enemy]) -> None:
        """Per-enemy velocity averaged over a window, matched by kind and nearest x."""
        vx: dict[int, float] = {}
        tracks: list[tuple[str, list[int]]] = []
        for e in enemies:
            match = min(
                (t for t in self.tracks if t[0] == e.kind and abs(t[1][-1] - e.x) <= 4),
                key=lambda t: abs(t[1][-1] - e.x),
                default=None,
            )
            xs = (match[1] if match else [])[-VELOCITY_WINDOW:] + [e.x]
            tracks.append((e.kind, xs))
            if len(xs) >= 3:
                vx[id(e)] = (xs[-1] - xs[0]) / (len(xs) - 1)
        self.enemy_vx = vx
        self.tracks = tracks

    @staticmethod
    def _relevant(enemies: list[Enemy], body_row: int) -> list[Enemy]:
        return [
            e
            for e in enemies
            if e.hostile and e.kind not in IGNORED and abs(e.row - body_row) <= ENEMY_ROWS
        ]

    # ------------------------------------------------------------- planning
    def _plan(self, world: WorldMap, m, enemies: list[Enemy], hazard_x: int, prof: str):
        """Best jump from here at this speed: safe, lands past the hazard, shortest."""
        best = None
        for hold in ("short", "long"):
            vx = getattr(m, "vx_override", None)
            arc = arc_for(m.vx, hold) if vx is None else ARCS[(prof, hold)]
            result = self._simulate(world, m, enemies, arc)
            if result is None or result[0] < hazard_x - FOOT_IN - 8:
                continue  # must come down on or past the hazard column (a foot point counts)
            if best is None or result[0] < best[2]:
                best = (prof, hold, result[0])
        if best is not None:
            self.plan_frames = len(ARCS[(best[0], best[1])])
        return best

    def _approach_profile(self, world: WorldMap, m, enemies: list[Enemy], hazard_x: int):
        """(speed, takeoff x) of the shortest safe jump available from somewhere before the hazard."""
        best = None
        for prof in ("stand", "walk", "run"):
            for takeoff in range(m.x, hazard_x - TILE // 2, TILE // 2):
                ghost = _Ghost(takeoff, m.y_screen, m.row)
                plan = self._plan(world, ghost, enemies, hazard_x, prof)
                if plan is not None:
                    if best is None or plan[2] - takeoff < best[0]:
                        best = (plan[2] - takeoff, prof, takeoff)
                    break  # the earliest takeoff at this speed is the safest
        return (best[1], best[2]) if best else ("run", hazard_x)

    def _simulate(self, world: WorldMap, m, enemies: list[Enemy], arc: list[tuple[int, int]]):
        """Fly the arc. None if the body hits a tile or an enemy; else (landing x, outcome)."""
        x0, feet0 = m.x, m.y_screen + 32  # screen y of the sole; tile rows start at screen y 32
        prev_up = 0
        for f, (dx, up) in enumerate(arc):
            x, feet = x0 + dx, feet0 - up
            descending = up < prev_up
            for e in enemies:
                if f < CONTACT_FRAMES:
                    continue  # already touching or not: nothing a jump decides this early
                ex = (
                    e.x
                    + self.enemy_vx.get(id(e), -DEFAULT_ENEMY_VX if e.dx > 0 else DEFAULT_ENEMY_VX)
                    * f
                )
                etop = 32 + 16 * e.row - (8 if e.kind in TALL else 0)
                if x + 3 < ex + 13 and ex + 3 < x + 13 and feet > etop and feet - 16 < etop + 16:
                    if descending and feet <= etop + 8:
                        return x, "stomp"
                    return None
            cols = range((x + 3) // TILE, (x + 12) // TILE + 1)  # the game's hitbox, not the sprite
            if any(not world.known(c) for c in cols):
                return None
            support_row = (feet - 32) // TILE
            if support_row >= MAP_ROWS:
                return None  # fell out of the map: a pit
            for c in cols:
                for r in range(max(0, (feet - 48) // TILE), min(MAP_ROWS, (feet - 33) // TILE + 1)):
                    if world.solid(c, r):
                        return None  # wall or ceiling
            if descending and self._lands(world, x, support_row):
                return x, self._outcome(x, enemies)
            prev_up = up
        x, feet = x0 + arc[-1][0], feet0 - arc[-1][1]
        support_row = (feet - 32) // TILE
        return (x, self._outcome(x, enemies)) if self._lands(world, x, support_row) else None

    @staticmethod
    def _outcome(land_x: int, enemies: list[Enemy]) -> str:
        """'over' when every enemy that was ahead is now behind the landing spot."""
        return "over" if all(e.dx < 0 or e.x + TILE < land_x for e in enemies) else "land"

    @staticmethod
    def _lands(world: WorldMap, x: int, support_row: int) -> bool:
        """Either foot point on solid ground, as the game checks it; a 3 px overlap is none."""
        if not 0 <= support_row < MAP_ROWS:
            return False
        return world.solid((x + FOOT_IN) // TILE, support_row) or world.solid(
            (x + TILE - 1 - FOOT_IN) // TILE, support_row
        )

    # -------------------------------------------------------------- terrain
    @staticmethod
    def _supported(world: WorldMap, col: int, body_row: int) -> bool:
        return any(world.solid(col, r) for r in range(body_row + 1, MAP_ROWS))

    def _pit_distance(self, world: WorldMap, col: int, body_row: int) -> int | None:
        for c in range(col + 1, col + LOOKAHEAD + 1):
            if not world.known(c):
                return None
            if not self._supported(world, c, body_row):
                return c - col
        return None

    @staticmethod
    def _wall_distance(world: WorldMap, col: int, body_row: int) -> tuple[int | None, int]:
        """Distance to the first solid tile at body height ahead, and how tall that wall is."""
        for c in range(col + 1, col + WALL_LOOKAHEAD + 1):
            if world.solid(c, body_row) or world.solid(c, body_row - 1):
                top = body_row
                while top > 0 and world.solid(c, top - 1):
                    top -= 1
                return c - col, body_row + 1 - top
        return None, 0


class _Ghost:
    """A hypothetical Mario position (at a measured profile speed) for approach planning."""

    vx_override = True

    def __init__(self, x: int, y_screen: int, row: int) -> None:
        self.x, self.y_screen, self.row, self.vx = x, y_screen, row, 0


PLAYER = ClaudePlayer
