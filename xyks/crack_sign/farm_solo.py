# -*- coding: utf-8 -*-
# farm_solo.py —— 单账号稳定串行刷分：
#   solo(match/v2 + PUT submit no-sign) + 6s做題 + 自然轨迹 + submit重放兜底 + 60s冷却对齐
# 用法: python farm_solo.py [目标分] [最大局数]
import sys, json, time, os, datetime
sys.stdout = sys.stderr
_D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _D)
import core_engine as C

CKF = os.path.join(_D, "login136.json")
LOGF = os.path.join(_D, "farm_solo.jsonl")
POINT = "73"
DOING = 6.0          # 每局做题秒数（用户要求 6 秒）
PERIOD = 630.0       # 对局周期：服务端回填约8.3-10.3分钟，静默10.5分钟后一发命中（零风暴策略）
MODE = "solo"

ck = json.load(open(CKF, encoding="utf-8"))["cookie"] if os.path.exists(CKF) else C.grab_cookie()


def log(o):
    o["ts"] = datetime.datetime.now().strftime("%H:%M:%S")
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(f"[{o['ts']}] {o.get('msg','')}", flush=True)


def score():
    return (C.fetch_honor(ck) or {}).get("curWeekScore")


def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    max_round = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    s0 = score()
    log({"msg": f"farm_solo 启动 mode={MODE} doing={DOING}s 目标={target} 起始分={s0}", "start": True})
    wins = fails = 0
    cd_streak = 0   # 连续 400 计数：短锁期(submit+60s)快速过线，长窗口期长睡等回填
    t_next = time.time()  # 立即第一局
    while True:
        sc = score()
        if sc is not None and sc >= target:
            log({"msg": f"★★★★★ 达成目标 {sc}", "done": True}); break
        if max_round and wins + fails >= max_round:
            log({"msg": f"到达最大局数 {max_round}, 共胜{wins}败{fails}", "stop": True}); break
        try:
            C.send_device_companion(ck)  # 真机伴随请求(设备证书/OAID/设备同步)
            r = C.complete_pk_round(POINT, ck, humanize=True, doing_sec=DOING, mode=MODE)
            if r.get("ok"):
                wins += 1
                cd_streak = 0
                sc = score()
                log({"msg": f"✓ 第{wins}局 分={sc} note={r.get('note')} 用时{r.get('dur_ms')}ms",
                     "win": True, "score": sc})
            else:
                note = r.get("note") or ""
                if "match" in note and "400" in note:
                    # 零风暴策略：失败也静默10分钟再单探（密集失败探测可能喂养降权计数器，
                    # 早上七连快波期间是零失败请求）
                    cd_streak += 1
                    log({"msg": f"match 未回填 #{cd_streak}，静默600s后单探", "wait_cd": True})
                    time.sleep(600)
                    t_next = time.time()
                    continue
                fails += 1
                log({"msg": f"✗ 该局失败 note={note}", "fail": True, "note": note})
        except Exception as e:
            fails += 1
            log({"msg": f"✗ 异常 {repr(e)[:80]}", "fail": True})
        # 对齐周期（仅成功局 + 非冷却等待时）
        t_next += PERIOD
        wait = t_next - time.time()
        if wait > 0:
            time.sleep(wait)
        else:
            # 落后时不追赶：等满一个完整冷却周期，避免踩 60s 锁
            t_next = time.time() + PERIOD


if __name__ == "__main__":
    main()