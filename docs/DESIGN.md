# mario-arena 设计

一句话：`world = env.step(world, instruction)`。环境从模拟器内存投影出 World，玩家只看 World、只回 instruction。
harness 在外面管节奏、重试、关卡推进和记录。玩家可以是进程内的 Python 类，也可以是任何语言的外部进程。

## 1. 核心对象

### World，每帧一份，不可变，schema 有版本号

```
World
  schema        "1"
  run_id        本局 id
  level         {id "1-1", kind overworld|underground|water|castle, attempt 1}
  frame         本关第几帧
  time_left     关卡计时
  status        playing | level_clear | level_failed | game_over
  mario         {x y vx vy grounded size invincible_frames lives on_feature}
  entities[]    {kind x y vx vy state hostile stompable}     敌人、物品、火球、平台
  features[]    {kind x0 x1 height note}                      坑 墙 台阶 管道 平台 岩浆 旗杆，从 grid 推导
  ahead[]       {kind distance_px width height entity}        从 Mario 往前按距离排序，决策直接用
  grid          {col: [13 个 TileKind]}                        真相层，随探索累积，未见列标 unknown
  view()        ascii 网格
  to_dict()     JSON
```

三个原则：grid 只放 RAM 事实不推断；features 和 ahead 从 grid 和 entities 派生，所有玩家共享，不用各自扫网格；
World 里不放历史，需要记忆的玩家自己存，保证“只看当前 World 就能判断”。

### Instruction

```
{"macro": "run_right_jump_long", "frames": 8}
```

`macro` 取自动作词表（noop right left run_right run_left down up jump_short jump_long
right_jump_short right_jump_long run_right_jump_long left_jump_short left_jump_long）。
`frames` 是这条指令至少执行多少帧再问下一次，回合制里有意义，实时模式忽略。
跳跃由环境按帧承诺：短跳按 A 6 帧，长跳按到落地，落地前后续指令只能转向。玩家不碰按键沿。

### MarioEnv

```python
class MarioEnv:
    def reset(self, level: str) -> World
    def step(self, instruction: Instruction) -> World
    def snapshot(self) -> bytes           # nes-py 存档，给搜索类玩家试探未来
    def restore(self, snap: bytes) -> World
```

## 2. Run：一局就是一个目录

开始一局就建一个 run，所有中间文件只落在这个目录里，跑完目录就是完整证据，可对比可回放。

```
runs/20260919-152301-reflex/
  run.json            harness 配置 + 玩家信息 + 最终结果（schema、fps、turn_based、frames_per_step、retries、动作词表 hash、seed、版本）
  summary.json        每关一行：cleared attempts best_x time_left decisions deaths wall_s
  levels/1-1/
    attempt-1/
      trace.jsonl     每次决策一行：frame、world 摘要（mario、ahead、entities）、instruction、玩家耗时
      result.json     本次尝试结果和死因
      video.mp4       可选，--record 时生成
      worlds/         可选，完整 World 逐帧 dump，调试用，默认关
    attempt-2/ ...
  levels/1-2/ ...
```

- run_id = 时间戳 + 玩家名，人能读，排序即时间序。
- trace 用 JSONL 追加写，进程中途挂掉也能保留到最后一步。
- `arena replay runs/<id>` 用 trace 里的 instruction 重放，不需要玩家在场就能重新出视频。模拟器确定性保证一致。
- `arena compare runs/a runs/b` 先校验 run.json 里 harness 字段一致，再并排。harness 不同的结果不比。

## 3. 外部玩家协议：harness 作为服务，玩家来拉

外部只做两件事：开一局；循环拿 World、回 instruction，直到被告知结束。

```
POST /runs
  {"player": "my-agent", "levels": ["1-1","1-2"] | "all",
   "fps": 60 | 0, "turn_based": false, "retries": 3, "record": true}
  -> {"run_id": "...", "world": {...}}

POST /runs/{id}/act
  {"macro": "run_right", "frames": 8}
  -> {"world": {...}, "events": ["stomped goomba", "entered 1-2"]}

GET  /runs/{id}/world      实时模式下随时拉最新一帧
GET  /runs/{id}            summary
DELETE /runs/{id}          中止
```

结束的判断全在返回的 `world.status` 里：

| status | 含义 | 玩家该做什么 |
|---|---|---|
| playing | 进行中 | 继续 act |
| level_clear | 本关通关，环境已自动进入下一关，world 里 level 已变 | 继续 act，需要的话重置自己的记忆 |
| level_failed | 死一次，环境已从本关重开，attempt 加一 | 继续 act |
| game_over | 全部通关，或某关用完重试次数，summary 里有原因 | 停止 |

两种节奏：
- 实时（默认）：环境按 60fps 走，不等玩家。玩家慢就少看几帧，上一条指令持续生效。
- 回合制（`turn_based: true`）：环境执行完一条指令的 `frames` 帧就停下等玩家。慢模型用这个，结果可复现。

同一个玩家在两种节奏下各跑一次，差值就是延迟的代价，这是 VideoGameBench 分 Lite 模式的做法。

进程内 Python 玩家走同一条路，只是不经过 HTTP：`act(world) -> instruction`。

## 4. 玩家分三类，都对着同一个 World

- 规则玩家：读 `world.ahead`，代码决定。今天的 reflex 是第一个。
- 搜索玩家：用 snapshot/restore 对每个候选指令试跑 1 秒未来，选活下来且走最远的。预计是 32 关的天花板基线。
- 模型玩家：Jev 收 `to_dict()`，LLM 收 `to_text()` 或 `view()`，回一个 macro 名。可以和搜索玩家组合：搜索给候选，模型选。

## 5. 分阶段

1. World 和 MarioEnv 落地，reflex 改成只读 `world.ahead`，1-1 仍通关。补敌人状态和图块种类。
2. Run 目录、trace、replay、compare 校验。
3. HTTP 服务和回合制。
4. 搜索玩家。
5. Jev 和 LLM 玩家接入，出第一张对比表。

## 6. 明确不做

- 不读像素。
- World 里不放历史和奖励，奖励是 harness 的统计，不是环境的输出。
- 不做通用游戏框架，先把 SMB 一款做扎实，接口不带第二款游戏的抽象。
