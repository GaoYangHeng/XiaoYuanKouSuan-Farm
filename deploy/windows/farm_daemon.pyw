# -*- coding: utf-8 -*-
# farm_daemon.pyw — 本机常驻刷分入口（pythonw 无窗口运行）
# 修复 pythonw 下 sys.stdout/stderr 为 None 导致 print 崩溃：先重定向到日志文件
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
_log = open(os.path.join(_REPO, "farm_daemon.log"), "a", buffering=1, encoding="utf-8")
sys.stdout = _log
sys.stderr = _log

sys.path.insert(0, os.path.join(_REPO, "xyks", "crack_sign"))

if __name__ == "__main__":
    import farm_solo
    print("[daemon] farm_daemon.pyw 启动 pid=%d" % os.getpid(), flush=True)
    farm_solo.main()
