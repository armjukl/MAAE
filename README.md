# MAAEase

MAAEase 通过本地伪装 ADB 设备，将 MaaCore 的截图和触控请求桥接到网易云游戏浏览器页面，使 MAA 能在云游戏中执行《明日方舟》任务。

## 工作方式

```text
MaaCore -> adb 127.0.0.1:5555 -> 伪装 ADB 设备 -> Playwright 浏览器 -> 网易云游戏
                                      ^                    |
                                      +------ 截图缓存 ------+
```

| 组件 | 作用 |
| --- | --- |
| `main.py` | 启动 ADB、伪设备、浏览器与 MaaCore，并执行任务循环。 |
| `src/cloud_browser.py` | 管理浏览器启动、登录等待、进入云游戏和资源关闭。 |
| `src/fake_device.py` | 每次截图请求直接返回最新的缓存截图。 |
| `src/fake_device_placeholder.py` | 按实验逻辑限制实时截图，其余请求返回占位图。 |
| `tasks/` | MAA 任务配置，例如日常、战斗、基建和肉鸽。 |

## 环境准备

```powershell
pip install -r requirements.txt
playwright install chromium
```

Windows 下可直接双击 `环境准备.bat`，它会自动执行上述两步。

项目使用 `./platform-tools/adb.exe`。首次启动时需在弹出的浏览器中手动登录网易云游戏，登录状态保存在 `./.browser_profile/`。

## 本地配置

复制 `.env.example` 为 `.env`，并按本机情况填写路径：

```text
MAAE_MAA_DIR=..\MAA-v6.14.1-win-x64
MAAE_PLACEHOLDER_IMAGE=..\netease-cloudgame-reverse\output\after_clicks.png
```

`MAAE_MAA_DIR` 指向包含 `MaaCore.dll` 的目录。占位图路径仅供 `placeholder` 模式使用；不可用时程序会回退到内置空白 PNG。

MaaCore 路径的优先级从高到低为：

1. 命令行 `--maa-dir`
2. 系统环境变量 `MAAE_MAA_DIR`
3. 项目 `.env` 文件
4. `main.py` 顶部的 `DEFAULT_MAA_DIR`

相对路径以项目目录为基准解析。`.env` 已被 Git 忽略，不会上传个人路径或登录信息。

## 运行

```powershell
python main.py
python main.py daily
python main.py fight --device-mode realtime
python main.py -t tasks/full.json
python main.py --maa-dir ..\MAA-v6.14.1-win-x64
```

`placeholder` 是默认截图模式；使用 `--device-mode realtime` 可切换为持续返回最新缓存截图的实现。运行日志写入 `./logs/`。

## 文档

- [伪装 ADB 设备](docs/adb-fake-device.md)
- [网易云游戏页面接入](docs/netease-cloudgame-api.md)
- [MaaCore 连接细节](docs/maa-connection-analysis.md)
- [任务配置](docs/tasks.md)
- [任务配置执行分析](docs/task-configuration-analysis.md)

## 注意事项

- 请勿提交 `.browser_profile/`、`.env` 或 `logs/`。
- 项目只读取浏览器中的登录状态；不提供网易云游戏账号密码或令牌的管理功能。
- 云游戏页面、登录流程和 MaaCore 版本发生变化时，截图、坐标或任务识别可能需要重新验证。

## 源码结构

| 文件或目录 | 关键对象 | 作用与边界 |
| --- | --- | --- |
| `main.py` | `main()` | 唯一的运行编排层，创建并销毁 ADB、伪设备、浏览器和 MaaCore。 |
| `main.py` | `read_env_value()` | 无第三方依赖地读取项目 `.env` 文件。 |
| `main.py` | `resolve_maa_dir()` | 校验 MaaCore 目录，避免浏览器启动后才发现 DLL 不存在。 |
| `src/cloud_browser.py` | `CloudGameBrowser` | 只管理 Playwright 浏览器会话，不处理 ADB 或 MAA 任务。 |
| `src/asst.py` | `Asst` | MaaCore 动态库的 ctypes 封装，负责 C 接口参数转换。 |
| `src/fake_device.py` | `handle()`、`_exec()` | 简化 ADB 服务端，处理 MaaCore 的设备探测、截图与输入命令。 |
| `src/fake_device_placeholder.py` | `_screencap()` | 与实时模式共用协议和输入逻辑，仅改变截图返回策略。 |
| `src/task.py` | `TaskConfig`、`Task` | 将任务 JSON 转成 MaaCore 的任务队列参数。 |
| `tasks/*.json` | 任务列表 | 运行时数据，不包含执行代码。 |
| `docs/` | 设计文档 | 记录各模块的协议、页面接入和配置细节。 |

## 完整运行时序

```text
读取 .env/参数
    -> 校验 MaaCore.dll
    -> adb start-server
    -> 启动 127.0.0.1:5555 伪设备
    -> adb connect 127.0.0.1:5555
    -> 启动持久化 Chromium 并进入 run.html
    -> 首次刷新浏览器截图缓存
    -> Asst.load + AsstConnect
    -> AsstAppendTask + AsstStart
    -> 处理输入队列并周期刷新截图
    -> 任务结束后关闭浏览器
```

这个顺序不能随意交换。MaaCore 连接前必须先存在 ADB 地址；伪设备开始响应截图前必须先绑定浏览器页面；浏览器退出后不应继续运行 MaaCore 任务。

## 配置字段参考

### `MAAE_MAA_DIR`

- 来源：`--maa-dir`、系统环境变量、`.env` 或 `DEFAULT_MAA_DIR`。
- 作用：指定包含 `MaaCore.dll` 的 MaaCore 安装目录。
- 缺失时行为：程序在启动浏览器前报错。

### `MAAE_PLACEHOLDER_IMAGE`

- 来源：系统环境变量、`.env` 或 `DEFAULT_PLACEHOLDER_IMAGE`。
- 作用：为 `placeholder` 截图模式指定回退 PNG。
- 缺失时行为：伪设备返回内置空白 PNG。

### `DEFAULT_MAA_DIR` 与 `DEFAULT_PLACEHOLDER_IMAGE`

- 来源：`main.py` 顶部常量。
- 作用：为未使用参数、系统环境变量或 `.env` 的本地环境提供默认值。
- 缺失时行为：两者默认均为空字符串。

### `--device-mode`

- 来源：命令行参数。
- 作用：选择 `placeholder` 或 `realtime` 截图策略。
- 缺失时行为：默认使用 `placeholder`。

### `--task`

- 来源：命令行参数。
- 作用：指定任务 JSON 路径。
- 缺失时行为：使用位置参数对应的 `tasks/*.json` 文件。

## 日志与排障入口

每次运行会生成 `logs/run_YYYYMMDD_HHMMSS.log`。建议按以下层级定位问题：

1. 先确认 MaaCore 目录、`adb start-server` 与 `adb connect` 是否成功。
2. 再确认浏览器已打开 `run.html`，并出现截图缓存日志。
3. 确认 `MaaCore 连接结果: True` 后再分析任务问题。
4. 识别失败优先检查截图模式、缓存字节数和 `wm size`。
5. 输入失败优先检查 `input tap`、`input swipe`、`[action]` 和 `[swipe]` 日志。
