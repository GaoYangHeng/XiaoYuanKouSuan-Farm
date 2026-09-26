# -*- coding: utf-8 -*-
# 写入启动文件夹实现开机自启（无需管理员权限）
# 用法: python install_autostart.py [--uninstall]
import os
import subprocess
import sys

APP = "xyks-farm"
HERE = os.path.dirname(os.path.abspath(__file__))
PYW = sys.executable.replace("python.exe", "pythonw.exe")
ENTRY = os.path.join(HERE, "farm_daemon.pyw")
LNK = os.path.join(os.environ.get("APPDATA", ""),
                   "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
                   APP + ".lnk")


def install():
    script = ("$ws=New-Object -ComObject WScript.Shell;"
              f"$s=$ws.CreateShortcut('{LNK}');"
              f"$s.TargetPath='{PYW}';"
              f"$s.Arguments='\"{ENTRY}\"';"
              f"$s.WorkingDirectory='{HERE}';"
              "$s.Save()")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print("installed" if (r.returncode == 0 and os.path.exists(LNK)) else "failed: " + r.stderr.decode(errors="replace"))


def uninstall():
    if os.path.exists(LNK):
        os.remove(LNK)
        print("removed")
    else:
        print("not installed")


if __name__ == "__main__":
    uninstall() if "--uninstall" in sys.argv else install()
