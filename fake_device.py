"""伪装 ADB 设备——监听 5555，真 adb daemon 连过来。"""
import socket, struct, threading, time, queue, logging

_log = logging.getLogger("fake_device")

PORT = 5555
DISPLAY_WIDTH = 1280
DISPLAY_HEIGHT = 720
A_CNXN, A_OPEN, A_OKAY, A_WRTE, A_CLSE = 0x4E584E43, 0x4E45504F, 0x59414B4F, 0x45545257, 0x45534C43
A_VERSION, A_MAXDATA = 0x01000001, 1024 * 1024

_page = None
_action_queue = queue.Queue()  # ADB 线程 → 主线程的触摸事件队列


def set_page(p):
    global _page
    _page = p


def adb_header(cmd, arg0, arg1, data):
    csum = sum(data) & 0xFFFFFFFF
    return struct.pack("<6I", cmd, arg0, arg1, len(data), csum, cmd ^ 0xFFFFFFFF) + data


def handle(conn, addr):
    _log.info(f"[device] connected: {addr}")
    buf = b""
    try:
        while True:
            data = conn.recv(4096)
            if not data: break
            buf += data
            while len(buf) >= 24:
                cmd, arg0, arg1, plen, magic, cs = struct.unpack("<6I", buf[:24])
                total = 24 + plen
                if len(buf) < total: break
                payload = buf[24:total]
                buf = buf[total:]

                if cmd == A_CNXN:
                    # ro.adb.secure=0 skips AUTH
                    banner = b"device::ro.product.name=cloud;ro.adb.secure=0;ro.product.model=Playwright;ro.product.device=cloud;"
                    conn.sendall(adb_header(A_CNXN, A_VERSION, A_MAXDATA, banner))
                    _log.info("[device] CNXN sent")

                elif cmd == A_OPEN:
                    dest = payload.decode().rstrip("\0")
                    remote_id = arg0   # client's local_id = remote from our perspective
                    our_id = (arg0 % 65535) + 1  # unique server local_id per stream
                    _log.info(f"[device] OPEN {dest[:80]} remote={remote_id}")

                    if "shell:" in dest or "exec-out:" in dest or "exec:" in dest:
                        cmd_text = dest.split(":", 1)[1] if ":" in dest else ""
                        result = _exec(cmd_text)
                        # 确保永远不返回空数据——否则 ADB daemon 会 RST
                        if result is None or len(result) == 0:
                            _log.info(f"[device] ⚠ result empty for '{cmd_text[:60]}', forcing newline")
                            result = b"\n"
                        conn.sendall(adb_header(A_OKAY, our_id, remote_id, b""))
                        # 分片发送：ADB 协议单条 WRTE 不能超过 A_MAXDATA (1MB)
                        MAX_CHUNK = 512 * 1024  # 512KB per chunk, well under 1MB limit
                        offset = 0
                        while offset < len(result):
                            chunk = result[offset:offset + MAX_CHUNK]
                            conn.sendall(adb_header(A_WRTE, our_id, remote_id, chunk))
                            offset += len(chunk)
                        conn.sendall(adb_header(A_CLSE, our_id, remote_id, struct.pack("<I", 0)))
                    else:
                        conn.sendall(adb_header(A_OKAY, our_id, remote_id, b""))
                        conn.sendall(adb_header(A_CLSE, our_id, remote_id, b""))

                elif cmd == A_WRTE:
                    pass
                elif cmd == A_CLSE:
                    pass
    except (ConnectionResetError, BrokenPipeError, OSError) as e:
        _log.info(f"[device] disconnected: {e}")
    finally:
        try:
            conn.close()
        except:
            pass


