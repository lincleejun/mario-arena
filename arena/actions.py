"""The player's vocabulary: macro actions the harness turns into frame-precise button presses.

A jump macro commits the A button: short = 6 frames (a hop of ~2 tiles), long = held until
Mario lands (max height/distance). Until landing, any later macro only steers (direction and
run buttons); it cannot cancel the jump or start another one. The harness inserts the release
frame a new A press needs, so players never think about button edges.
"""

from __future__ import annotations

from dataclasses import dataclass

SHORT_HOLD = 6
LONG_HOLD = 32  # SMB stops adding height after ~32 frames; landing usually ends it first


@dataclass(frozen=True)
class Macro:
    name: str
    buttons: frozenset[str]  # direction/run buttons held every frame: right, left, down, up, B
    jump: bool = False
    hold: int = 0  # frames A is held after the press

    @property
    def description(self) -> str:
        return DESCRIPTIONS[self.name]


DESCRIPTIONS = {
    "noop": "Release everything; Mario decelerates.",
    "right": "Walk right.",
    "left": "Walk left.",
    "run_right": "Run right (B held): faster, longer jumps.",
    "run_left": "Run left (B held).",
    "down": "Crouch (big Mario) or enter a pipe below.",
    "up": "Climb a vine or enter a pipe above.",
    "jump_short": "Small vertical hop, ~2 tiles high, stays in place.",
    "jump_long": "Full vertical jump, ~4 tiles high, stays in place.",
    "right_jump_short": "Short hop moving right: clears a 1-tile step, lands ~1.5 tiles ahead.",
    "right_jump_long": "Full walking jump right: clears a 2-tile pit, lands ~4 tiles ahead.",
    "run_right_jump_long": "Full running jump right: clears a 3-4 tile pit, lands ~6 tiles ahead.",
    "left_jump_short": "Short hop moving left.",
    "left_jump_long": "Full walking jump left.",
}

MACROS: dict[str, Macro] = {
    "noop": Macro("noop", frozenset()),
    "right": Macro("right", frozenset({"right"})),
    "left": Macro("left", frozenset({"left"})),
    "run_right": Macro("run_right", frozenset({"right", "B"})),
    "run_left": Macro("run_left", frozenset({"left", "B"})),
    "down": Macro("down", frozenset({"down"})),
    "up": Macro("up", frozenset({"up"})),
    "jump_short": Macro("jump_short", frozenset(), jump=True, hold=SHORT_HOLD),
    "jump_long": Macro("jump_long", frozenset(), jump=True, hold=LONG_HOLD),
    "right_jump_short": Macro("right_jump_short", frozenset({"right"}), jump=True, hold=SHORT_HOLD),
    "right_jump_long": Macro("right_jump_long", frozenset({"right"}), jump=True, hold=LONG_HOLD),
    "run_right_jump_long": Macro(
        "run_right_jump_long", frozenset({"right", "B"}), jump=True, hold=LONG_HOLD
    ),
    "left_jump_short": Macro("left_jump_short", frozenset({"left"}), jump=True, hold=SHORT_HOLD),
    "left_jump_long": Macro("left_jump_long", frozenset({"left"}), jump=True, hold=LONG_HOLD),
}

# nes-py JoypadSpace takes a list of button-name lists; the index is the env action.
BUTTON_COMBOS: list[list[str]] = sorted(
    {
        tuple(sorted(m.buttons | ({"A"} if a else set())))
        for m in MACROS.values()
        for a in (False, True)
    }
)
BUTTON_COMBOS = [list(c) or ["NOOP"] for c in BUTTON_COMBOS]
COMBO_INDEX = {frozenset(c if c != ["NOOP"] else []): i for i, c in enumerate(BUTTON_COMBOS)}


class Executor:
    """Per-frame button state for the current macro, with jump commitment and release edges."""

    def __init__(self) -> None:
        self.macro = MACROS["noop"]
        self.a_left = 0  # frames of A still to press for the committed jump
        self.airborne_seen = False
        self.last_a = False

    def set(self, macro: Macro, grounded: bool) -> None:
        if self.a_left > 0 or not grounded:
            # a committed jump keeps its A until landing; any macro only steers mid-air
            self.macro = Macro(self.macro.name, macro.buttons, self.macro.jump, self.macro.hold)
            return
        self.macro = macro
        if macro.jump:
            self.a_left = macro.hold
            self.airborne_seen = False

    def buttons(self, grounded: bool) -> frozenset[str]:
        press = False
        if self.a_left > 0:
            self.airborne_seen = self.airborne_seen or not grounded
            if self.airborne_seen and grounded:
                self.a_left = 0  # landed: the jump is over
            elif self.last_a and self.a_left == self.macro.hold:
                press = False  # release edge: a fresh press needs one frame without A
            else:
                press = True
                self.a_left -= 1
        self.last_a = press
        return self.macro.buttons | ({"A"} if press else frozenset())

    def action_index(self, grounded: bool) -> int:
        return COMBO_INDEX[self.buttons(grounded)]
