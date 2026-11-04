# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

相对原版的改动：
  1. 补上窗口图标（仓库里的 favicon.ico 之前没用上）；
  2. 把 sv_ttk 的 .tcl 主题文件一起打包，否则打包后一启动就报
     "can't read sv.tcl"，深色主题失效；
  3. 显式声明 UPX 缺省可用性 —— 没装 UPX 时 PyInstaller 只会警告，不会失败。
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

# sv_ttk 用 __file__ 相对路径加载 .tcl，必须作为数据文件随包分发。
datas = collect_data_files("sv_ttk", includes=["**/*.tcl"])

a = Analysis(
    ["tools_box.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="tools_box",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,              # GUI 程序，不弹控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="favicon.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="tools_box",
)
