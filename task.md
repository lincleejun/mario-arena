# 任务书：为 mario-arena 写一个玩家

你在一个隔离的 worktree 里。目标：在 `players/<你的名字>.py` 里实现一个玩家，让 Mario 从 RAM 状态出发通过尽可能多的关卡。没有像素，没有截图，只有结构化状态。

## 规则

- 只允许新增或修改 `players/<你的名字>.py` 这一个文件。`arena/` 目录、动作词表、harness 参数一律不许改，改了成绩作废。
- 允许读仓库里任何代码和文档，允许跑任何 `arena` 命令和 `scripts/tune.py`。
- 时间上限 2 小时。到时提交当前版本。
- 不许调用外部 API 或联网查攻略。玩家必须是自包含的 Python，只依赖标准库和仓库已装的包。
- 文件顶部写清楚思路，`info` 字段填作者和方法。

## 怎么跑

```bash
uv run arena actions                                              # 动作词表
uv run play --player players/<name>.py --levels 1-1 --fps 0  # 全速跑一关
uv run play --player players/<name>.py --levels all --fps 0 --retries 3
uv run play --player players/<name>.py --levels 1-3 --fps 0 -v   # 每次决策打印一行
ARENA_TRACE=1500 uv run play ...                            # 从第 1500 帧起逐帧打印
uv run arena replay runs/<id> --record                            # 回放并出视频
```

每局输出在 `runs/<id>/`：`run.json` 是结果，`levels/<关>/attempt-N/trace.jsonl` 是每次决策。

## 玩家合约

从 `players/TEMPLATE.py` 复制。`act(obs)` 每次收到 `arena.ram.Observation`，返回一个 macro 名，或 `(macro, frames)`，或 `None`。`obs` 里有：

- `obs.mario`：x、col、row、vx、vy、grounded、size、lives
- `obs.enemies`：kind、x、row、dx（相对 Mario 的像素，正为前方）、hostile
- `obs.world`：累积地图，`solid(col, row)`、`known(col)`、`rows(col_from, col_to)`
- `obs.view()` 文字网格，`obs.to_dict()` JSON

跳跃由 harness 承诺：短跳按 A 6 帧，长跳按到落地，空中只能转向。你不用管按键沿。

## 评分

正式评测用固定命令，所有玩家一致：

```bash
uv run play --player players/<name>.py --levels all --turn-based --retries 3
```

回合制是为了可复现：实时模式下玩家线程和模拟器有竞态，同一玩家两次结果可能不同；回合制下模拟器等玩家，结果逐帧确定。开发时也建议用 `--turn-based`。

排序依据依次是：通关数、未通关的那一关走到的最远 x、总决策数（少者优）。附带记录你的开发用时。

## 已知情况

`players/reflex.py` 的规则玩家能过 1-1，1-2 走到 1241，1-3 死在第一个大坑，1-4 死在第一个岩浆坑。可以参考它，也可以完全另起炉灶。`scripts/tune.py` 能对一个模块常量做参数扫描，一局约 1 秒。

## 提交

把 `players/<name>.py` 放在仓库里，附一段不超过 200 字的说明：方法、过了哪些关、卡在哪、如果再有 2 小时会做什么。
