"""MAA、伪装设备和任务配置的程序入口。"""

import argparse
import logging
import os
import pathlib
import subprocess
import sys
import threading
import time
from datetime import datetime


PROJECT_DIR = pathlib.Path(__file__).resolve().parent
ADB_DIR = PROJECT_DIR / "platform-tools"
GAME_CODE = "mrfz"
CLOUD_URL = "https://cg.163.com"
# 可直接在此填写 MaaCore 目录；留空时继续读取其他配置来源。
DEFAULT_MAA_DIR = ""
DEFAULT_PLACEHOLDER_IMAGE = ""
ENV_FILE = PROJECT_DIR / ".env"


def read_env_value(name: str) -> str | None:
    """读取项目 .env 文件中的单个环境变量。"""
    if not ENV_FILE.is_file():
        return None
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def get_maa_dir_setting() -> str | None:
    """按优先级获取用户配置的 MaaCore 目录。"""
    return (
        os.environ.get("MAAE_MAA_DIR")
        or read_env_value("MAAE_MAA_DIR")
        or DEFAULT_MAA_DIR
        or None
    )


def resolve_placeholder_image() -> pathlib.Path | None:
    """解析用户配置的占位图路径。"""
    configured_path = (
        os.environ.get("MAAE_PLACEHOLDER_IMAGE")
        or read_env_value("MAAE_PLACEHOLDER_IMAGE")
        or DEFAULT_PLACEHOLDER_IMAGE
    )
    if not configured_path:
        return None

    image_path = pathlib.Path(configured_path).expanduser()
    if not image_path.is_absolute():
        image_path = PROJECT_DIR / image_path
    return image_path.resolve()


def resolve_maa_dir(configured_dir: str | None) -> pathlib.Path:
    """解析用户明确配置的 MaaCore 目录。"""
    if not configured_dir:
        raise FileNotFoundError(
            "未配置 MaaCore 目录。请使用 --maa-dir 或设置环境变量 MAAE_MAA_DIR。"
        )

    maa_dir = pathlib.Path(configured_dir).expanduser()
    if not maa_dir.is_absolute():
        maa_dir = PROJECT_DIR / maa_dir
    maa_dir = maa_dir.resolve()
    if not (maa_dir / "MaaCore.dll").exists():
        raise FileNotFoundError(f"MaaCore.dll 不存在: {maa_dir}")
    return maa_dir


def parse_args():
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="MAA + 云游戏自动化")
    parser.add_argument(
        "task_name",
        nargs="?",
        default="startup",
        help="任务名称（不带 .json），例如：daily、startup",
    )
    parser.add_argument(
        "-t",
        "--task",
        dest="task_path",
        help="任务配置文件的完整路径",
    )
    parser.add_argument(
        "--device-mode",
        choices=("placeholder", "realtime"),
        default="placeholder",
        help="伪设备截图传输模式",
    )
    parser.add_argument(
        "--maa-dir",
        default=get_maa_dir_setting(),
        help="MaaCore 目录，默认读取系统环境变量、.env 或顶部默认值",
    )
    return parser.parse_args()


def find_task_file(task_name: str) -> pathlib.Path:
    """查找任务配置文件。"""
    base_dir = PROJECT_DIR
    tasks_dir = PROJECT_DIR / "tasks"

    supplied_path = pathlib.Path(task_name)
    if supplied_path.is_absolute() and supplied_path.exists():
        return supplied_path
    if (PROJECT_DIR / supplied_path).exists():
        return PROJECT_DIR / supplied_path

    if tasks_dir.exists():
        for extension in (".json", ".toml", ".yaml", ".yml"):
            path = tasks_dir / f"{task_name}{extension}"
            if path.exists():
                return path

    for extension in (".json", ".toml", ".yaml", ".yml"):
        path = base_dir / f"{task_name}{extension}"
        if path.exists():
            return path

    return tasks_dir / f"{task_name}.json"


def setup_logging():
    """配置控制台和文件日志。"""
    log_dir = PROJECT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("maaease"), log_file


