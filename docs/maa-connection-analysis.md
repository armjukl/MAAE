# MaaCore 连接细节分析

## 连接目标

本项目的目标不是让 MaaCore 直接控制浏览器，而是让 MaaCore 相信自己连接到了一台标准 Android 设备。浏览器页面负责画面与输入，`src/fake_device*.py` 负责补齐 MaaCore 所需的 ADB 设备行为。

```text
MaaCore
  |
  | AsstConnect("adb", "127.0.0.1:5555", "General")
  v
platform-tools/adb.exe
  |
  | ADB 传输协议
  v
src/fake_device.py 或 src/fake_device_placeholder.py
  |                                      |
  | 截图缓存                             | 输入队列
  v                                      v
Playwright 页面截图                    Playwright 鼠标事件
  \                                      /
   +----------- 网易云游戏页面 ----------+
```

## 启动顺序

`main.py` 的连接顺序必须保持如下关系：

1. 解析 `.env`、系统环境变量或 `--maa-dir`，确认 MaaCore 目录中存在 `MaaCore.dll`。
2. 将 `platform-tools/` 加入当前进程的 `PATH`，并执行 `adb start-server`。
3. 以守护线程启动伪设备监听器，绑定 `127.0.0.1:5555`。
4. 执行 `adb connect 127.0.0.1:5555`，让本地 ADB daemon 建立到伪设备的传输通道。
5. 启动浏览器，进入云游戏页面，将 `Page` 对象交给伪设备模块。
6. 加载 MaaCore、创建 `Asst` 实例，并通过 ADB 地址执行 `AsstConnect`。
7. 追加任务后调用 `AsstStart`，主循环持续处理输入队列并刷新截图缓存。

若先连接 MaaCore、后启动伪设备，MaaCore 的设备探测会直接失败；若先启动 MaaCore、后设置浏览器页面，则早期截图请求只能得到回退图片。

## MaaCore 加载

`src/asst.py` 是 MaaCore 的 ctypes 封装。

1. `Asst.load(maa_dir)` 根据系统选择 `MaaCore.dll`、`libMaaCore.dylib` 或 `libMaaCore.so`。
2. MaaCore 所在目录被加入动态库搜索路径。
3. 通过 `AsstLoadResource` 加载该目录下的资源文件。
4. `Asst()` 调用 `AsstCreate` 创建助手实例。
5. `set_instance_option(InstanceOptionType.touch_type, "adb")` 指定触控实现为 ADB 输入。
6. `connect("adb", "127.0.0.1:5555")` 调用底层 `AsstConnect`。

默认连接配置名为 `General`。这意味着 MaaCore 会以通用 ADB 设备方式探测显示尺寸、系统属性、截图能力与输入能力，而不会知道后端实际是浏览器页面。

## ADB 探测过程

MaaCore 连接后通常会发送多条 shell 或 exec 请求。当前伪设备实现重点响应以下探测行为：

| 探测目的 | 常见命令 | 伪设备响应 |
| --- | --- | --- |
| 识别设备 | `settings get secure android_id` | 固定 Android ID。 |
| 识别系统版本 | `getprop` | Android 11、SDK 30、CPU 架构等。 |
| 获取分辨率 | `wm size` | `1280x720`。 |
| 获取画面 | `screencap` 及其变体 | 浏览器截图缓存的 PNG。 |
| 验证包信息 | `pm path` | 模拟的游戏包路径。 |
| 发送触控 | `input tap`、`input swipe` | 放入本地输入队列。 |

伪设备只实现 MaaCore 当前使用的最小命令集合，不是完整的 `adbd` 实现。新增 MaaCore 版本若发送未覆盖命令，应先从运行日志中确认命令内容，再补充模拟结果。

## 截图通路

截图包含两个线程边界：

```text
主线程: update_screencap() -> Playwright Page/元素截图 -> _cached_screencap
ADB 线程: _screencap() -> 加锁读取 _cached_screencap -> ADB WRTE 数据块
```

Playwright 同步 API 必须在创建 `Page` 的线程调用，因此浏览器截图只能由主循环刷新。ADB 连接线程只读取内存缓存，避免跨线程调用 Playwright。

`realtime` 模式每次读取缓存；`placeholder` 模式每秒最多放行一次实时缓存，其余时间返回 `MAAE_PLACEHOLDER_IMAGE` 配置的图片。两种模式都使用同一个缓存锁，避免读取到半写入的 PNG。

