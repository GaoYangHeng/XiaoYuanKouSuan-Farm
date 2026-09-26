# -*- coding: utf-8 -*-
# 状态页：GET / 返回最近日志 + 分数（兼作平台/监控的访问保活目标）
import http.server
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = [
    os.path.join(HERE, "farm_stdout.log"),
    os.path.join(HERE, "crack_sign", "farm_solo.jsonl"),
]


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        tail = []
        for p in LOGS:
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()[-40:]
                tail.append("== %s ==" % os.path.basename(p))
                tail.extend(lines)
            except Exception as e:
                tail.append("== %s == (无)" % os.path.basename(p))
        body = ("<html><head><meta charset='utf-8'><title>xyks-farm</title></head>"
                "<body style='font-family:monospace;background:#111;color:#0f0;padding:16px'>"
                "<h3>xyks-farm 状态 " + __import__("datetime").datetime.now().strftime("%H:%M:%S") +
                "</h3><pre>" + "\n".join(tail) +
                "</pre></body></html>").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("0.0.0.0", 8080), H).serve_forever()
