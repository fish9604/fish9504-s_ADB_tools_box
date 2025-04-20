import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
from datetime import datetime
import webbrowser
import sv_ttk  # 现代化主题库


class ADBToolbox:
    def __init__(self, root):
        self.root = root
        self.root.title("ADB工具箱 v1.3")
        sv_ttk.set_theme("dark")  # 默认深色主题（可选 "light"）

        # 初始化样式系统
        self.style = ttk.Style()
        self.configure_styles()  # 配置加粗字体和主题

        # ADB 环境变量
        self.device = None
        self.adb_path = "adb"

        # 构建界面
        self.create_widgets()
        self.refresh_devices()

    def configure_styles(self):
        """配置全局加粗字体和主题样式"""
        base_font = ('Microsoft YaHei', 10, 'bold')  # 加粗字体

        # 标题加粗样式
        self.style.configure("Bold.TLabel", font=base_font)
        self.style.configure("BoldHeader.TLabelframe.Label", font=base_font)

        # 按钮加粗样式
        self.style.configure(
            "Bold.TButton",
            font=base_font,
            padding=6  # 增加按钮内边距
        )

        # 输入框加粗样式
        self.style.configure("Bold.TEntry", font=base_font)

    def create_widgets(self):
        """构建GUI界面"""
        # 设备管理区域
        device_frame = ttk.LabelFrame(
            self.root,
            text="设备管理",
            style="BoldHeader.TLabelframe"
        )
        device_frame.pack(padx=10, pady=5, fill=tk.X)

        self.device_combobox = ttk.Combobox(device_frame, style="Bold.TEntry")
        self.device_combobox.pack(side=tk.LEFT, padx=5, pady=2, expand=True, fill=tk.X)

        ttk.Button(
            device_frame,
            text="刷新设备",
            command=self.refresh_devices,
            style="Bold.TButton"
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            device_frame,
            text="连接网络设备",
            command=self.connect_network_device,
            style="Bold.TButton"
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            device_frame,
            text="断开设备",
            command=self.disconnect_device,
            style="Bold.TButton"
        ).pack(side=tk.LEFT, padx=5)

        # 常用功能区
        func_frame = ttk.LabelFrame(
            self.root,
            text="常用功能",
            style="BoldHeader.TLabelframe"
        )
        func_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        buttons = [
            ("安装APK", self.install_apk),
            ("屏幕截图", self.take_screenshot),
            ("酷安市场", self.open_coolapk),
            ("重启设备", lambda: self.run_adb_command("reboot")),
            ("进入Recovery", lambda: self.run_adb_command("reboot recovery")),
            ("查看日志", self.show_logcat)
        ]

        for i, (text, command) in enumerate(buttons):
            ttk.Button(
                func_frame,
                text=text,
                command=command,
                style="Bold.TButton"
            ).grid(row=i // 3, column=i % 3, padx=5, pady=2, sticky="ew")

        # 命令终端区
        cmd_frame = ttk.LabelFrame(
            self.root,
            text="终端命令",
            style="BoldHeader.TLabelframe"
        )
        cmd_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        self.cmd_entry = ttk.Entry(cmd_frame, style="Bold.TEntry")
        self.cmd_entry.pack(fill=tk.X, padx=5, pady=2)
        self.cmd_entry.bind("<Return>", self.execute_custom_command)

        # 日志输出区
        log_frame = ttk.LabelFrame(
            self.root,
            text="输出日志",
            style="BoldHeader.TLabelframe"
        )
        log_frame.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_frame,
            height=10,
            font=('Microsoft YaHei', 10, 'bold')  # 原生组件直接加粗
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    # --------------------------
    # ADB 功能方法（保持不变）
    # --------------------------
    def run_adb_command(self, command, show_output=True):
        """执行ADB命令并返回输出"""
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
        """输出日志到文本框"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def refresh_devices(self):
        """刷新设备列表"""
        output = self.run_adb_command("devices", show_output=False)
        if output:
            devices = [line.split("\t")[0] for line in output.splitlines()[1:] if line.strip()]
            self.device_combobox["values"] = devices
            self.device = devices[0] if devices else None
            self.device_combobox.set(self.device if devices else "")

    def connect_network_device(self):
        """连接网络设备"""
        ip = tk.simpledialog.askstring("连接设备", "输入设备IP地址和端口（例：192.168.1.100:5555）")
        if ip:
            self.run_adb_command(f"connect {ip}")
            self.refresh_devices()

    def disconnect_device(self):
        """断开设备连接"""
        if self.device:
            self.run_adb_command(f"disconnect {self.device}")
            self.refresh_devices()

    def install_apk(self):
        """安装APK文件"""
        apk_path = filedialog.askopenfilename(title="选择APK文件", filetypes=[("APK文件", "*.apk")])
        if apk_path:
            self.run_adb_command(f"install -r \"{apk_path}\"")

    def take_screenshot(self):
        """截取设备屏幕"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        remote_path = f"/sdcard/screenshot_{timestamp}.png"
        local_path = os.path.join(os.getcwd(), f"screenshot_{timestamp}.png")

        self.run_adb_command(f"shell screencap -p {remote_path}")
        self.run_adb_command(f"pull {remote_path} \"{local_path}\"")
        self.log(f"截图已保存到：{local_path}")

    def open_coolapk(self):
        """在浏览器打开酷安市场"""
        try:
            webbrowser.open("https://www.coolapk.com/apk")
            self.log("已打开酷安应用市场")
        except Exception as e:
            self.log(f"打开浏览器失败: {str(e)}")

    def show_logcat(self):
        """显示实时日志"""
        log_window = tk.Toplevel(self.root)
        log_window.title("实时日志")

        text = tk.Text(log_window, font=('Microsoft YaHei', 9), wrap=tk.WORD)
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
        """执行自定义命令"""
        cmd = self.cmd_entry.get()
        if cmd:
            self.run_adb_command(cmd)
            self.cmd_entry.delete(0, tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("800x600")
    app = ADBToolbox(root)
    root.mainloop()