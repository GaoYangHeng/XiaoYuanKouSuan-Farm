# -*- coding: utf-8 -*-
# PC 端 PK 完整对局闭环：match -> 解密测验 -> 构造答题卡 -> 加密提交 -> 查分
import os, sys, time, ssl
import urllib.request, urllib.error, gzip, json, base64
import contentcoder

SAVE_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_card_src.json")

sys.stdout = sys.stderr
from emulator import Emulator

HOST = "https://xyks.yuanfudao.com"
MATCH_PATH = "/leo-game-pk/android/math/pk/multi/match/v2"
SUBMIT_PATH = "/leo-game-pk/android/math/pk/submit"
DETAIL_PATH = "/leo-game-pk/android/math/pk/history/detail"
KEY = "wdi4n2t8edr"
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "req_capture.log")

UA = ("Mozilla/5.0 (Linux; Android 14; ELZ-AN10 Build/HONORELZ-AN10) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36")
COMMON_Q = [("_productId", "611"), ("platform", "android34"), ("version", "3.141.1"),
            ("vendor", "tencent"), ("av", "5"), ("deviceCategory", "phone"),
            ("webviewVersion", "131"), ("whRatio", "2.06")]


def gen_sign(ts, path):
    P = chr((ord(path[0]) + 1) % 256) + path[1:]
    e = Emulator()
    e.time_ret = ts
    save = sys.stdout
    sys.stdout = open(os.devnull, "w")
    try:
        e.start(P, KEY, ts)
        return (e.final_sign or "").strip()
    finally:
        sys.stdout = save


def grab_cookie():
    c0 = c70 = None
    with open(LOG, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    for l in lines:
        if " CK[0]=" in l:
            c0 = l[l.rindex(" CK[0]=") + len(" CK[0]="):].strip()
        if " CK[700]=" in l:
            c70 = l[l.rindex(" CK[700]=") + len(" CK[700]="):].strip()
    if not c0:
        return None
    return c0 + (c70 if c70 else "")


def http(method, url, cookie, body=None, content_type=None):
    ctx = ssl.create_default_context()
    hd = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    if content_type:
        hd["Content-Type"] = content_type
    if cookie:
        hd["Cookie"] = cookie
    req = urllib.request.Request(url, data=body, headers=hd, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=25, context=ctx)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def build_card(root, captured_ms, fixed_cost=None):
    examVO = root["examVO"]
    src = examVO.get("questions", [])
    s = []
    for q in src:
        nq = dict(q)
        ans = nq.get("answer", "")
        nq["userAnswer"] = ans
        nq["curTrueAnswer"] = {"answer": 1, "recognizeResult": ans, "pathPoints": []}
        nq["status"] = 1
        s.append(nq)
    now = int(time.time() * 1000)
    if fixed_cost:
        cost = fixed_cost
    else:
        cost = now - captured_ms
        if cost < 2000:
            cost = 2000
        if cost > 9000:
            cost = 9000
    y = dict(examVO)
    y["questions"] = s
    y["correctCnt"] = len(s)
    y["costTime"] = cost
    y["updatedTime"] = now
    k = dict(y)
    k["examVO"] = y
    ui = []
    for op in root.get("opponents", []) or []:
        info = (op or {}).get("userInfo")
        if info:
            ui.append(info)
    k["userInfos"] = ui
    return k


def main():
    cookie = grab_cookie()
    print("COOKIE LEN:", len(cookie) if cookie else 0)
    if not cookie:
        print("!! 未抓到 cookie，退出")
        return

    ts = int(time.time())
    qmc = [("pointId", "73")] + COMMON_Q + [("sign", gen_sign(ts, MATCH_PATH))]
    murl = HOST + MATCH_PATH + "?" + "&".join(f"{k}={v}" for k, v in qmc)
    print("== 1. match ==")
    st, raw = http("POST", murl, cookie)
    print("match STATUS=", st, "rawLen=", len(raw), "head=", raw[:16].hex())
    if st != 200:
        print("!! match 失败"); return
    gz = contentcoder.run_e_c(raw)
    root = json.loads(gzip.decompress(gz))
    with open(SAVE_SRC, "w", encoding="utf-8") as f:
        json.dump(root, f, ensure_ascii=False)
    cap = int(time.time() * 1000)
    print("== 2. 解密 == pkIdStr=", root["pkIdStr"], "questions=", len(root["examVO"]["questions"]),
          "Q0=", root["examVO"]["questions"][0]["content"], root["examVO"]["questions"][0]["answer"])
    print("  模拟真实做题耗时 9s，costTime 按实际 elapsed 动态计算 ...")
    time.sleep(9)

    card = build_card(root, cap, None)
    print("== 3. 构造答题卡 == cnt=", len(card["questions"]), "cost=", card["costTime"])
    body = contentcoder.encrypt(json.dumps(card, separators=(",", ":")).encode("utf-8"))
    print("  encrypt len=", len(body), "head=", body[:8].hex())
    surl = HOST + SUBMIT_PATH + "?" + "&".join(f"{k}={v}" for k, v in COMMON_Q)
    print("== 4. submit PUT ==")
    sst, sbody = http("PUT", surl, cookie, body, content_type="application/octet-stream")
    print("submit STATUS=", sst, "resp=", sbody[:200])
    if sst not in range(200, 300):
        print("!! submit 失败"); return

    time.sleep(3)
    ts = int(time.time())
    dq = [("pkIdStr", root["pkIdStr"])] + COMMON_Q + [("sign", gen_sign(ts, DETAIL_PATH))]
    durl = HOST + DETAIL_PATH + "?" + "&".join(f"{k}={v}" for k, v in dq)
    print("== 5. 查分 ==")
    dst, dbody = http("GET", durl, cookie)
    print("detail STATUS=", dst)
    print("detail body=", dbody[:1500])


if __name__ == "__main__":
    main()