def _exec(cmd):
    _log.info(f"[exec] {cmd[:100]}")
    parts = cmd.split()
    if not parts: return b"\n"
    if "screencap" in parts[0]:
        return _screencap()
    if parts[0] == "input" and len(parts) >= 3:
        if parts[1] == "tap":
            _action_queue.put(("tap", int(parts[2]), int(parts[3])))
        elif parts[1] == "swipe" and len(parts) >= 6:
            x1, y1, x2, y2 = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
            dur = int(parts[6]) if len(parts) > 6 else 200
            _action_queue.put(("swipe", x1, y1, x2, y2, dur))
        return b"\n"
    if "echo" in cmd:
        return (" ".join(parts[1:]) + "\n").encode()
    if "settings" in cmd:
        if "android_id" in cmd: return b"0123456789abcdef\n"
        return b"\n"
    if "wm" in cmd:
        # MAA display command pipes: wm size | tail -n 1 | grep -o -E [0-9]+
        return f"{DISPLAY_WIDTH}\n{DISPLAY_HEIGHT}\n".encode()
    if "getprop" in cmd:
        if "release" in cmd: return b"11\n"
        if "sdk" in cmd: return b"30\n"
        if "cpu" in cmd: return b"x86_64\n"
        return b"\n"
    if "pm" in cmd and "path" in cmd:
        return b"package:/data/app/arknights/base.apk\n"
    if "dumpsys" in cmd or "cat" in cmd or "ls" in cmd or "pm" in cmd or "am" in cmd:
        return b"\n"
    if "chmod" in cmd or "push" in cmd or "mkdir" in cmd or "rm" in cmd:
        return b"\n"
    return b"\n"


_cached_screencap = None
_screencap_lock = threading.Lock()


def process_actions():
    """主线程每帧调用，执行 ADB 线程排队的触摸事件。swipe 在后台线程执行不阻塞。"""
    while True:
        try:
            action = _action_queue.get_nowait()
        except queue.Empty:
            break
        if not _page:
            continue
        try:
            if action[0] == "tap":
                _, x, y = action
                _page.mouse.click(x, y)
                _log.info(f"[action] tap {x} {y}")
            elif action[0] == "swipe":
                _, x1, y1, x2, y2, dur = action
                # 云游戏环境下超过 500ms 的 swipe 不生效，截断
                dur = min(dur, 500)
                threading.Thread(target=_do_swipe, args=(x1, y1, x2, y2, dur), daemon=True).start()
                _log.info(f"[action] swipe {x1},{y1} → {x2},{y2} dur={dur}")
        except Exception as e:
            _log.info(f"[action] error: {e}")


def _do_swipe(x1, y1, x2, y2, dur):
    """在后台线程执行 swipe，不阻塞主线程的截屏循环。"""
    try:
        steps = max(10, dur // 8)
        step_delay = dur / 1000 / steps
        _page.mouse.move(x1, y1)
        _page.mouse.down()
        for i in range(1, steps + 1):
            t = i / steps
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            _page.mouse.move(x, y)
            time.sleep(step_delay)
        _page.mouse.up()
        _log.info(f"[swipe] done: {x1},{y1} → {x2},{y2} dur={dur}ms steps={steps}")
    except Exception as e:
        _log.info(f"[swipe] error: {e}")


def update_screencap():
    """主线程调用，缓存截图供 ADB 回调线程使用。"""
    global _cached_screencap
    if _page:
        png = None
        try:
            for sel in ("canvas", "video", "#app canvas", "#app video"):
                try:
                    el = _page.wait_for_selector(sel, timeout=500, state="attached")
                    if el:
                        png = el.screenshot(type="png")
                        break
                except: continue
            if png is None:
                png = _page.screenshot(type="png")
        except Exception as e:
            _log.info(f"[screencap] error: {e}")
        if png:
            with _screencap_lock:
                _cached_screencap = png


def _screencap():
    """每次直接返回真实缓存的截图。"""
    with _screencap_lock:
        data = _cached_screencap
    if data:
        _log.info(f"[screencap] real: {len(data)} bytes")
        return data
    # 缓存还没就绪（启动瞬间），返回占位图
    try:
        with open(r"C:\Users\Administrator\Downloads\neteasegame\netease-cloudgame-reverse\output\after_clicks.png", "rb") as f:
            return f.read()
    except:
        return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x07\x80\x00\x00\x048\x08\x02\x00\x00\x00\x8e\x1b\xf6\xcc\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x11\x00\x01\xc8\x89\xe8\x1f\x00\x00\x00\x00IEND\xaeB`\x82"


def start():
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", PORT))
    s.listen(5)
    _log.info(f"[device] listening on {PORT}")
    while True:
        try:
            c, a = s.accept()
            threading.Thread(target=handle, args=(c, a), daemon=True).start()
        except: break
