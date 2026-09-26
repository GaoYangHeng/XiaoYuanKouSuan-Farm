# -*- coding: utf-8 -*-
# 魔搭 Studio 入口（studio-launcher 执行，cwd=仓库挂载点）
# 职责：后台启动 farm → 前台状态页（7860，兼作平台健康检查端口）
import datetime
import http.server
import os
import subprocess
import sys

PROJ = os.path.dirname(os.path.abspath(__file__))
XYKS = os.path.join(PROJ, "xyks")
CRACK = os.path.join(XYKS, "crack_sign")


def boot_farm():
    """后台启动刷分循环；日志同时写文件供状态页展示"""
    log = open(os.path.join(XYKS, "farm_stdout.log"), "a", buffering=1)
    p = subprocess.Popen(
        [sys.executable, "-u", os.path.join(CRACK, "farm_solo.py"), "10000"],
        cwd=CRACK, stdout=log, stderr=log,
    )
    print("[boot] farm started pid=%d" % p.pid)


class StatusHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        tail = []
        for p in (os.path.join(XYKS, "farm_stdout.log"),
                  os.path.join(CRACK, "farm_solo.jsonl")):
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()[-50:]
                tail.append("== %s ==" % os.path.basename(p))
                tail.extend(lines)
            except Exception:
                tail.append("== %s == (无)" % os.path.basename(p))
        body = ("<html><head><meta charset='utf-8'><title>xyks-farm</title></head>"
                "<body style='font-family:monospace;background:#111;color:#0f0;padding:16px'>"
                "<h3>xyks-farm " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") +
                "</h3><pre>" + "\n".join(tail) +
                "</pre></body></html>").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print("[boot] proj=%s" % PROJ)
    boot_farm()
    http.server.ThreadingHTTPServer(("0.0.0.0", 7860), StatusHandler).serve_forever()
