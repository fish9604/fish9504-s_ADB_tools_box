"""ADB 工具箱 — 单文件 tkinter GUI。

基于 https://github.com/fish9604/fish9504-s_ADB_tools_box 修订，主要修复：
  1. simpledialog 未导入导致"连接网络设备"必然抛 AttributeError；
  2. logcat 在 Tk 主线程里阻塞 readline，界面卡死；关闭窗口不结束进程；
  3. 设备列表把 adb 的 daemon 提示行当成设备，且忽略 unauthorized/offline；
  4. 下拉框切换设备不生效（self.device 永远停在第一个）；
  5. 安装 APK / 重启固定 10 秒超时，必然误报失败；
  6. 截图存到 os.getcwd()，打包后可能无权限，且失败仍提示成功；
  7. 未检查 adb 是否存在，缺 adb 时整个工具静默失效；
  8. adb 输出按 GBK 解码导致乱码；每次调用 adb 闪控制台黑框；
  9. `Bold.TEntry` 用在 Combobox 上不生效。
新增：无线调试配对（Android 11+）、明确的成功/失败弹窗、DPI 自适应。
"""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    import sv_ttk  # 现代主题库
except ImportError:  # 没装也能跑，只是界面朴素
    sv_ttk = None

APP_VERSION = "1.4"
# 打包成 windowed exe 后，每次 subprocess 都会闪一个控制台窗口，用它压掉。
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)