## 输入通路

```text
MaaCore -> adb shell input tap/swipe -> ADB 线程 -> _action_queue
                                                    |
                                                    v
主循环 process_actions() -> Page.mouse.click/move/down/up
```

点击由主循环调用 `Page.mouse.click()`。拖动命令会将请求时长限制为不超过 500ms，再按多个鼠标移动步骤模拟手势。

当前拖动实现使用后台线程调用 Playwright 同步 API。Playwright 对象具有线程亲和性，若日志出现 `Cannot switch to a different thread`，说明后台拖动线程无法访问创建页面的线程。此时应先保留截图和点击链路的日志，再调整输入调度方案；不能简单在 ADB 连接线程直接调用 `Page.mouse`。

## 任务生命周期

任务配置由 `TaskConfig.from_file()` 读取。每个任务通过 `AsstAppendTask` 追加至 MaaCore 队列，随后由 `AsstStart` 执行。主循环通过 `AsstRunning` 判断是否结束：

```text
追加任务 -> AsstStart -> AsstRunning 为真
                         |-> 处理输入队列
                         |-> 刷新浏览器截图缓存
                         |-> 检查云游戏页面仍为 run.html
                         +-> AsstRunning 为假后停止并关闭浏览器
```

退出时 `main.py` 会尝试停止仍在运行的 MaaCore 任务，并关闭浏览器上下文。伪设备监听线程为守护线程，随 Python 进程结束。

## 排障顺序

1. 确认 `MAAE_MAA_DIR` 指向包含 `MaaCore.dll` 的目录。
2. 确认日志出现 `ADB 连接结果: connected to 127.0.0.1:5555`。
3. 确认随后出现 `settings`、`getprop`、`wm size` 和 `screencap` 请求。
4. 确认 `MaaCore 连接结果: True`。
5. 若识别异常，检查截图模式、截图字节数和浏览器页面地址。
6. 若输入异常，检查 `input tap` 或 `input swipe` 后的 `[action]`、`[swipe]` 日志。

## 源码职责与调用关系

| 文件 | 关键对象或函数 | 具体作用 |
| --- | --- | --- |
| `main.py` | `main()` | 组织配置、进程、伪设备、浏览器和 MaaCore 的生命周期。 |
| `main.py` | `resolve_maa_dir()` | 校验 `MAAE_MAA_DIR` 或 `--maa-dir`，确保目标目录有 `MaaCore.dll`。 |
| `main.py` | `resolve_placeholder_image()` | 将 `.env` 中的占位图相对路径解析为进程可使用的绝对路径。 |
| `src/asst.py` | `Asst.load()` | 加载 MaaCore 动态库、声明 ctypes 签名并加载资源。 |
| `src/asst.py` | `Asst.connect()` | 封装底层 `AsstConnect`，将 ADB 程序名、地址和配置名传给 MaaCore。 |
| `src/cloud_browser.py` | `CloudGameBrowser` | 持有 Playwright、浏览器上下文和页面对象。 |
| `src/fake_device*.py` | `handle()` | 解析 ADB 数据包并把 shell/exec 命令分发给 `_exec()`。 |
| `src/fake_device*.py` | `update_screencap()` | 在浏览器拥有线程中更新 PNG 截图缓存。 |
| `src/fake_device*.py` | `process_actions()` | 在主循环中消费触控队列并调用页面鼠标接口。 |
| `src/task.py` | `TaskConfig`、`Task` | 把 JSON 任务转换为传入 MaaCore 的任务类型和参数。 |

从依赖方向看，`main.py` 是唯一同时认识浏览器、伪设备与 MaaCore 的编排层；伪设备模块不应导入 MaaCore，MaaCore 封装也不应了解 Playwright。这种边界能让两种截图策略独立替换。

## `main.py` 的执行细节

### 配置读取

`read_env_value()` 逐行读取项目根目录 `.env`，忽略空行、注释行和不含 `=` 的行。它不修改系统环境，只返回请求的配置值。

`parse_args()` 在解析参数时为 `--maa-dir` 设置默认值。该默认值来自以下顺序：系统环境变量 `MAAE_MAA_DIR`、`.env`、`DEFAULT_MAA_DIR`。因为 argparse 对显式参数优先，最终完整优先级为：

