"""网易云游戏浏览器会话管理。"""

import logging
import pathlib
import time


class CloudGameBrowser:
    """负责启动、登录和关闭云游戏浏览器。"""

    def __init__(
        self,
        profile_dir: pathlib.Path,
        game_code: str,
        cloud_url: str,
        log: logging.Logger,
    ):
        self._profile_dir = profile_dir
        self._game_code = game_code
        self._cloud_url = cloud_url
        self._log = log
        self._playwright = None
        self.context = None
        self.page = None

    def launch(self):
        """启动浏览器、等待登录并进入云游戏页面。"""
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._log.info(f"浏览器配置目录: {self._profile_dir} (exists={self._profile_dir.exists()})")
        self._log.info("正在启动浏览器...")
        self.context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self._profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 720},
            device_scale_factor=1,
        )
        self.page = self.context.new_page()

        try:
            self._log.info("正在访问网易云游戏...")
            self.page.goto(self._cloud_url, timeout=15000)
        except Exception as exc:
            self._log.warning(f"初始页面访问超时，可继续等待: {exc}")

        self._wait_for_login()
        self._open_game()
        return self.page

    def close(self):
        """关闭浏览器上下文和 Playwright 进程。"""
        try:
            if self.context:
                self.context.close()
                self.context = None
        finally:
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
            self.page = None

    def _wait_for_login(self):
        """在登录信息不存在时等待用户完成登录。"""
        logged_in = self.page.evaluate("() => !!localStorage.getItem('NCG-token')")
        if logged_in:
            return

        self._log.info("请在浏览器中完成登录...")
        for _ in range(120):
            time.sleep(2)
            if self.page.evaluate("() => !!localStorage.getItem('NCG-token')"):
                self._log.info("已检测到登录状态。")
                return

        self._log.warning("等待登录超时，继续尝试打开云游戏。")

    def _open_game(self):
        """打开指定的云游戏并等待画面加载。"""
        self._log.info(f"正在打开游戏: {self._game_code}")
        game_url = f"{self._cloud_url}/run.html?code={self._game_code}&id={int(time.time() * 1000)}&inline=1"
        self.page.goto(game_url, timeout=30000)
        self._log.info(f"游戏页面地址: {self.page.url[:100]}")
        self._log.info("等待云游戏画面加载...")
        time.sleep(10)
        self._log.info(f"加载后页面地址: {self.page.url[:100]}")