def app_base_dir() -> Path:
    """脚本目录；打包后为 PyInstaller 的解包目录。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def find_adb() -> str:
    """按 环境变量 → 程序目录 → PATH 的顺序找 adb。"""
    candidates = []
    env = os.environ.get("ADB_PATH")
    if env:
        candidates.append(env)
    base = app_base_dir()
    candidates += [
        str(base / "adb.exe"),
        str(base / "adb"),
        str(base / "platform-tools" / "adb.exe"),
        str(base / "platform-tools" / "adb"),
    ]
    for path in candidates:
        if Path(path).is_file():
            return path
    return shutil.which("adb") or "adb"


def split_command(text: str) -> list[str]:
    """按 shell 习惯切分命令，但不把反斜杠当转义（Windows 路径常见 C:\\new）。

    只处理成对的单/双引号：
        install -r "C:\\Program Files\\a b.apk"  ->  ['install', '-r', 'C:\\\\Program Files\\\\a b.apk']
    """
    tokens: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for ch in text:
        if quote:
            if ch == quote:
                quote = None
            else:
                current.append(ch)
        elif ch in "\"'":
            quote = ch
        elif ch.isspace():
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(ch)
    if current:
        tokens.append("".join(current))
    return tokens


def quote_arg(arg: str) -> str:
    """仅用于日志里还原可读的命令行。"""
    return f'"{arg}"' if (" " in arg or not arg) else arg


class ADBToolbox:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"ADB工具箱 v{APP_VERSION}")

        if sv_ttk is not None:
            sv_ttk.set_theme("dark")

        self.style = ttk.Style()
        self.configure_styles()

        # ADB 环境
        self.device: str | None = None
        self.adb_path = find_adb()
        self._device_map: dict[str, str] = {}
        self._logcat_procs: list[subprocess.Popen] = []

        self.create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if sv_ttk is None:
            self.log("提示：未安装 sv-ttk，已使用系统默认主题（pip install sv-ttk 可恢复深色界面）。")

        self.check_adb()
        self.refresh_devices()

    # ------------------------------------------------------------------ 样式
    def configure_styles(self):
        """配置全局加粗字体和主题样式。"""
        base_font = ("Microsoft YaHei", 10, "bold")

        self.style.configure("Bold.TLabel", font=base_font)
        self.style.configure("BoldHeader.TLabelframe.Label", font=base_font)
        self.style.configure("Bold.TButton", font=base_font, padding=6)
        self.style.configure("Bold.TEntry", font=base_font)
        # Combobox 的样式名是 TCombobox，原来写成 TEntry 不会生效
        self.style.configure("Bold.TCombobox", font=base_font)

    # ------------------------------------------------------------------ 界面
    def create_widgets(self):
        """构建 GUI 界面。"""
        # 设备管理区域
        device_frame = ttk.LabelFrame(
            self.root, text="设备管理", style="BoldHeader.TLabelframe"
        )
        device_frame.pack(padx=10, pady=5, fill=tk.X)

        self.device_combobox = ttk.Combobox(
            device_frame, style="Bold.TCombobox", state="readonly"
        )
        self.device_combobox.pack(
            side=tk.LEFT, padx=5, pady=2, expand=True, fill=tk.X
        )
        self.device_combobox.bind("<<ComboboxSelected>>", self.on_device_selected)

        ttk.Button(
            device_frame, text="刷新设备", command=self.refresh_devices,
            style="Bold.TButton",
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            device_frame, text="连接网络设备", command=self.connect_network_device,
            style="Bold.TButton",
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            device_frame, text="配对(安卓11+)", command=self.pair_device,
            style="Bold.TButton",
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            device_frame, text="断开设备", command=self.disconnect_device,
            style="Bold.TButton",
        ).pack(side=tk.LEFT, padx=5)

        # 常用功能区
        func_frame = ttk.LabelFrame(
            self.root, text="常用功能", style="BoldHeader.TLabelframe"
        )
        func_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        buttons = [
            ("安装APK", self.install_apk),
            ("屏幕截图", self.take_screenshot),
            ("酷安市场", self.open_coolapk),
            ("重启设备", self.reboot_device),
            ("进入Recovery", lambda: self.reboot_device("recovery")),
            ("查看日志", self.show_logcat),
        ]
        for i, (text, command) in enumerate(buttons):
            ttk.Button(
                func_frame, text=text, command=command, style="Bold.TButton"
            ).grid(row=i // 3, column=i % 3, padx=5, pady=2, sticky="ew")
        for col in range(3):
            func_frame.columnconfigure(col, weight=1)

        # 命令终端区
        cmd_frame = ttk.LabelFrame(
            self.root, text="adb 命令（不用写 adb 前缀）", style="BoldHeader.TLabelframe"
        )
        cmd_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        self.cmd_entry = ttk.Entry(cmd_frame, style="Bold.TEntry")
        self.cmd_entry.pack(fill=tk.X, padx=5, pady=2)
        self.cmd_entry.bind("<Return>", self.execute_custom_command)

        # 日志输出区
        log_frame = ttk.LabelFrame(
            self.root, text="输出日志", style="BoldHeader.TLabelframe"
        )
        log_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_frame, height=10, font=("Microsoft YaHei", 10, "bold"), wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    # -------------------------------------------------------------- 基础能力
    def log(self, message: str):
        """输出日志到文本框。"""
        self.log_text.insert(tk.END, message.rstrip("\n") + "\n")
        self.log_text.see(tk.END)

    def _run(self, args, *, timeout: float | None = 20, show_output: bool = True):
        """执行一条 adb 命令，返回 CompletedProcess；失败返回 None。

        args 可以是字符串（会按引号规则切分）或列表。全程 no shell，避免注入与引号问题。
        """
        if isinstance(args, str):
            args = split_command(args)
        cmd = [self.adb_path]
        if self.device:
            cmd += ["-s", self.device]
        cmd += list(args)
        display = "> " + " ".join(quote_arg(a) for a in cmd)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                creationflags=NO_WINDOW,
            )
        except FileNotFoundError:
            self.log(display)
            self.log("找不到 adb：请安装 Android platform-tools 并加入 PATH，"
                     "或把 adb.exe 放到本程序同目录，或设置环境变量 ADB_PATH。")
            return None
        except subprocess.TimeoutExpired:
            if show_output:
                self.log(display)
                self.log(f"命令超过 {timeout} 秒没有返回；它可能仍在设备上执行。")
            return None
        except OSError as exc:
            self.log(display)
            self.log(f"命令执行失败：{exc}")
            return None

        if show_output:
            body = display
            if proc.stdout:
                body += "\n" + proc.stdout.rstrip("\n")
            if proc.stderr and proc.stderr.strip():
                body += "\n" + proc.stderr.rstrip("\n")
            self.log(body)
        return proc

    def run_adb_command(self, command, show_output: bool = True, timeout=20):
        """执行 adb 命令并返回 stdout（保留原有方法名，便于外部调用）。"""
        proc = self._run(command, timeout=timeout, show_output=show_output)
        return proc.stdout if proc is not None else None

    def _require_device(self) -> bool:
        if self.device:
            return True
        messagebox.showwarning(
            "没有选择设备",
            "还没有可用设备。请用 USB 连接并打开「USB 调试」，"
            "或先用「配对」+「连接网络设备」建立无线连接。",
            parent=self.root,
        )
        return False

    def check_adb(self) -> bool:
        """启动时确认 adb 可用，缺了就明确告知，而不是静默失败。"""
        proc = self._run(["version"], timeout=10, show_output=False)
        if proc is None or proc.returncode != 0:
            self.log("警告：无法运行 adb，下面的操作都会失败。")
            messagebox.showwarning(
                "未找到 adb",
                "没有找到可用的 adb。\n\n"
                "解决办法（任选其一）：\n"
                "1. 安装 Google 的 Android platform-tools 并加入 PATH；\n"
                "2. 把 adb.exe 放到本程序所在目录；\n"
                "3. 设置环境变量 ADB_PATH 指向 adb.exe。",
                parent=self.root,
            )
            return False
        first_line = (proc.stdout or "").strip().splitlines()
        self.log(f"adb 路径：{self.adb_path}")
        if first_line:
            self.log(f"adb 版本：{first_line[0]}")
        return True

    # -------------------------------------------------------------- 设备管理
    def refresh_devices(self):
        """刷新设备列表，保留序列号与状态。"""
        proc = self._run(["devices"], timeout=15, show_output=False)
        if proc is None:
            return
        pairs: list[tuple[str, str]] = []
        for line in (proc.stdout or "").splitlines():
            parts = line.split("\t")
            # 只认 "序列号<TAB>状态"，这样 "* daemon started successfully *"
            # 和 "List of devices attached" 都不会被当成设备
            if len(parts) >= 2 and parts[1].strip():
                pairs.append((parts[0].strip(), parts[1].strip()))

        displays = []
        self._device_map = {}
        for serial, state in pairs:
            display = serial if state == "device" else f"{serial}  [{state}]"
            displays.append(display)
            self._device_map[display] = serial

        self.device_combobox["values"] = displays
        self.device = pairs[0][0] if pairs else None
        self.device_combobox.set(displays[0] if displays else "")

        if not pairs:
            self.log("没有检测到设备。请检查 USB 连接、USB 调试开关，或先连接网络设备。")
        elif any(state != "device" for _, state in pairs):
            self.log("注意：有设备处于 offline / unauthorized 状态，"
                     "需要在手机上点「允许 USB 调试」才能操作。")

    def on_device_selected(self, event=None):
        """下拉框换设备时同步 self.device，否则操作会一直发给第一个设备。"""
        display = self.device_combobox.get()
        self.device = self._device_map.get(display, display or None)
        if self.device:
            self.log(f"当前设备：{self.device}")

    def connect_network_device(self):
        """连接网络设备。"""
        ip = simpledialog.askstring(
            "连接设备",
            "输入设备IP地址和端口（例：192.168.1.100:5555）",
            parent=self.root,
        )
        if not ip:
            return
        proc = self._run(["connect", ip.strip()], timeout=30)
        self.refresh_devices()
        if proc is not None and "connected to" not in (proc.stdout or "").lower():
            messagebox.showwarning(
                "连接未成功",
                "adb 没有报告连接成功。\n\n"
                "如果是 Android 11+，请先在无线调试里「使用配对码配对设备」，"
                "点上面的「配对(安卓11+)」完成配对后再连接。",
                parent=self.root,
            )

    def pair_device(self):
        """Android 11+ 无线调试配对：adb pair 地址 配对码。"""
        address = simpledialog.askstring(
            "配对设备",
            "输入「无线调试」里显示的配对地址（例：192.168.1.100:37123）",
            parent=self.root,
        )
        if not address:
            return
        code = simpledialog.askstring(
            "配对设备", "输入手机屏幕上显示的 6 位配对码", parent=self.root
        )
        if not code:
            return

        saved_device, self.device = self.device, None  # 配对不需要 -s
        try:
            proc = self._run(["pair", address.strip(), code.strip()], timeout=30)
        finally:
            self.device = saved_device

        if proc is not None and "Successfully paired" in (proc.stdout or ""):
            messagebox.showinfo(
                "配对成功",
                "配对完成。接下来点「连接网络设备」，输入同一个地址"
                "（端口换成无线调试页面上显示的连接端口，通常是 5555）。",
                parent=self.root,
            )

    def disconnect_device(self):
        """断开设备连接。"""
        if not self.device:
            return
        # adb disconnect 只接受地址本身，不该再带 -s
        saved_device, self.device = self.device, None
        try:
            self._run(["disconnect", saved_device], timeout=15)
        finally:
            self.device = saved_device
        self.refresh_devices()

    # -------------------------------------------------------------- 常用功能
    def install_apk(self):
        """安装 APK 文件。"""
        if not self._require_device():
            return
        apk_path = filedialog.askopenfilename(
            title="选择APK文件", filetypes=[("APK文件", "*.apk")]
        )
        if not apk_path:
            return
        # 安装大包经常超过 10 秒，给足时间；超时也别谎报失败
        proc = self._run(["install", "-r", apk_path], timeout=600)
        if proc is None:
            messagebox.showerror("安装未完成", "adb 没有返回结果，详见日志。", parent=self.root)
            return
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0 and "Success" in output:
            messagebox.showinfo("安装成功", Path(apk_path).name, parent=self.root)
        else:
            messagebox.showwarning(
                "安装失败", output.strip()[-800:] or "adb 没有给出原因", parent=self.root
            )

    def take_screenshot(self):
        """截取设备屏幕，保存到 图片/ADB工具箱。"""
        if not self._require_device():
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        remote_path = f"/data/local/tmp/screenshot_{stamp}.png"
        # 不再用 os.getcwd()：从快捷方式启动时它可能是 System32
        out_dir = Path.home() / "Pictures" / "ADB工具箱"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            out_dir = Path(os.environ.get("TEMP") or str(Path.home()))

        local_path = out_dir / f"screenshot_{stamp}.png"
        if self._run(["shell", "screencap", "-p", remote_path], timeout=30) is None:
            return
        proc = self._run(["pull", remote_path, str(local_path)], timeout=60)
        # 顺手清掉设备上的临时文件，避免 /data/local/tmp 越积越多
        self._run(["shell", "rm", "-f", remote_path], timeout=10, show_output=False)

        if proc is None or not local_path.is_file() or local_path.stat().st_size == 0:
            self.log("截图失败：本地文件没有生成。")
            messagebox.showerror("截图失败", "没有拿到截图文件，详见日志。", parent=self.root)
            return
        self.log(f"截图已保存：{local_path}")
        messagebox.showinfo("截图成功", f"已保存到\n{local_path}", parent=self.root)

    def open_coolapk(self):
        """在浏览器打开酷安市场。"""
        try:
            webbrowser.open("https://www.coolapk.com/apk")
            self.log("已打开酷安应用市场")
        except Exception as exc:
            self.log(f"打开浏览器失败: {exc}")

    def reboot_device(self, target: str = ""):
        """重启设备；target 为 "recovery" 时进入 Recovery。"""
        args = ["reboot"] + ([target] if target else [])
        # reboot 会立刻断开连接，等不到正常返回是常态，不当作失败
        self._run(args, timeout=5, show_output=False)
        where = "Recovery" if target == "recovery" else "系统"
        self.log(f"已发送重启命令（{where}），设备正在重启…")

    def show_logcat(self):
        """在独立窗口显示实时日志（后台线程读取，不阻塞界面）。"""
        if not self._require_device():
            return

        log_window = tk.Toplevel(self.root)
        log_window.title(f"实时日志 - {self.device}")
        text = tk.Text(log_window, font=("Microsoft YaHei", 9), wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True)

        self._run(["logcat", "-c"], timeout=15, show_output=False)  # 先清缓冲

        cmd = [self.adb_path, "-s", self.device, "logcat"]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                creationflags=NO_WINDOW,
            )
        except OSError as exc:
            self.log(f"无法启动 logcat：{exc}")
            log_window.destroy()
            return
        self._logcat_procs.append(proc)

        lines: queue.Queue[str | None] = queue.Queue()

        def reader():
            # 阻塞读放在后台线程，界面线程只做刷新
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)

        threading.Thread(target=reader, daemon=True).start()

        def poll():
            if not log_window.winfo_exists():   # 窗口已关，停止刷新
                return
            try:
                while True:
                    line = lines.get_nowait()
                    if line is None:
                        text.insert(tk.END, "\n--- logcat 已结束 ---\n")
                        text.see(tk.END)
                        return
                    text.insert(tk.END, line)
                    text.see(tk.END)
            except queue.Empty:
                pass
            log_window.after(100, poll)

        def close():
            if proc.poll() is None:
                proc.kill()
            if proc in self._logcat_procs:
                self._logcat_procs.remove(proc)
            log_window.destroy()

        log_window.protocol("WM_DELETE_WINDOW", close)
        poll()

    def execute_custom_command(self, event=None):
        """执行自定义 adb 命令（无需输入 adb 前缀）。"""
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return
        self._run(cmd, timeout=60)
        self.cmd_entry.delete(0, tk.END)

    # ------------------------------------------------------------------ 退出
    def on_close(self):
        """关闭主窗口前结束所有 logcat 进程，避免后台残留。"""
        for proc in list(self._logcat_procs):
            if proc.poll() is None:
                proc.kill()
        self._logcat_procs.clear()
        self.root.destroy()


def main() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 高分屏字体不发虚
        except Exception:
            pass

    root = tk.Tk()
    root.geometry("820x620")
    root.minsize(720, 520)

    icon = app_base_dir() / "favicon.ico"
    if icon.is_file():
        try:
            root.iconbitmap(str(icon))
        except tk.TclError:
            pass

    ADBToolbox(root)
    root.mainloop()


if __name__ == "__main__":
    main()
