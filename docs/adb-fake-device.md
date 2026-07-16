# 伪装 ADB 设备

## 目标

MaaCore 只能通过 ADB 与 Android 设备交互。本项目不启动模拟器，而是在 `127.0.0.1:5555` 监听一个简化的 ADB 服务，将 MaaCore 的截图与输入命令转发到浏览器中的云游戏页面。

实现位于 `src/fake_device.py` 和 `src/fake_device_placeholder.py`。二者的 ADB 协议与输入逻辑相同，仅截图返回策略不同。

## 连接流程

```text
1. main.py 启动 platform-tools/adb.exe 的服务端。
2. 伪设备在 127.0.0.1:5555 监听连接。
3. adb connect 127.0.0.1:5555 建立连接。
4. MaaCore 使用 adb 连接该地址。
5. 伪设备把截图和触控命令桥接到 Playwright 页面。
```

服务端处理 ADB 的 `CNXN`、`OPEN`、`WRTE` 与 `CLSE` 数据包，并对 `shell:`、`exec:` 和 `exec-out:` 通道返回模拟结果。截图数据会以不超过 512KB 的 ADB 数据块分段发送。

## 已模拟命令

| 命令类别 | 返回或行为 |
| --- | --- |
| `settings get secure android_id` | 返回固定 Android ID。 |
| `getprop` | 返回 Android 11、SDK 30、`x86_64` 等设备信息。 |
| `wm size` | 返回 `1280x720`，与浏览器视口一致。 |
| `screencap` | 返回浏览器页面缓存的 PNG 截图。 |
| `input tap x y` | 将点击放入队列，由主线程调用 `page.mouse.click()`。 |
| `input swipe ...` | 将拖动放入队列，按请求时长执行，最长限制为 500ms。 |
| `pm path` | 返回模拟的《明日方舟》包路径。 |
| 其他查询命令 | 返回空行，以满足 MaaCore 的探测流程。 |

## 截图模式

### `realtime`

`src/fake_device.py` 每次收到截图请求时，都返回最新的浏览器截图缓存。适合优先保证识别画面新鲜度的场景。

### `placeholder`

`src/fake_device_placeholder.py` 每秒最多返回一次实时截图，其余请求返回 `MAAE_PLACEHOLDER_IMAGE` 指向的 PNG。若未配置或读取失败，则使用内置空白 PNG。该模式用于比较不同截图返回策略对 MaaCore 的影响。

通过以下参数切换：

```powershell
python main.py --device-mode realtime
python main.py --device-mode placeholder
```

## 坐标与截图

浏览器视口固定为 `1280x720`，伪设备也向 MaaCore 上报 `1280x720`。点击与拖动坐标会直接传递给 Playwright 鼠标接口，因此截图尺寸、浏览器视口与 ADB 上报尺寸必须保持一致。

## 排障

| 现象 | 检查方向 |
| --- | --- |
| `adb connect` 失败 | 检查 5555 端口是否被占用，以及 `platform-tools/adb.exe` 是否可执行。 |
| MaaCore 连接失败 | 查看日志中 `getprop`、`wm size` 与 `screencap` 请求是否正常出现。 |
| 识别画面过期 | 使用 `--device-mode realtime`，并检查浏览器页面是否仍处于云游戏页面。 |
| 点击偏移 | 检查浏览器视口和 `wm size` 是否均为 `1280x720`。 |
| 拖动失败 | 查看日志中的 `input swipe` 和 `[swipe]` 记录；同步 Playwright API 不支持跨线程调用。 |

## 源码级职责

两份伪设备实现共享相同的 ADB 数据包、设备探测、截图缓存和输入队列逻辑。差异集中在 `_screencap()`：

| 函数或变量 | 作用 |
| --- | --- |
| `PORT` | 本地监听端口，固定为 5555。 |
| `A_CNXN`、`A_OPEN`、`A_WRTE` 等 | ADB 传输协议命令编号。 |
| `adb_header()` | 组装 24 字节 ADB 包头及负载。 |
| `handle()` | 为每个 TCP 连接解析完整 ADB 包并生成响应。 |
| `_exec()` | 将 shell/exec 字符串映射为模拟设备命令。 |
| `_cached_screencap` | 最近一次浏览器截图的 PNG 字节。 |
| `_screencap_lock` | 协调主线程写缓存和 ADB 线程读缓存。 |
| `_action_queue` | 在 ADB 线程和浏览器主线程之间传递点击、拖动事件。 |
| `update_screencap()` | 在 Playwright 所属线程创建截图缓存。 |
| `process_actions()` | 在主循环消费输入队列并操作鼠标。 |