```text
--maa-dir
  > 系统环境变量 MAAE_MAA_DIR
  > .env 的 MAAE_MAA_DIR
  > DEFAULT_MAA_DIR
```

`resolve_maa_dir()` 会把相对路径拼接到 `PROJECT_DIR` 后再调用 `resolve()`。因此 `.env` 可以使用可移植的相对路径，而传给 ctypes 的始终是标准化后的实际目录。

### 建立运行环境

`main()` 在 `try` 块的开头先验证 MaaCore 目录和可选占位图路径。这样路径错误会在打开浏览器前失败。之后的关键代码等价于：

```python
subprocess.run([adb_path, "start-server"])
threading.Thread(target=start, daemon=True).start()
subprocess.run([adb_path, "connect", "127.0.0.1:5555"])
```

这里有三个不同的角色：

- `adb.exe` 是客户端和本地 daemon，不是伪设备本身。
- `start()` 是伪设备的 TCP 服务端，模拟的是远端 Android 设备。
- `adb connect` 要求本地 daemon 主动连接伪设备，后续 MaaCore 才能通过同一个 daemon 使用该地址。

### 主循环

MaaCore 成功启动后，循环每约 20ms 执行一次。`process_actions()` 先处理 ADB 线程排入的输入，`update_screencap()` 最多每 100ms 产生一次新截图。100ms 是刷新节流，不是 ADB 请求节流；ADB 收到更多截图请求时只会重复返回最近缓存。

循环还检查 `page.url` 是否仍包含 `run.html`。该检查不能修复会话中断，但能在日志中标出浏览器已离开游戏页的时间点。

## `Asst.load()` 的 ctypes 细节

`src/asst.py` 不是重新实现 MaaCore，而是为动态库建立 Python 调用边界。

### 动态库定位

在 Windows 上，`Asst.load(path)` 的目标文件是：

```text
{path}/MaaCore.dll
```

函数会把该目录追加到当前进程的 `PATH`，再用 `ctypes.WinDLL` 加载 DLL。若按路径加载失败，代码会调用 `ctypes.util.find_library("MaaCore")` 作为后备查找。加载成功后调用 `AsstLoadResource(path)`，因此 MaaCore 资源目录必须与 DLL 的版本匹配。

### 函数签名

`__set_lib_properties()` 为每个 C 接口设置 `restype` 与 `argtypes`。这一步不可省略：例如 `AsstConnect` 的地址、ADB 路径和配置名都是 `c_char_p`；若 Python 未正确声明参数，64 位进程可能因指针转换错误导致连接失败或崩溃。

最关键的底层调用对应关系如下：

| Python 方法 | MaaCore 接口 | 作用 |
| --- | --- | --- |
| `Asst.load()` | `AsstLoadResource` | 加载任务识别资源。 |
| `Asst()` | `AsstCreate` | 创建助手实例。 |
| `set_instance_option()` | `AsstSetInstanceOption` | 设定触控方式等实例选项。 |
| `connect()` | `AsstConnect` | 建立到 ADB 地址的连接。 |
| `append_task()` | `AsstAppendTask` | 将任务 JSON 追加到队列。 |
| `start()` | `AsstStart` | 运行任务队列。 |
| `running()` | `AsstRunning` | 查询任务是否尚在执行。 |
| `stop()` | `AsstStop` | 请求停止任务。 |

### 连接参数

主程序传入：

```python
asst.set_instance_option(InstanceOptionType.touch_type, "adb")
connected = asst.connect("adb", "127.0.0.1:5555")
```

第一个参数 `adb` 是希望 MaaCore 使用的 ADB 程序名。由于主程序已将 `platform-tools/` 加入 `PATH`，MaaCore 能找到同目录中的 `adb.exe`。第二个参数是设备地址。第三个参数未传入时由 `Asst.connect()` 默认使用 `General`，决定 MaaCore 使用通用 ADB 探测策略。

## ADB 数据包的实现细节

### 包格式

`adb_header()` 使用：

```python
struct.pack("<6I", command, arg0, arg1, length, checksum, magic)
```

每个 ADB 数据包包含 24 字节头部：

| 字段 | 作用 |
| --- | --- |
| `command` | 命令编号，例如 `CNXN`、`OPEN`、`WRTE`。 |
| `arg0`、`arg1` | 连接或逻辑流的本地/远端标识。 |
| `length` | 后续负载长度。 |
| `checksum` | 负载字节和。 |
| `magic` | `command ^ 0xFFFFFFFF`，用于基本校验。 |

