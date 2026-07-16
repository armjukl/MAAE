# 网易云游戏页面接入

## 范围

本项目没有调用网易云游戏的公开 HTTP 服务 API，也不实现账号、支付、排队或游戏数据接口。项目使用 Playwright 打开云游戏网页，并通过页面截图和鼠标事件完成浏览器自动化。

本文记录的是当前代码依赖的页面地址和浏览器交互方式，不应视为网易云游戏的官方 API 文档。

## 页面地址

| 用途 | 地址 |
| --- | --- |
| 云游戏主页 | `https://cg.163.com` |
| 游戏运行页 | `https://cg.163.com/run.html?code={游戏代码}&id={时间戳}&inline=1` |

当前默认游戏代码为 `mrfz`。`id` 使用当前毫秒时间戳，`inline=1` 使游戏以内嵌页面方式加载。

## 浏览器流程

`src/cloud_browser.py` 按以下顺序执行：

1. 使用持久化 Chromium 上下文启动浏览器。
2. 使用 `./.browser_profile/` 保存站点登录状态。
3. 打开云游戏主页。
4. 读取浏览器 `localStorage` 中是否存在 `NCG-token`，以判断是否已登录。
5. 未登录时等待用户在浏览器中手动完成登录，最长等待约 4 分钟。
6. 打开游戏运行页，等待 10 秒后将页面交给伪设备模块。

`NCG-token` 仅用于本地登录状态检测，项目不会读取、上传或打印其内容。

## 页面输入与画面

浏览器使用 `1280x720` 视口。伪设备模块会从 `canvas`、`video` 或整个页面获取 PNG 截图，并把 ADB 的点击与拖动请求转为 Playwright 鼠标操作。

页面运行期间不应离开 `run.html`。主循环检测到页面地址变化时会记录警告，通常意味着会话中断、页面跳转或云游戏退出。

## 登录与安全

- `.browser_profile/` 包含浏览器会话数据，应视为敏感本地目录。
- `.browser_profile/` 已在 `.gitignore` 中排除，不应手动添加到仓库。
- 需要重新登录时，可关闭程序后清理该目录，再次启动并在浏览器中完成登录。
- 页面结构、存储键名与运行页参数都可能随网易云游戏更新而变化，应以实际页面行为为准。

## 常见问题

| 现象 | 处理建议 |
| --- | --- |
| 浏览器没有打开 | 运行 `playwright install chromium`，并检查 `src/cloud_browser.py` 的启动日志。 |
| 一直等待登录 | 在浏览器窗口完成登录；确认站点未被网络策略拦截。 |
| 游戏页加载后无画面 | 检查 `run.html` 是否仍在地址栏中，以及浏览器是否有排队或提示页面。 |
| 截图不是游戏画面 | 查看页面中的 `canvas` 或 `video` 是否已加载，并尝试 `realtime` 截图模式。 |

## 源码职责与对象生命周期

浏览器接入全部封装在 `src/cloud_browser.py` 的 `CloudGameBrowser` 类中。该类保存三个有生命周期关系的对象：

```text
sync_playwright().start()
    -> Playwright 实例
        -> persistent BrowserContext
            -> Page
```

| 字段或方法 | 具体作用 |
| --- | --- |
| `_profile_dir` | 持久化浏览器数据目录，保存站点会话。 |
| `_game_code` | 游戏代码，当前由 `main.py` 设置为 `mrfz`。 |
| `_cloud_url` | 云游戏站点根地址。 |
| `_playwright` | Playwright 驱动对象，必须在关闭时调用 `stop()`。 |
| `context` | Chromium 持久化上下文，管理 cookie、存储和页面。 |
| `page` | 当前云游戏页面，供伪设备截图和鼠标输入使用。 |
| `launch()` | 创建对象、检测登录、打开运行页并返回 `Page`。 |
| `close()` | 先关闭上下文，再停止 Playwright 驱动。 |

`main.py` 只持有 `CloudGameBrowser` 实例和返回的页面，不直接调用 `sync_playwright()`。这样浏览器资源的创建和清理集中在一个模块，发生异常时也能由 `finally` 统一关闭。

## 启动参数的作用

浏览器上下文使用：

