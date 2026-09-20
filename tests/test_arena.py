from arena.actions import MACROS, Executor
from arena.players.reflex import BEHIND_MACRO, ENEMY_JUMP_MACRO, ReflexPlayer
from arena.ram import MAP_ROWS, Enemy, Mario, Observation, WorldMap


def world(cols: dict[int, str], default: str = ".........#") -> WorldMap:
    """cols: col -> 13-char column string top to bottom ('#' solid). Others get `default`."""
    w = WorldMap()
    for c in range(-2, 30):
        text = cols.get(c, default).ljust(MAP_ROWS, ".")
        w.cols[c] = [1 if ch == "#" else 0 for ch in text]
    return w


GROUND = "." * 10 + "###"  # rows 10..12 solid; Mario stands on row 9


def obs(w: WorldMap, col=2, grounded=True, vx=28, enemies=()):
    mario = Mario(col * 16, 176, col, 9, vx, 0, grounded, "small", 2)
    return Observation("1-1", 0, 300, 0, mario, list(enemies), w)


def goomba(col, dx, kind="goomba"):
    return Enemy(kind, col * 16, 9, dx, True)


def test_executor_release_edge_and_short_hold():
    ex = Executor()
    ex.set(MACROS["right_jump_short"], grounded=True)
    presses = [("A" in ex.buttons(grounded=True)) for i in range(7)]
    assert presses == [True] * 6 + [False]  # 6 frames of A, then released
    ex.set(MACROS["right_jump_short"], grounded=True)
    ex.buttons(grounded=True)  # A down again
    ex.a_left = 0
    ex.set(MACROS["right_jump_long"], grounded=True)  # new press right after A: needs an edge
    assert "A" not in ex.buttons(grounded=True)
    assert "A" in ex.buttons(grounded=True)


def test_executor_long_jump_ends_on_landing_and_ignores_double_jump():
    ex = Executor()
    ex.set(MACROS["right_jump_long"], grounded=True)
    assert "A" in ex.buttons(True)
    for _ in range(5):
        assert "A" in ex.buttons(False)
    ex.set(MACROS["jump_long"], grounded=False)  # ignored: only direction changes
    assert ex.macro.buttons == frozenset()
    assert "A" not in ex.buttons(True)  # landed


def test_reflex_pit_walkup_then_walking_jump():
    w = world({c: "." * 13 for c in (6, 7)}, default=GROUND)  # 2-wide pit at cols 6-7
    p = ReflexPlayer()
    assert p.act(obs(w, col=2)) == "right" and p.reason == "walk-up"
    assert p.act(obs(w, col=5)) == "right_jump_long" and p.reason == "gap"
    assert p.act(obs(w, col=6, grounded=False)) is None  # over the pit: keep flying
    assert p.act(obs(w, col=8, grounded=False)) == "left" and p.reason == "air-brake"


def test_reflex_wide_pit_runs_and_wall_before_pit_hops():
    w = world({c: "." * 13 for c in (6, 7, 8)}, default=GROUND)
    assert ReflexPlayer().act(obs(w, col=5)) == "run_right_jump_long"
    step = "." * 9 + "####"  # one tile higher than ground
    w = world({3: step, 6: "." * 13, 7: "." * 13}, default=GROUND)
    p = ReflexPlayer()
    assert p.act(obs(w, col=2)) == "right_jump_short" and p.reason == "obstacle"


def test_reflex_enemy_wait_jump_over_and_behind():
    w = world({}, default=GROUND)
    p = ReflexPlayer()
    assert p.act(obs(w, enemies=[goomba(8, 100)])) == "noop" and p.reason == "wait:goomba"
    assert p.act(obs(w, enemies=[goomba(3, 30)])) == ENEMY_JUMP_MACRO and p.reason == "over:goomba"
    assert ReflexPlayer().act(obs(w, enemies=[goomba(0, -30)])) == BEHIND_MACRO
    assert ReflexPlayer().act(obs(w, enemies=[goomba(3, 20, "koopa")])) == ENEMY_JUMP_MACRO


def test_reflex_tall_pipe_and_stall_retreat_only_over_ground():
    pipe = "." * 6 + "#" * 7  # 4 tiles above ground rows
    w = world({5: pipe, 6: pipe}, default=GROUND)
    assert ReflexPlayer().act(obs(w, col=2)) == "run_right_jump_long"  # 3 tiles away, height 4
    p = ReflexPlayer()
    assert p.act(obs(w, col=4, vx=0)) == "left" and p.reason == "retreat"
    w2 = world({5: pipe, 6: pipe, 2: "." * 13, 3: "." * 13}, default=GROUND)
    assert ReflexPlayer().act(obs(w2, col=4, vx=0)) == "run_right_jump_long"


def test_observation_view_marks():
    w = world({}, default=GROUND)
    rows = obs(w, enemies=[goomba(5, 48)]).view(back=2, ahead=6)
    assert rows[9] == "..M..E.."
    assert rows[10] == "########"


def test_script_player_sends_each_entry_once(tmp_path):
    import json

    from arena.players.script import ScriptPlayer

    path = tmp_path / "steps.json"
    path.write_text(
        json.dumps([{"macro": "run_right", "frames": 10}, {"macro": "jump_long", "frames": 1}])
    )
    p = ScriptPlayer(str(path))
    w = world({}, default=GROUND)
    frames = [p.act(Observation("1-1", f, 300, 0, obs(w).mario, [], w)) for f in range(14)]
    assert frames[0] == ("run_right", 10)
    assert frames[10] == ("jump_long", 1)
    assert all(f is None for i, f in enumerate(frames) if i not in (0, 10))
