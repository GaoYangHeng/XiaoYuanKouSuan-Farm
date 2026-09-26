# -*- coding: utf-8 -*-
"""xyks_ai.py — 给 AI Agent 用的操作接口（全 JSON 输出）

用法:
  python xyks_ai.py status              进程/分数/节奏/健康 一览
  python xyks_ai.py score               仅查周荣誉分
  python xyks_ai.py round [--once]      手动跑一局（含逐步耗时）
  python xyks_ai.py logs [--tail N]     最近日志
  python xyks_ai.py diagnose            自动诊断 + 处理建议
  python xyks_ai.py start               启动本机常驻 farm（pythonw 无窗口）
  python xyks_ai.py stop                停止本机常驻 farm

输出: 每个命令向 stdout 打印恰好一个 JSON 对象
  {"ok": bool, "cmd": str, "data": {...}, "error": str|null, "advice": str|null}
退出码: 0=成功  1=失败  2=需要人工处理（仅 diagnose 使用）
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CRACK = os.path.join(HERE, "xyks", "crack_sign")
JSONL = os.path.join(CRACK, "farm_solo.jsonl")
STDOUT_LOG = os.path.join(HERE, "farm_stdout.log")
PID_FILE = os.path.join(HERE, "farm.pid")
PYTHONW = sys.executable.replace("python.exe", "pythonw.exe")

sys.path.insert(0, CRACK)
sys.path.insert(0, os.path.join(HERE, "xyks", "mod_apk", "work"))


def emit(cmd, ok, data=None, error=None, advice=None, code=0):
    print(json.dumps({"ok": ok, "cmd": cmd, "data": data or {},
                      "error": error, "advice": advice}, ensure_ascii=False))
    sys.exit(code)


def load_cookie():
    p = os.path.join(CRACK, "login136.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f).get("cookie")


def read_tail(path, n):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()[-n:]
    except OSError:
        return []


def parse_jsonl(n=200):
    out = []
    for ln in read_tail(JSONL, n):
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out


def farm_pid():
    """返回本机常驻 farm 的 PID（通过 pid 文件 + 命令行校验）"""
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return None
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if not h:
            return None
        ctypes.windll.kernel32.CloseHandle(h)
        return pid
    except Exception:
        return pid


def pace_stats(entries):
    """最近成功局的间隔统计"""
    wins = [e for e in entries if e.get("win")]
    ts = []
    for e in wins[-10:]:
        t = e.get("ts")
        if not t:
            continue
        d = datetime.strptime(t, "%H:%M:%S")
        ts.append(d.hour * 3600 + d.minute * 60 + d.second)
    diffs = [b - a for a, b in zip(ts, ts[1:]) if b > a]
    if not diffs:
        return None
    avg = sum(diffs) / len(diffs)
    return {"avg_interval_sec": round(avg, 1),
            "tier": "fast(<120s)" if avg < 120 else "quota(~10min)"}


def cmd_status(a):
    ck = load_cookie()
    data = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cookie_present": bool(ck),
            "farm_pid": farm_pid(),
            "jsonl_exists": os.path.exists(JSONL)}
    entries = parse_jsonl()
    data["recent"] = entries[-3:]
    data["pace"] = pace_stats(entries)
    advice = None
    if not ck:
        advice = "缺 cookie：先跑 login136.py（XYKS_PHONE/XYKS_SMS_CODE 环境变量）"
    elif not data["farm_pid"]:
        advice = "本机 farm 未运行：python xyks_ai.py start（若部署在容器/魔搭则看平台日志）"
    emit("status", True, data, advice=advice)


def cmd_score(a):
    ck = load_cookie()
    if not ck:
        emit("score", False, error="cookie missing", code=1)
    import core_engine as C
    h = C.fetch_honor(ck)
    if not h:
        emit("score", False, error="fetch_honor failed (网络或登录态失效)", code=1)
    emit("score", True, {"curWeekScore": h.get("curWeekScore"),
                         "curRank": h.get("curRank"),
                         "multiInfoList": h.get("multiInfoList")})


def cmd_round(a):
    ck = load_cookie()
    if not ck:
        emit("round", False, error="cookie missing", code=1)
    import core_engine as C
    t0 = time.time()
    r = C.complete_pk_round(73, ck, humanize=True, doing_sec=6.0, mode="solo")
    dur = int((time.time() - t0) * 1000)
    data = {"ok": r.get("ok"), "win": r.get("win"), "answered": r.get("answered"),
            "pkIdStr": r.get("pkIdStr"), "note": r.get("note"), "dur_ms": dur}
    advice = None
    if not r.get("ok"):
        note = r.get("note") or ""
        if "400" in note:
            advice = "配额未回填：静默等待约 10 分钟后重试，勿连续轰炸"
        elif "401" in note:
            advice = "登录态失效：重新执行 login136.py"
    emit("round", bool(r.get("ok")), data, error=None if r.get("ok") else note_or(r),
         advice=advice, code=0 if r.get("ok") else 1)


def note_or(r):
    return r.get("note") or "round failed"


def cmd_logs(a):
    lines = read_tail(JSONL if a.source == "jsonl" else STDOUT_LOG, a.tail)
    emit("logs", True, {"source": a.source, "lines": lines})


def cmd_diagnose(a):
    issues = []

    # 1) so 依赖
    so = os.path.join(HERE, "xyks", "so", "libRequestEncoder.so")
    if not os.path.exists(so):
        issues.append({"level": "high", "code": "SO_MISSING",
                       "msg": "缺 libRequestEncoder.so（签名模拟必需）",
                       "fix": "unzip -j <小猿口算.apk> lib/armeabi-v7a/libRequestEncoder.so -d xyks/so/"})

    # 2) cookie
    ck = load_cookie()
    if not ck:
        issues.append({"level": "high", "code": "COOKIE_MISSING",
                       "msg": "缺 login136.json",
                       "fix": "XYKS_PHONE=... XYKS_SMS_CODE=... python xyks/crack_sign/login136.py"})

    # 3) 节奏 / 400 风暴
    entries = parse_jsonl(300)
    wait = sum(1 for e in entries[-30:] if e.get("wait_cd"))
    pace = pace_stats(entries)
    if wait > 15:
        issues.append({"level": "high", "code": "RATE_STORM",
                       "msg": "最近 30 条中冷却等待 >15，疑似 400 风暴",
                       "fix": "保持零风暴策略（成功后静默 10.5min、失败静默 10min），等待窗口自愈"})
    if pace and pace["avg_interval_sec"] < 90 and len(entries) > 5:
        pass  # 快档，好事

    # 4) 进程
    pid = farm_pid()
    if not pid and not os.environ.get("XYKS_CONTAINER"):
        issues.append({"level": "mid", "code": "FARM_DOWN",
                       "msg": "本机常驻 farm 未运行",
                       "fix": "python xyks_ai.py start"})

    high = [i for i in issues if i["level"] == "high"]
    advice = None
    if issues:
        advice = "；".join(i["code"] for i in issues)
    emit("diagnose", not high, {"issues": issues, "pace": pace,
                                "recent_wait_cd": wait},
         advice=advice, code=2 if high else 0)


def cmd_start(a):
    if farm_pid():
        emit("start", True, {"already_running": farm_pid()})
    if not os.path.exists(PYTHONW):
        emit("start", False, error="pythonw.exe not found: " + PYTHONW, code=1)
    daemon = os.path.join(HERE, "deploy", "windows", "farm_daemon.pyw")
    if not os.path.exists(daemon):
        emit("start", False, error="daemon entry missing: " + daemon, code=1)
    p = subprocess.Popen([PYTHONW, daemon], cwd=os.path.dirname(daemon),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with open(PID_FILE, "w") as f:
        f.write(str(p.pid))
    time.sleep(1.5)
    emit("start", True, {"pid": p.pid})


def cmd_stop(a):
    pid = farm_pid()
    if not pid:
        emit("stop", True, {"was_running": False})
    os.system("taskkill /PID %d /F" % pid)
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    emit("stop", True, {"was_running": True, "killed": pid})


def main():
    ap = argparse.ArgumentParser(prog="xyks_ai", add_help=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("score")
    p_round = sub.add_parser("round")
    p_round.add_argument("--once", action="store_true")
    p_logs = sub.add_parser("logs")
    p_logs.add_argument("--tail", type=int, default=50)
    p_logs.add_argument("--source", choices=["jsonl", "stdout"], default="jsonl")
    sub.add_parser("diagnose")
    sub.add_parser("start")
    sub.add_parser("stop")
    a = ap.parse_args()

    {"status": cmd_status, "score": cmd_score, "round": cmd_round,
     "logs": cmd_logs, "diagnose": cmd_diagnose,
     "start": cmd_start, "stop": cmd_stop}[a.cmd](a)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"ok": False, "cmd": "crash", "data": {},
                          "error": repr(e), "advice": "查看 xyks_ai.py traceback"},
                         ensure_ascii=False))
        sys.exit(1)