`handle()` 维护一个 `buf` 缓冲区。TCP 不保证一次 `recv()` 恰好得到一个 ADB 包，因此代码先积累数据，再只有在 `len(buf) >= 24 + payload_length` 时处理完整包。这个缓冲机制是协议能稳定工作的基础。

### 连接与逻辑流

收到 `CNXN` 后，伪设备返回带有设备属性的 `CNXN`，其中 `ro.adb.secure=0` 让客户端跳过 ADB 鉴权。

收到 `OPEN` 后，代码从负载取出类似 `shell:wm size` 或 `exec:screencap -p` 的目标字符串。每条逻辑流都会生成 `our_id`，并按以下顺序回复：

```text
OKAY -> 一个或多个 WRTE -> CLSE
```

截图可能大于单个安全数据块，因此结果以 512KB 分片循环发送。发送 `CLSE` 后，MaaCore 会将这次 shell/exec 命令视为完成。

### 有意简化的部分

当前实现没有完整覆盖 ADB 的认证、流量确认、双向 WRTE 交互、文件同步服务和安装 APK 协议。它的目标是满足 MaaCore 的探测、截图和输入调用，不适合作为通用 ADB 服务端。

## 浏览器模块的细节

`CloudGameBrowser.launch()` 先执行 `sync_playwright().start()`，然后创建持久化 Chromium 上下文：

```python
launch_persistent_context(
    user_data_dir=".browser_profile",
    viewport={"width": 1280, "height": 720},
    device_scale_factor=1,
)
```

持久化上下文的作用是保存站点登录状态；`device_scale_factor=1` 使 Playwright PNG 截图的 CSS 像素与伪设备上报坐标一致。随后模块：

1. 打开 `https://cg.163.com`。
2. 检查 `localStorage` 是否存在 `NCG-token`。
3. 未登录时每 2 秒检查一次，最多 120 次。
4. 打开 `run.html?code=mrfz&id={毫秒时间戳}&inline=1`。
5. 等待画面加载后，把 `Page` 返回给主程序。

`close()` 先关闭浏览器上下文，再停止 Playwright 驱动。无论任务正常结束、连接失败还是收到 Ctrl+C，`main.py` 的 `finally` 都会尝试执行这一步。

## 截图代码的细节

`update_screencap()` 只应在创建 `Page` 的线程调用。它按以下顺序尝试元素选择器：

```text
canvas -> video -> #app canvas -> #app video -> 整个页面
```

找到元素时使用元素截图；没有元素时使用 `page.screenshot()`。获取到 PNG 后，在 `_screencap_lock` 保护下替换 `_cached_screencap`。

ADB 线程调用 `_screencap()` 时只做两件事：加锁取出当前 `bytes` 引用，按模式返回该引用或占位图。它绝不能直接调用 `Page.screenshot()`，否则会发生同步 Playwright 的跨线程切换异常。

缓存还有两个边界条件：

- 浏览器还未设置页面或首帧尚未完成时，实时模式会使用占位图回退。
- 浏览器已经关闭而 MaaCore 仍在请求截图时，`update_screencap()` 会记录截图异常，ADB 端仍可能返回最后一帧缓存。

## 输入代码的细节与限制

`_exec()` 通过 `cmd.split()` 解析 `input tap` 与 `input swipe`。它不会立刻操作页面，而是将元组放入线程安全的 `_action_queue`：

```python
("tap", x, y)
("swipe", x1, y1, x2, y2, duration)
```

主循环的 `process_actions()` 使用 `get_nowait()` 取出所有已有动作。点击直接调用 `Page.mouse.click()`；拖动会限制为至多 500ms、至少 10 个移动步骤，并在鼠标按下后沿线性插值移动到终点。

现有拖动函数由后台线程执行，以避免占用主循环。然而 `Page.mouse` 属于同步 Playwright 对象，必须由创建页面的线程访问。当前结构因此存在明确风险：拖动时可能出现 `Cannot switch to a different thread`。这不是 ADB 协议错误，而是 Python 线程与 Playwright 同步 API 的约束。

后续若要修复拖动，应把手势拆成由主线程高频调度的状态机，并在拖动期间避免耗时截图；或迁移到专门管理异步 Playwright 事件循环的架构。无论采用哪种方案，都不能从 ADB 处理线程直接调用 `Page.mouse`。