def get_device_functions(mode: str):
    """根据截图模式加载伪设备实现。"""
    if mode == "placeholder":
        from fake_device_placeholder import process_actions, set_page, start, update_screencap
    else:
        from fake_device import process_actions, set_page, start, update_screencap
    return start, set_page, update_screencap, process_actions


def main():
    """启动自动化任务并在结束后清理资源。"""
    from config.task import TaskConfig

    args = parse_args()
    log, _ = setup_logging()
    task_path = PROJECT_DIR / args.task_path if args.task_path else find_task_file(args.task_name)
    if task_path.exists():
        log.info(f"加载任务配置: {task_path}")
        task_config = TaskConfig.from_file(task_path)
    else:
        log.warning(f"任务配置不存在: {task_path}，将使用默认启动任务")
        task_config = None

    browser = None
    asst = None
    try:
        maa_dir = resolve_maa_dir(args.maa_dir)
        placeholder_image = resolve_placeholder_image()
        if placeholder_image:
            os.environ["MAAE_PLACEHOLDER_IMAGE"] = str(placeholder_image)

        # 启动本地 ADB 服务。
        adb_path = ADB_DIR / "adb.exe"
        os.environ["PATH"] = str(ADB_DIR) + ";" + os.environ.get("PATH", "")
        log.info("正在启动 ADB 服务...")
        subprocess.run([adb_path, "start-server"], capture_output=True)
        time.sleep(1)

        # 启动并连接伪设备。
        start, set_page, update_screencap, process_actions = get_device_functions(args.device_mode)
        log.info(f"伪设备截图模式: {args.device_mode}")
        threading.Thread(target=start, daemon=True).start()
        time.sleep(1)
        result = subprocess.run([adb_path, "connect", "127.0.0.1:5555"], capture_output=True, text=True)
        log.info(f"ADB 连接结果: {result.stdout.strip()}")

        # 浏览器会话由独立模块管理。
        from cloud_browser import CloudGameBrowser

        profile_dir = PROJECT_DIR / ".browser_profile"
        browser = CloudGameBrowser(profile_dir, GAME_CODE, CLOUD_URL, log)
        page = browser.launch()
        set_page(page)
        for _ in range(5):
            process_actions()
            update_screencap()
            time.sleep(0.3)

        # 加载 MaaCore 并执行任务。
        from asst import Asst
        from utils import InstanceOptionType

        log.info(f"正在加载 MaaCore: {maa_dir}")
        Asst.load(maa_dir)
        asst = Asst()
        asst.set_instance_option(InstanceOptionType.touch_type, "adb")
        connected = asst.connect("adb", "127.0.0.1:5555")
        log.info(f"MaaCore 连接结果: {connected} (页面: {page.url[:100]})")
        if not connected:
            return

        if task_config and task_config.tasks:
            log.info(f"添加 {len(task_config.tasks)} 个任务...")
            for task in task_config.tasks:
                log.info(f"  - {task.name or task.task_type}")
                asst.append_task(task.task_type, task.params)
        else:
            log.info("使用默认启动任务...")
            asst.append_task("StartUp", {"client_type": "Official", "start_game_enabled": False})

        asst.start()
        log.info(f"MAA 任务运行中，可按 Ctrl+C 停止 (页面: {page.url[:100]})")
        last_screencap_at = 0.0
        while asst.running():
            process_actions()
            now = time.monotonic()
            if now - last_screencap_at >= 0.1:
                update_screencap()
                last_screencap_at = now
            if "run.html" not in page.url:
                log.warning(f"页面已离开云游戏: {page.url[:100]}")
            time.sleep(0.02)

        asst.stop()
        log.info("MAA 任务正常完成。")
    except KeyboardInterrupt:
        log.info("收到 Ctrl+C，正在退出...")
    except SystemExit as exc:
        if exc.code != 0:
            log.error(f"程序以状态码 {exc.code} 退出")
    except Exception:
        log.exception("发生未预期异常:")
    finally:
        try:
            if asst and asst.running():
                asst.stop()
                log.info("已停止 MAA 任务。")
        except Exception:
            pass
        try:
            if browser:
                browser.close()
                log.info("浏览器已关闭。")
        except Exception:
            pass
        logging.shutdown()


if __name__ == "__main__":
    main()