## ADB 包解析过程

`handle()` 不假设一次 `recv(4096)` 就得到完整请求。它会先把字节追加到 `buf`，从头部解出：

```text
command | arg0 | arg1 | payload_length | checksum | magic
```

只有当缓冲区至少包含 `24 + payload_length` 字节时才取出一个包。处理后会保留剩余字节，继续解析下一个包。这使协议能正确处理 TCP 分包、粘包和大截图数据。

对于 `OPEN` 命令，`arg0` 被保存为客户端的逻辑流标识，服务端生成新的 `our_id`。执行命令后按 `OKAY -> WRTE -> CLSE` 顺序回复。截图可能很大，因此每个 `WRTE` 最多携带 512KB，避免超过 ADB 协议声明的单包上限。

## 设备身份与探测兼容性

返回 `CNXN` 时的 banner 包含：

```text
ro.product.name=cloud
ro.product.model=Playwright
ro.product.device=cloud
ro.adb.secure=0
```

`ro.adb.secure=0` 的意义是跳过 ADB 认证挑战。它只适用于绑定到 `127.0.0.1` 的本地实验服务，不能用于暴露到局域网或公网的 ADB 端口。

MaaCore 并不要求真正安装游戏 APK；`pm path` 返回的是模拟包路径。真正关键的是系统属性、分辨率、截图和 `input` 命令能形成自洽的设备行为。

## 截图缓存实现

`update_screencap()` 先尝试截图 `canvas`、`video`、`#app canvas`、`#app video`，最后回退到整个 `Page`。选择器顺序的目的是优先裁取云游戏画面，避免网页周围的非游戏元素干扰 MAA 识别。

截图完成后，代码在锁内用新的 `bytes` 替换 `_cached_screencap`。读取端只持锁取得引用，不在锁内做网络发送；这样 ADB 线程不会因大 PNG 分片发送而阻塞下一帧截图。

两种模式的差异如下：

| 模式 | 实时缓存返回规则 | 占位图用途 |
| --- | --- | --- |
| `realtime` | 只要缓存存在便直接返回。 | 仅在首帧缓存尚未生成时回退。 |
| `placeholder` | 相邻两次实时返回至少间隔一秒。 | 其余请求使用配置的占位图。 |

占位图由 `MAAE_PLACEHOLDER_IMAGE` 指定。主程序会先解析 `.env` 的相对路径，再写入当前进程环境，伪设备模块只读取最终的环境变量值。

## 输入队列与线程边界

ADB 的 `input` 命令在 `handle()` 所在的 TCP 线程接收，而同步 Playwright `Page` 由主线程创建。因此 `_exec()` 只入队：

```python
_action_queue.put(("tap", x, y))
_action_queue.put(("swipe", x1, y1, x2, y2, duration))
```

`main.py` 的主循环调用 `process_actions()`。点击可在该线程直接调用 `mouse.click()`；拖动实现会按线性插值连续调用 `mouse.move()`，并将时长限制为 500ms，防止云游戏将超长手势判为无效。

当前拖动函数使用后台线程以避免主循环长时间停顿，但这与同步 Playwright 的线程亲和性冲突。若出现 `greenlet.error` 或 `Cannot switch to a different thread`，截图和点击仍可作为独立链路排查，拖动需要单独调整调度架构。

## 协议范围与扩展方式

该服务不是完整 Android Debug Bridge 实现，以下能力被刻意省略：设备认证、文件同步、APK 安装、端口转发、完整 shell、反向 WRTE 确认和多设备管理。

当 MaaCore 更新后出现未知命令时，先从日志中的 `[device] OPEN ...` 和 `[exec] ...` 记录提取实际命令，再在 `_exec()` 中添加最小且稳定的模拟响应。不要把真实系统命令直接执行到宿主机上。
