import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
from datetime import datetime
import webbrowser  # 新增浏览器支持模块


class ADBToolbox:
    def __init__(self, root):
        self.root = root
        self.root.title("ADB工具箱 v1.1")  # 更新版本号

        # 初始化变量
        self.device = None
        self.adb_path = "adb"

        # 创建界面
        self.create_widgets()
        self.refresh_devices()

    def create_widgets(self):
        # 设备选择区
        device_frame = ttk.LabelFrame(self.root, text="设备管理")
        device_frame.pack(padx=10, pady=5, fill=tk.X)

        self.device_combobox = ttk.Combobox(device_frame)
        self.device_combobox.pack(side=tk.LEFT, padx=5, pady=2, fill=tk.X, expand=True)

        ttk.Button(device_frame, text="刷新设备", command=self.refresh_devices).pack(side=tk.LEFT, padx=5)
        ttk.Button(device_frame, text="连接网络设备", command=self.connect_network_device).pack(side=tk.LEFT, padx=5)
        ttk.Button(device_frame, text="断开设备", command=self.disconnect_device).pack(side=tk.LEFT, padx=5)

        # 常用功能区
        func_frame = ttk.LabelFrame(self.root, text="常用功能")
        func_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        buttons = [
            ("安装APK", self.install_apk),
            ("屏幕截图", self.take_screenshot),
            ("酷安市场", self.open_coolapk),  # 修改按钮名称和功能
            ("重启设备", lambda: self.run_adb_command("reboot")),
            ("进入Recovery", lambda: self.run_adb_command("reboot recovery")),
            ("查看日志", self.show_logcat)
        ]

        for i, (text, command) in enumerate(buttons):
            ttk.Button(func_frame, text=text, command=command).grid(
                row=i // 3, column=i % 3, padx=5, pady=2, sticky="ew")

        # 命令终端区
        cmd_frame = ttk.LabelFrame(self.root, text="终端命令")
        cmd_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        self.cmd_entry = ttk.Entry(cmd_frame)
        self.cmd_entry.pack(fill=tk.X, padx=5, pady=2)
        self.cmd_entry.bind("<Return>", self.execute_custom_command)

        # 日志输出区
        log_frame = ttk.LabelFrame(self.root, text="输出日志")
        log_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def run_adb_command(self, command, show_output=True):
        try:
            full_cmd = f"{self.adb_path} -s {self.device} {command}" if self.device else f"{self.adb_path} {command}"
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            output = f"> {full_cmd}\n{result.stdout}"
            if result.stderr:
                output += f"\nError:\n{result.stderr}"
            if show_output:
                self.log(output)
            return result.stdout
        except Exception as e:
            self.log(f"命令执行失败: {str(e)}")
            return None

    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def refresh_devices(self):
        output = self.run_adb_command("devices", show_output=False)
        if output:
            devices = [line.split("\t")[0] for line in output.splitlines()[1:] if line.strip()]
            self.device_combobox["values"] = devices
            if devices:
                self.device = devices[0]
                self.device_combobox.set(self.device)
            else:
                self.device = None

    def connect_network_device(self):
        ip = tk.simpledialog.askstring("连接设备", "输入设备IP地址和端口（例：192.168.1.100:5555）")
        if ip:
            self.run_adb_command(f"connect {ip}")
            self.refresh_devices()

    def disconnect_device(self):
        if self.device:
            self.run_adb_command(f"disconnect {self.device}")
            self.refresh_devices()

    def install_apk(self):
        apk_path = filedialog.askopenfilename(title="选择APK文件", filetypes=[("APK文件", "*.apk")])
        if apk_path:
            self.run_adb_command(f"install -r \"{apk_path}\"")

    def take_screenshot(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        remote_path = f"/sdcard/screenshot_{timestamp}.png"
        local_path = os.path.join(os.getcwd(), f"screenshot_{timestamp}.png")

        self.run_adb_command(f"shell screencap -p {remote_path}")
        self.run_adb_command(f"pull {remote_path} \"{local_path}\"")
        self.log(f"截图已保存到：{local_path}")

    def open_coolapk(self):  # 修改后的功能方法
        """在电脑浏览器打开酷安市场"""
        try:
            webbrowser.open('https://www.coolapk.com/apk')
            self.log("已打开酷安应用市场页面")
        except Exception as e:
            self.log(f"打开浏览器失败: {str(e)}")

    def show_logcat(self):
        log_window = tk.Toplevel(self.root)
        log_window.title("实时日志")

        text = tk.Text(log_window, wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True)

        process = subprocess.Popen(
            f"{self.adb_path} logcat -c && {self.adb_path} logcat",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        def update_log():
            line = process.stdout.readline()
            if line:
                text.insert(tk.END, line)
                text.see(tk.END)
                text.after(100, update_log)
            else:
                process.kill()

        update_log()

    def execute_custom_command(self, event=None):
        cmd = self.cmd_entry.get()
        if cmd:
            self.run_adb_command(cmd)
            self.cmd_entry.delete(0, tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("800x600")
    app = ADBToolbox(root)
    root.mainloop()