```python
launch_persistent_context(
    user_data_dir=str(profile_dir),
    headless=False,
    viewport={"width": 1280, "height": 720},
    device_scale_factor=1,
)
```

| 参数 | 作用 | 与伪设备的关系 |
| --- | --- | --- |
| `user_data_dir` | 保存登录状态、站点 cookie 和本地存储。 | 目录必须私有，不能提交。 |
| `headless=False` | 显示真实浏览器窗口，便于首次登录和人工观察。 | 用户可直接处理登录或排队页面。 |
| `viewport` | 指定 CSS 视口尺寸。 | 必须与 `wm size` 同为 `1280x720`。 |
| `device_scale_factor=1` | 截图按 CSS 像素生成。 | 使 MAA 坐标与页面鼠标坐标一致。 |

改变视口后，必须同步修改伪设备的 `DISPLAY_WIDTH`、`DISPLAY_HEIGHT` 和验证用的 MAA 资源识别效果；只改其中一处会造成点击偏移或图像缩放。

## 登录检测逻辑

`_wait_for_login()` 仅执行一个浏览器端 JavaScript 表达式：

```javascript
() => !!localStorage.getItem('NCG-token')
```

它只关心键是否存在，不读取令牌值，也不会将令牌写入日志、任务 JSON 或环境变量。未检测到登录状态时，代码每 2 秒重新检查一次，最多 120 次。超时后仍会尝试打开游戏页，实际页面可能显示登录、排队或错误提示，因此后续仍应检查截图和页面 URL。

## 运行页构造

`_open_game()` 以当前毫秒时间戳构造：

```text
{CLOUD_URL}/run.html?code={GAME_CODE}&id={毫秒时间戳}&inline=1
```

| 参数 | 项目内作用 | 注意事项 |
| --- | --- | --- |
| `code` | 选择云游戏，当前为 `mrfz`。 | 游戏代码是否有效由站点决定。 |
| `id` | 每次启动生成新的毫秒时间戳。 | 项目未依赖其具体业务语义。 |
| `inline` | 固定传入 `1`。 | 项目按当前页面行为使用，不保证站点长期兼容。 |

页面导航超时会记录警告而不是立即退出，以保留用户手动处理网络慢、排队或登录提示的机会。进入运行页后固定等待 10 秒，再将页面交给伪设备模块刷新首帧截图。

## 与伪设备的接口契约

浏览器模块不会直接处理 ADB。它向主程序返回 `Page`，随后主程序执行 `set_page(page)`。从这一刻起，伪设备模块可以：

| 伪设备操作 | Playwright 调用 | 前提 |
| --- | --- | --- |
| 更新截图缓存 | `元素.screenshot()` 或 `page.screenshot()` | 页面仍存活。 |
| 点击 | `page.mouse.click(x, y)` | 坐标与视口一致。 |
| 拖动 | `mouse.move()`、`mouse.down()`、`mouse.up()` | 必须满足同步 API 的线程约束。 |

浏览器关闭后，旧的页面对象失效。若 MaaCore 此时仍运行，日志会出现 `Target page, context or browser has been closed`；这表示上游会话已失效，应停止 MaaCore 而不是继续提供过期输入。

## 页面结构变化的影响

项目当前按 `canvas`、`video`、`#app canvas`、`#app video` 的顺序寻找游戏画面。若网易云游戏改用 shadow DOM、iframe、不同容器或更改登录存储键，可能出现以下症状：

| 页面变化 | 可观察现象 | 建议检查点 |
| --- | --- | --- |
| 游戏画面容器变更 | 截图变成空白或主页。 | 检查 `update_screencap()` 的选择器。 |
| 登录状态键变更 | 每次启动都等待手动登录。 | 检查 `_wait_for_login()` 的本地存储键。 |
| 运行页参数变更 | `run.html` 跳转或加载失败。 | 检查 `_open_game()` 构造的 URL。 |
| 浏览器缩放变化 | 识别正常但点击偏移。 | 检查 viewport、缩放与 `wm size`。 |

## 安全边界

本模块只进行浏览器自动化，不应扩展为抓取、伪造或绕过云游戏的服务端接口。登录会话属于用户本地数据；调试时应记录页面状态、截图字节数和 URL，而不是输出 cookie、localStorage 全量内容或令牌文本。
