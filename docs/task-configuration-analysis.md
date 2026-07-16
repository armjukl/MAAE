# 任务配置执行分析

## 配置文件的角色

`tasks/*.json` 不直接控制浏览器或 ADB。它们只描述应交给 MaaCore 的任务链。`main.py` 读取配置后，逐项调用 `Asst.append_task(task.task_type, task.params)`；真正的游戏识别、页面操作和任务完成判断由 MaaCore 资源与任务引擎负责。

```text
tasks/*.json
    -> TaskConfig.from_file()
    -> TaskConfig.tasks: list[Task]
    -> AsstAppendTask(type, params_json)
    -> AsstStart()
    -> MaaCore 内部任务链
```

## 文件选择规则

`main.py` 的 `find_task_file()` 按以下顺序定位位置参数指定的任务：

1. 若参数是存在的绝对路径，直接使用。
2. 若参数是相对路径，先以项目根目录为基准检查。
3. 查找 `tasks/{任务名}.json`。
4. 查找项目根目录中的同名 JSON、TOML、YAML 或 YML 文件。
5. 返回预期的 `tasks/{任务名}.json` 路径，由后续逻辑决定是否存在。

例如：

```powershell
python main.py daily
python main.py -t tasks/full.json
python main.py -t .\my-tasks.json
```

`-t/--task` 会直接作为任务文件路径使用。相对路径以项目目录解析，因此可以从任意当前工作目录启动脚本。

## `TaskConfig` 解析细节

实现位于 `src/task.py`。两个数据类分别表示整体配置与单个任务：

```python
TaskConfig(
    client_type="Official",
    start_game_enabled=False,
    close_game_enabled=False,
    tasks=[Task(...)],
)

Task(
    name="显示名称",
    task_type="MaaCore 任务类型",
    params={...},
)
```

`Task.from_dict()` 的字段映射为：

| JSON 字段 | `Task` 字段 | 作用 |
| --- | --- | --- |
| `name` | `name` | 仅用于日志展示；缺失时回退到 `type`。 |
| `type` | `task_type` | 传给 MaaCore 的任务链类型。 |
| `params` | `params` | 原样序列化为 JSON 后传给 MaaCore。 |

`TaskConfig.from_file()` 当前真正解析的是 UTF-8 JSON。虽然任务查找函数会尝试 `.toml`、`.yaml` 和 `.yml` 扩展名，但配置加载器尚未实现这些格式；使用它们会返回 `None`。因此当前项目应使用 JSON。

## 顶层字段与任务字段

顶层的 `client_type`、`start_game_enabled`、`close_game_enabled` 会被保留在 `TaskConfig` 中，但主程序当前只逐项使用 `tasks`。实际生效的启动、关闭和客户端参数应放在对应任务的 `params` 内，例如：

```json
{
  "name": "启动",
  "type": "StartUp",
  "params": {
    "client_type": "Official",
    "start_game_enabled": false
  }
}
```

这意味着仅修改顶层 `client_type` 不会自动修改已存在的 `StartUp`、`Fight` 等任务参数。顶层字段目前更接近配置元数据，而不是运行时全局覆盖项。

## 任务追加与顺序

主程序按 JSON 数组顺序执行：

```python
for task in task_config.tasks:
    asst.append_task(task.task_type, task.params)
asst.start()
```

MaaCore 任务链是顺序队列。前一个任务失败、停止或等待页面条件时，会影响后续任务是否能执行。建议将 `StartUp` 放在依赖游戏主界面的任务之前；需要收尾时将 `CloseDown` 或基建收工任务放在最后。

JSON 中的 `name` 不影响执行顺序或 MaaCore 行为，只用于本项目日志，例如：

```text
添加 3 个任务...
  - 启动
  - 基建
  - 1-7
```

## 预置任务文件

| 文件 | 任务链意图 | 适用场景 |
| --- | --- | --- |
| `startup.json` | 只执行 `StartUp`。 | 验证连接、识别和游戏已在前台。 |
| `daily.json` | 启动、基建、战斗、访问、商店。 | 常规日常流程。 |
| `fight.json` | 启动后重复指定关卡。 | 单独刷图。 |
| `infrast_only.json` | 启动后处理基建。 | 只做换班或基建事务。 |
| `full.json` | 日常任务加公开招募和领奖。 | 完整日常。 |
| `roguelike.json` | 启动后运行集成战略。 | 肉鸽专项。 |

预置 JSON 的字段含义和任务类型参数见 [任务配置参考](tasks.md)。修改预置任务时建议复制为新文件，避免升级或调试时丢失对照基线。

## 参数如何传入 MaaCore

`Asst.append_task()` 最终执行：

```python
AsstAppendTask(
    assistant_pointer,
    type_name.encode("utf-8"),
    json.dumps(params, ensure_ascii=False).encode("utf-8"),
)
```

这有三个实际影响：

1. 参数键名必须符合当前 MaaCore 版本所支持的任务参数。
2. 中文干员名、商店物品名等会以 UTF-8 JSON 传入，不会被转义成 ASCII。
3. 本项目不会预先验证每个 `params` 字段；拼写错误、过时字段或无效值通常由 MaaCore 在运行时报告。

## 常见任务类型与依赖

| 类型 | 常用参数 | 前置条件 |
| --- | --- | --- |
| `StartUp` | `client_type`、`start_game_enabled` | 浏览器已进入云游戏、画面可识别。 |
| `Fight` | `stage`、`medicine`、`times`、`stone` | 已位于可进入作战的游戏状态。 |
| `Infrast` | `mode`、`facility`、`filename` | 基建计划和游戏版本兼容。 |
| `Recruit` | `select`、`confirm`、`times` | 公开招募界面可访问。 |
| `Mall` | `shopping`、`buy_first`、`blacklist` | 信用商店可访问。 |
| `Roguelike` | `theme`、`mode`、`squad`、`core_char` | 当前游戏版本支持对应主题。 |
| `Award`、`Visit` | 通常无参数 | 游戏主页和相应功能入口可访问。 |

任务参数可能随 MaaCore 和游戏版本变化。文档中的字段是本项目预置任务使用的集合，不是 MaaCore 全部参数的固定契约。

## 配置错误的定位

| 现象 | 最可能位置 | 检查方法 |
| --- | --- | --- |
| 启动时提示任务不存在 | 路径或任务名。 | 检查 `tasks/`、`-t` 参数和当前日志中的加载路径。 |
| JSON 解析失败 | JSON 语法或编码。 | 使用 UTF-8，检查逗号、引号和括号。 |
| 任务已追加但立即失败 | `type` 或 `params` 不兼容。 | 查看 MaaCore 回调和运行日志。 |
| 后续任务未执行 | 前置任务停止或页面状态异常。 | 检查任务追加顺序与首个失败任务。 |
| 战斗关卡不生效 | `stage` 格式或当前活动限制。 | 核对游戏内关卡与 MaaCore 当前资源。 |

## 新增任务的最小流程

1. 复制一个接近的 `tasks/*.json` 到新文件。
2. 保留顶层结构和 `tasks` 数组。
3. 每次只新增一个任务类型或参数变化。
4. 先用 `startup.json` 验证 ADB、截图和识别链路。
5. 再用新 JSON 单独运行，观察 MaaCore 日志。
6. 确认稳定后再把任务并入 `daily` 或 `full` 类型的长任务链。
