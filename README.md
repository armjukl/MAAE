# maaease

网易云游戏 + MAA 自动化，通过伪装 ADB 设备让 MaaCore 控制浏览器中的云游戏。

## 文件说明

| 文件 | 作用 |
|------|------|
| `test_v1_fake_adb.py` | **主入口** — 启动 ADB / 浏览器 / MAA，主循环 |
| `fake_device.py` | 伪装 ADB 设备（监听 5555），截屏 + 触摸转发 |
| `asst.py` | MaaCore (MAA) Python 绑定 |
| `utils.py` | MAA 配置枚举 (InstanceOptionType 等) |
| `requirements.txt` | Python 依赖 |

## 环境准备

```bash
# 1. Python 依赖
pip install -r requirements.txt

# 2. Chromium 浏览器 (Playwright)
playwright install chromium

# 3. 准备以下目录/文件：
#    - MAA 安装目录 (如 MAA-v6.14.1-win-x64/)
#    - Android platform-tools (adb.exe)
```

## 配置

编辑 `test_v1_fake_adb.py` 顶部的配置：

```python
ADB_DIR = r"你的platform-tools目录"
MAA_DIR = r"你的MAA安装目录"
GAME_CODE = "mrfz"        # 明日方舟
```

## 运行

```bash
python test_v1_fake_adb.py
```

首次运行需要手动登录网易云游戏，之后浏览器 profile 会保存登录状态。

## 工作流程

```
test_v1_fake_adb.py
  ├── 启动 adb daemon
  ├── 启动 fake_device (监听 127.0.0.1:5555)
  ├── adb connect 127.0.0.1:5555
  ├── 启动 Chromium → 打开 cg.163.com → 进入云游戏
  ├── 加载 MaaCore → 连接伪装设备
  └── 主循环: process_actions() + update_screencap()
```

.browser_profile/为储存网易云游戏token实现自动登录

## 日志

运行日志保存在 `logs/run_YYYYMMDD_HHMMSS.log`，每次启动不覆盖。
