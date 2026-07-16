# MAAEase

通过伪装 ADB 设备，让 MaaCore 操作网易云游戏中的《明日方舟》。浏览器会话、ADB 协议和任务配置均由本项目管理。

## 环境准备

```powershell
pip install -r requirements.txt
playwright install chromium
```

项目自带 `./platform-tools/adb.exe`。首次启动需要在浏览器中手动登录网易云游戏，登录信息保存在 `./.browser_profile/`。

## MaaCore 目录配置

MaaCore 目录必须包含 `MaaCore.dll`。支持四种配置来源，优先级从高到低如下：

1. 命令行参数 `--maa-dir`
2. 系统环境变量 `MAAE_MAA_DIR`
3. 项目根目录 `.env` 文件中的 `MAAE_MAA_DIR`
4. `main.py` 顶部的 `DEFAULT_MAA_DIR`

推荐复制 `.env.example` 为 `.env`，然后填写 MaaCore 目录：

```text
MAAE_MAA_DIR=..\MAA-v6.14.1-win-x64
```

`.env` 已加入 Git 忽略规则。相对路径以项目目录为基准，绝对路径也可使用。

占位截图路径使用同一份 `.env` 配置：

```text
MAAE_PLACEHOLDER_IMAGE=..\netease-cloudgame-reverse\output\after_clicks.png
```

未配置或文件不可读时，伪设备会回退到内置的空白 PNG。

也可以在单次运行时指定目录：

```powershell
python main.py --maa-dir ..\MAA-v6.14.1-win-x64
```

## 运行

```powershell
python main.py
python main.py daily
python main.py daily --device-mode realtime
python main.py -t tasks/full.json
```

`--device-mode placeholder` 是默认模式，会按实验逻辑限制实时截图返回；`--device-mode realtime` 每次直接返回最新缓存截图。

运行日志保存在 `./logs/`，任务配置位于 `./tasks/`。
