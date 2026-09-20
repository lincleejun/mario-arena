"""Decode Super Mario Bros. RAM into a structured observation and an accumulating level map.

No pixels are read anywhere. Addresses follow the community RAM map for SMB (NES).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TILE = 16
MAP_ROWS = 13  # the tile buffer at 0x0500 holds 13 rows x 16 columns per page, two pages
ENEMY_SLOTS = 5
ENEMY_KINDS = {
    0x00: "koopa",
    0x01: "koopa_red",
    0x02: "buzzy_beetle",
    0x03: "koopa_red",
    0x04: "koopa",
    0x05: "hammer_bro",
    0x06: "goomba",
    0x07: "blooper",
    0x08: "bullet_bill",
    0x09: "paratroopa",
    0x0A: "cheep_cheep",
    0x0B: "cheep_cheep_red",
    0x0C: "podoboo",
    0x0D: "piranha_plant",
    0x0E: "paratroopa",
    0x0F: "paratroopa_red",
    0x10: "paratroopa",
    0x11: "lakitu",
    0x12: "spiny",
    0x14: "cheep_cheep",
    0x15: "bowser_flame",
    0x2D: "bowser",
    0x2E: "power_up",
    0x2F: "vine",
    0x30: "flagpole",
    0x31: "flagpole",
    0x32: "star_flag",
    0x33: "spring",
}
HARMLESS = frozenset({"power_up", "vine", "flagpole", "star_flag", "spring"})


@dataclass(frozen=True)
class Enemy:
    kind: str
    x: int  # world px
    row: int  # tile row, 0 = top of the play field
    dx: int  # px relative to Mario, positive = ahead
    hostile: bool


@dataclass
class Mario:
    x: int
    y_screen: int
    col: int
    row: int
    vx: int  # subpixel units from RAM: ~28 walking, ~48 running
    vy: int  # signed; negative = rising
    grounded: bool
    size: str  # small | big | fire
    lives: int


class WorldMap:
    """Tiles accumulated by world column. Written only from the camera's trusted window."""

    def __init__(self) -> None:
        self.cols: dict[int, list[int]] = {}

    def update(self, ram: Any, camera_x: int) -> None:
        for x in range(camera_x, camera_x + 256 + TILE, TILE):
            page = (x // 256) % 2
            base = 0x0500 + page * MAP_ROWS * 16 + (x % 256) // TILE
            self.cols[x // TILE] = [int(ram[base + row * 16]) for row in range(MAP_ROWS)]

    def solid(self, col: int, row: int) -> bool:
        column = self.cols.get(col)
        return bool(column and 0 <= row < MAP_ROWS and column[row] != 0)

    def known(self, col: int) -> bool:
        return col in self.cols

    def rows(self, col_from: int, col_to: int) -> list[str]:
        """Ascii rows for [col_from, col_to): '#' solid, '.' empty, '?' never seen."""
        out = []
        for row in range(MAP_ROWS):
            line = []
            for col in range(col_from, col_to):
                column = self.cols.get(col)
                line.append("?" if column is None else ("#" if column[row] else "."))
            out.append("".join(line))
        return out

    @property
    def max_col(self) -> int:
        return max(self.cols) if self.cols else -1


@dataclass
class Observation:
    level: str
    frame: int
    time_left: int
    camera_x: int
    mario: Mario
    enemies: list[Enemy]
    world: WorldMap
    flag: bool = False
    dead: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def view(self, back: int = 4, ahead: int = 16) -> list[str]:
        """Ascii window around Mario with M and E marks, for humans and text models."""
        col_from, col_to = self.mario.col - back, self.mario.col + ahead
        rows = [list(r) for r in self.world.rows(col_from, col_to)]

        def mark(col: int, row: int, ch: str) -> None:
            if 0 <= row < MAP_ROWS and col_from <= col < col_to:
                rows[row][col - col_from] = ch

        for enemy in self.enemies:
            mark(enemy.x // TILE, enemy.row, "E" if enemy.hostile else "i")
        mark(self.mario.col, self.mario.row, "M")
        return ["".join(r) for r in rows]

    def to_dict(self, back: int = 4, ahead: int = 16) -> dict[str, Any]:
        return {
            "level": self.level,
            "frame": self.frame,
            "time_left": self.time_left,
            "mario": vars(self.mario),
            "enemies": [vars(e) for e in self.enemies],
            "map": {"col_from": self.mario.col - back, "rows": self.view(back, ahead)},
            "flag": self.flag,
            "dead": self.dead,
        }


def decode(ram: Any, info: dict[str, Any], world: WorldMap, level: str, frame: int) -> Observation:
    camera_x = int(ram[0x071A]) * 256 + int(ram[0x071C])
    world.update(ram, camera_x)
    x = int(ram[0x006D]) * 256 + int(ram[0x0086])
    y_screen = int(ram[0x00CE])
    vx, vy = int(ram[0x0057]), int(ram[0x009F])
    mario = Mario(
        x=x,
        y_screen=y_screen,
        col=x // TILE,
        row=(y_screen - TILE) // TILE,
        vx=vx - 256 if vx > 127 else vx,
        vy=vy - 256 if vy > 127 else vy,
        grounded=int(ram[0x001D]) == 0,
        size=("small", "big", "fire")[min(int(ram[0x0756]), 2)],
        lives=int(ram[0x075A]),
    )
    enemies = []
    for slot in range(ENEMY_SLOTS):
        if int(ram[0x000F + slot]) == 0:
            continue
        kind = ENEMY_KINDS.get(int(ram[0x0016 + slot]), f"enemy_{int(ram[0x0016 + slot]):02x}")
        ex = int(ram[0x006E + slot]) * 256 + int(ram[0x0087 + slot])
        ey = int(ram[0x00CF + slot])
        enemies.append(
            Enemy(kind=kind, x=ex, row=(ey - TILE) // TILE, dx=ex - x, hostile=kind not in HARMLESS)
        )
    return Observation(
        level=level,
        frame=frame,
        time_left=int(info.get("time", 0)),
        camera_x=camera_x,
        mario=mario,
        enemies=enemies,
        world=world,
        flag=bool(info.get("flag_get")),
    )
