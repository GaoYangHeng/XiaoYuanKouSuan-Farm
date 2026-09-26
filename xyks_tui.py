# -*- coding: utf-8 -*-
"""xyks_tui.py — 终端仪表盘（零依赖，跨平台）

运行: python xyks_tui.py [--interval 15]
刷新: 全屏重绘；Ctrl+C 退出
按键（单字符模式下）: q 退出 / r 立即跑一局（同步）
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CRACK = os.path.join(HERE, "xyks", "crack_sign")
JSONL = os.path.join(CRACK, "farm_solo.jsonl")
sys.path.insert(0, HERE)


def read_jsonl(n=12):
    out = []
    try:
        with open(JSONL, encoding="utf-8", errors="replace") as f:
            for ln in f.read().splitlines()[-n:]:
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def fetch_score():
    try:
        import xyks_ai
        ck = xyks_ai.load_cookie()
        if not ck:
            return None, "no cookie"
        import core_engine as C
        h = C.fetch_honor(ck)
        if not h:
            return None, "fetch failed"
        return h.get("curWeekScore"), None
    except Exception as e:
        return None, repr(e)


def render(score, score_err, entries, pid, pace):
    lines = []
    lines.append("=" * 72)
    lines.append("  XiaoYuanKouSuan Farm  ·  TUI")
    lines.append("=" * 72)
    st = "RUNNING pid=%s" % pid if pid else "STOPPED"
    lines.append("  时间: %s     进程: %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), st))
    if score is not None:
        try:
            lines.append("  周荣誉分: %d" % int(score))
        except (TypeError, ValueError):
            lines.append("  周荣誉分: %s" % score)
    else:
        lines.append("  周荣誉分: 查询失败 (%s)" % score_err)
    lines.append("  节奏: %s" % (pace or "-"))
    lines.append("-" * 72)
    lines.append("  最近对局:")
    for e in entries[-8:]:
        mark = "✓" if e.get("win") else ("~" if e.get("wait_cd") else "✗")
        msg = e.get("msg", "")[:56]
        lines.append("   %s [%s] %s" % (mark, e.get("ts", "--:--:--"), msg))
    lines.append("=" * 72)
    lines.append("  q=退出  r=立即跑一局  （Ctrl+C 亦可退出）")
    os.system("cls" if os.name == "nt" else "clear")
    print("\n".join(lines))


def pace_summary(entries):
    wins = [e for e in entries if e.get("win")]
    if len(wins) < 2:
        return None
    def sec(t):
        h, m, s = map(int, t.split(":"))
        return h * 3600 + m * 60 + s
    try:
        last = [sec(e["ts"]) for e in wins[-4:]]
        diffs = [b - a for a, b in zip(last, last[1:])]
        avg = sum(diffs) / len(diffs)
        return "%.1f 分钟/局" % (avg / 60)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=15)
    a = ap.parse_args()
    last_score = None
    score_err = None
    next_score_at = 0
    try:
        while True:
            now = time.time()
            if now >= next_score_at:
                last_score, score_err = fetch_score()
                next_score_at = now + 120
            entries = read_jsonl()
            try:
                import xyks_ai
                pid = xyks_ai.farm_pid()
            except Exception:
                pid = None
            render(last_score, score_err, entries, pid, pace_summary(entries))
            time.sleep(a.interval)
    except KeyboardInterrupt:
        print("\n[tui] 退出")


if __name__ == "__main__":
    main()
