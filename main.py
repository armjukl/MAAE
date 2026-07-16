"""MaaCore + 伪装设备 + 任务配置系统

用法:
  python main.py                  # 使用默认任务 (tasks/startup.json)
  python main.py daily            # 使用 daily.json 任务
  python main.py -t tasks/daily.json    # 指定完整路径
"""
import sys, time, subprocess, os, threading, logging, pathlib
from datetime import datetime
import argparse


# ── 配置 (按你的环境修改) ─────────────────────────────────
ADB_DIR = str(pathlib.Path(__file__).parent / "platform-tools")
MAA_DIR = r"C:\Users\Administrator\Downloads\neteasegame\MAA-v6.14.1-win-x64"
GAME_CODE = "mrfz"
CLOUD_URL = "https://cg.163.com"


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="MAA + 云游戏自动化")
    parser.add_argument(
        "task_name",
        nargs="?",
        default="startup",
        help="任务名称 (不带 .json), 例如: daily, startup",
    )
    parser.add_argument(
        "-t", "--task",
        dest="task_path",
        help="任务配置文件完整路径",
    )
    parser.add_argument(
        "--device-mode",
        choices=("placeholder", "realtime"),
        default="placeholder",
        help="Screenshot transport mode for the fake ADB device",
    )
    return parser.parse_args()


def find_task_file(task_name: str) -> pathlib.Path:
    """查找任务配置文件"""
    base_dir = pathlib.Path(__file__).parent
    tasks_dir = base_dir / "tasks"

    # 如果是完整路径，直接返回
    if pathlib.Path(task_name).exists():
        return pathlib.Path(task_name)

    # 先找 tasks/xxx.json
    if tasks_dir.exists():
        for ext in [".json", ".toml", ".yaml", ".yml"]:
            p = tasks_dir / (task_name + ext)
            if p.exists():
                return p

    # 直接当文件名找
    for ext in [".json", ".toml", ".yaml", ".yml"]:
        p = base_dir / (task_name + ext)
        if p.exists():
            return p

    return tasks_dir / (task_name + ".json")


def setup_logging():
    """设置日志"""
    log_dir = pathlib.Path(__file__).parent / "logs"
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


def main():
    from config.task import TaskConfig

    args = parse_args()
    log, log_file = setup_logging()

    # 加载任务配置
    if args.task_path:
        task_path = pathlib.Path(args.task_path)
    else:
        task_path = find_task_file(args.task_name)

    if task_path.exists():
        log.info(f"加载任务配置: {task_path}")
        task_config = TaskConfig.from_file(task_path)
    else:
        log.warning(f"任务配置不存在: {task_path}，使用默认启动任务")
        task_config = None

    browser = None
    asst = None

    try:
        # ── ADB setup ────────────────────────────────────────────
        ADB = os.path.join(ADB_DIR, "adb.exe")
        os.environ["PATH"] = ADB_DIR + ";" + os.environ.get("PATH", "")

        log.info("Starting ADB daemon...")
        subprocess.run([ADB, "start-server"], capture_output=True)
        time.sleep(1)

        # Start fake device on 5555
        if args.device_mode == "placeholder":
            from fake_device_placeholder import start, set_page, update_screencap, process_actions
        else:
            from fake_device import start, set_page, update_screencap, process_actions
        log.info(f"Fake device mode: {args.device_mode}")
        log.info("Starting fake device server on :5555...")
        threading.Thread(target=start, daemon=True).start()
        time.sleep(1)

        # Connect daemon to fake device
        r = subprocess.run([ADB, "connect", "127.0.0.1:5555"], capture_output=True, text=True)
        log.info(f"ADB connect: {r.stdout.strip()}")

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            profile_dir = pathlib.Path(__file__).parent / ".browser_profile"
            log.info(f"Browser profile: {profile_dir} (exists={profile_dir.exists()})")
            log.info("Launching browser...")
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                viewport={"width": 1280, "height": 720},
                device_scale_factor=1,
            )
            page = browser.new_page()
            set_page(page)
            try:
                log.info("Navigating to cg.163.com...")
                page.goto("https://cg.163.com", timeout=15000)
            except Exception as e:
                log.warning(f"Initial navigation timeout (may be ok): {e}")

            # 检测登录态
            logged = page.evaluate("() => !!localStorage.getItem('NCG-token')")
            if not logged:
                log.info("Please login in the browser...")
                for _ in range(120):
                    time.sleep(2)
                    if page.evaluate("() => !!localStorage.getItem('NCG-token')"):
                        log.info("Login detected!")
                        break

            log.info("Opening game (mrfz)...")
            page.goto(f"https://cg.163.com/run.html?code=mrfz&id={int(time.time()*1000)}&inline=1", timeout=30000)
            log.info(f"Game URL: {page.url[:100]}")
            log.info("Waiting for game stream to load...")
            time.sleep(10)
            log.info(f"After 10s URL: {page.url[:100]}")
            for _ in range(5):
                process_actions()
                update_screencap()
                time.sleep(0.3)

            # ── MaaCore ───────────────────────────────────────────
            sys.path.insert(0, str(pathlib.Path(__file__).parent))
            from asst import Asst
            from utils import InstanceOptionType
            log.info(f"Loading MaaCore from {MAA_DIR}...")
            Asst.load(MAA_DIR)
            asst = Asst()
            asst.set_instance_option(InstanceOptionType.touch_type, "adb")
            ok = asst.connect("adb", "127.0.0.1:5555")
            log.info(f"MaaCore connect: {ok} (page URL: {page.url[:100]})")

            if ok:
                # 添加任务
                if task_config and task_config.tasks:
                    log.info(f"添加 {len(task_config.tasks)} 个任务...")
                    for task in task_config.tasks:
                        log.info(f"  - {task.name or task.task_type}")
                        asst.append_task(task.task_type, task.params)
                else:
                    # 默认任务
                    log.info("使用默认启动任务...")
                    asst.append_task("StartUp", {"client_type": "Official", "start_game_enabled": False})

                asst.start()
                log.info(f"MAA task running... Ctrl+C to stop (page URL: {page.url[:100]})")
                last_screencap_at = 0.0
                while asst.running():
                    process_actions()
                    now = time.monotonic()
                    if now - last_screencap_at >= 0.1:
                        update_screencap()
                        last_screencap_at = now
                    # 检测是否被踢出游戏
                    if "run.html" not in page.url:
                        log.warning(f"Page navigated away from game! URL: {page.url[:100]}")
                    time.sleep(0.02)
                asst.stop()
                log.info("MAA task completed normally.")

            browser.close()
            browser = None
            log.info("Done!")

    except KeyboardInterrupt:
        log.info("⚠ Ctrl+C — shutting down...")
    except SystemExit as e:
        if e.code != 0:
            log.error(f"Exiting with code {e.code}")
    except Exception:
        log.exception("Unexpected error:")
    finally:
        # Cleanup
        try:
            if asst and asst.running():
                asst.stop()
                log.info("MAA task stopped (cleanup).")
        except Exception:
            pass
        try:
            if browser:
                browser.close()
                log.info("Browser closed (cleanup).")
        except Exception:
            pass
        logging.shutdown()


if __name__ == "__main__":
    main()
