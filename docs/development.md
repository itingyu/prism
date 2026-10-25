# 开发

## 环境

```bash
git clone git@github.com:itingyu/prism.git && cd prism
python -m venv .venv && . .venv/bin/activate
pip install -e .                 # 可编辑安装：改源码立即生效
pip install pytest
prism --version
```

可选依赖按需装，命令自己会提示缺哪个：

```bash
pip install -e '.[events]'       # akshare，扩展数据集 / 宏观
pip install -e '.[finance]'      # baostock，杜邦拆解等
pip install -e '.[spare]'        # adata，第三备用源
```

## 测试

```bash
pytest -q                        # 全量，约 20 秒
pytest tests/test_help_text.py   # 只跑帮助形态
```

测试守的是**纪律**而不是数字：

- 没有悬空命令（文档 / 提示里出现的命令必须真的注册过）
- `--kind` 必有 `--list`；同一 flag 不得对应两个参数名
- 动作返回的字段必须能被渲染层取到
- `docs/commands.md` 与注册表一致（漂了就重新生成）

## 加一个命令

1. 在 `stock/command/_actions*.py` 写动作：`_act_xxx(args, cfg) -> dict`，
   返回 `{'title': ..., 'rows': [...]}` 这种形状，不要自己 print。
2. 在 `_registry.py` 的 `ACTIONS` 里登记动作名。
3. 在 `cli/stock.py` 用 `@cmd('xxx')` 写入口，转发给 `_dispatch`。
4. 需要口径就传 `kind` + `list_kinds`，走 `_fam_route`；口径表在
   `bridge/ak_families.py`，由上游接口清单生成，别手改。
5. 跑 `python tools/gen_docs.py` 更新 `docs/commands.md`。
6. `pytest -q`。

动作层只负责"把参数变成一次取数"，字段口径交给 `_textfmt*.py`，
格式化交给 `_render.py`。

## 改选项的规矩

- 短标志全仓唯一：`-n` 恒为条数，`-f` 恒为格式，`-o` 恒为输出文件。
- 不用"空选项"：声明了就必须有命令提供它，否则删掉。
- 同一个 flag 不映射两个参数名。
- 旧名不留兼容层，直接替换；错误提示给近似名。

这些都是测试挡着的，不用靠记性。

## 发布

`prism/__init__.py` 的 `__version__` 从 `core/version.py` 派生，只有一处版本号。
改 `pyproject.toml` 的 `version`，然后：

```bash
python -m build && twine upload dist/*
```

## 目录约定

| 位置 | 放什么 |
|---|---|
| `docs/` | 用户文档；`docs/commands.md` 由脚本生成，不手改 |
| `tools/` | 生成器与一次性脚本：`gen_docs.py`（命令文档）、`gen_ak_via.py` / `gen_ak_extra.py`（akshare 包装与补充口径） |
| `src/prism/stock/data/reverse/` | 东财接口配方 `em_recipes.json` / `em_maps.json`，**是数据不是文档** |
| `tests/` | 纪律性测试 |
| `skills/prism/` | agent 用的命令地图 `SKILL.md`；改命令后同步，装机见下 |

## SKILL.md

`skills/prism/SKILL.md` 是给 AI agent 的任务→命令地图，和 `docs/` 各有读者：
文档给人读，SKILL 给 agent 读（怎么写 prompt、哪个命令是唯一口径、哪些坑会静默返空）。

规则：
- 只引用真实存在的命令与选项，`tests/test_docs_numbers.py` 会扫它
- 命令增删或选项改名后一起改，否则测试红
- 安装：`cp skills/prism/SKILL.md /var/minis/skills/prism/SKILL.md`

`data/reverse/` 下的 json 被 `bridge/em.py` 在运行时读取（东财 reportName 与列序映射），
删了 `--source em_*` 与部分 `--kind` 口径会取不到数。不要当成文档删改。
