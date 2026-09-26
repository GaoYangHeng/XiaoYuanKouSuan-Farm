# -*- coding: utf-8 -*-
# core_engine.py — PK 上分核心引擎：人类化手写轨迹 + 完整对局闭环 + 积分/用户/题型补录
# 复用 pc_pk_round 的签名/请求基础；防封关键：pathPoints 由 S1 笔画模板 + jitter 抖动生成
import os, sys, time, ssl, random, threading
import urllib.request, urllib.error, urllib.parse, gzip, json
import contentcoder
import pc_pk_round as P  # 复用 http/gen_sign/grab_cookie

sys.stdout = sys.stderr
from emulator import Emulator

_LOGIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mod_apk", "work")
if _LOGIN_DIR not in sys.path:
    sys.path.insert(0, _LOGIN_DIR)
import login_sms as _L  # 复用 RSA/md5签名/YFD_U（ape-api 登录链路）

HOST = P.HOST
MATCH_PATH, SUBMIT_PATH, DETAIL_PATH = P.MATCH_PATH, P.SUBMIT_PATH, P.DETAIL_PATH
# 对局模式 → (匹配路径, 提交路径, 提交方法, 提交是否需sign)。
# 关键（实测）：8人局 = POST /multi/submit 且【必须带 sign】，支持秒级快速提交（实测2s 200）；
# 1v1 = PUT /pk/submit（query 不带 sign，慢速）。两者都走 contentcoder 加密 body。
PK_MODES = {
    "multi": ("/leo-game-pk/android/math/pk/multi/match/v2",
              "/leo-game-pk/android/math/pk/multi/submit", "POST", True),
    "solo":  ("/leo-game-pk/android/math/pk/match/v2",
              "/leo-game-pk/android/math/pk/submit", "PUT", False),
}
KEY, LOG, UA, COMMON_Q = P.KEY, P.LOG, P.UA, P.COMMON_Q
SAVE_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_card_src.json")

# ---- 已知题型 pointId->名称（离线预置；运行时对局自动补录新题型）----
KNOWN_POINTS = [
    {"pointId": "1951", "name": "巅峰对决"},
    {"pointId": "73", "name": "两三位数的加减法"},
]
POINT_REGISTRY = {p["pointId"]: p["name"] for p in KNOWN_POINTS}

# 书写题板逻辑尺寸（px，近似手机写答案区；坐标并不校验精确像素，仅需非空且带抖动）
PAD = {"left": 20, "top": 150, "width": 340, "height": 100}

# 年级枚举（来自 H5 pk-config）：1-6 一~六年级，13=巅峰对决，100=学龄前
GRADES = [
    {"grade": "1", "name": "一年级"}, {"grade": "2", "name": "二年级"},
    {"grade": "3", "name": "三年级"}, {"grade": "4", "name": "四年级"},
    {"grade": "5", "name": "五年级"}, {"grade": "6", "name": "六年级"},
    {"grade": "13", "name": "巅峰对决"},
]


# ---- 人类化手写轨迹：移植自 PkHelper.java 的 AUTO_ANSWER_JS ----
S1 = {
    "<": [[[.62, .32], [.5, .43], [.38, .5], [.5, .58], [.61, .68]]],
    ">": [[[.38, .32], [.5, .43], [.62, .5], [.5, .58], [.39, .68]]],
    "0": [[[.44, .32], [.35, .4], [.35, .6], [.44, .68], [.56, .68], [.65, .6], [.65, .4], [.56, .32], [.44, .32]]],
    "1": [[[.44, .37], [.53, .3], [.53, .68]]],
    "2": [[[.36, .38], [.47, .3], [.6, .34], [.56, .47], [.38, .62], [.36, .68], [.63, .68]]],
    "3": [[[.36, .33], [.57, .32], [.45, .46], [.58, .52], [.56, .63], [.44, .68], [.34, .64]]],
    "4": [[[.57, .3], [.37, .55], [.65, .55]]],
    "5": [[[.59, .31], [.4, .31], [.38, .46], [.53, .45], [.62, .55], [.54, .67], [.4, .66]]],
    "6": [[[.57, .32], [.42, .5], [.4, .63], [.51, .68], [.6, .61], [.57, .52], [.44, .51]]],
    "7": [[[.36, .32], [.62, .32], [.46, .68]]],
    "8": [[[.5, .32], [.41, .37], [.47, .47], [.56, .53], [.6, .62], [.51, .68], [.42, .62], [.46, .53], [.55, .46], [.6, .38], [.5, .32]]],
    "9": [[[.6, .44], [.45, .42], [.4, .34], [.55, .3], [.62, .41], [.58, .66]]],
    "+": [[[.5, .32], [.5, .66]], [[.33, .49], [.67, .49]]],
    "-": [[[.34, .5], [.66, .5]]],
    "=": [[[.32, .42], [.68, .42]], [[.32, .6], [.68, .6]]],
    "×": [[[.36, .36], [.64, .64]], [[.64, .36], [.36, .64]]],
    "x": [[[.36, .36], [.64, .64]], [[.64, .36], [.36, .64]]],
    "*": [[[.5, .34], [.5, .64]], [[.36, .42], [.64, .42]], [[.4, .6], [.6, .6]]],
    "÷": [[[.32, .5], [.68, .5]], [[.5, .35], [.5, .37]], [[.5, .63], [.5, .65]]],
    "/": [[[.62, .3], [.38, .7]]],
    ":": [[[.5, .4], [.5, .41]], [[.5, .6], [.5, .61]]],
}
FALLBACK = [[[.38, .58], [.44, .36], [.54, .38], [.58, .54], [.5, .66], [.42, .62]]]

AMP_X, AMP_Y = 0.006, 0.008  # 抖动幅度（横向/纵向），保留真实手写随机偏移，避免"笔记太直"


def _jitter(v, amp):
    return v + random.uniform(-amp, amp)


def _scatter(p):
    """给单点加有界的自然噪声（比均匀 jitter 更柔和）。"""
    return p * random.uniform(0.92, 1.08)


def build_strokes(ans, pad=None):
    """根据答案字符串生成自然手写轨迹：每笔做 Catmull-Rom 平滑插值，
    点密度/起笔偏移/轻微缩放旋转随机，保证同一答案每次都不同（防轨迹模板被风控识别）。
    返回 [{x,y},...] 扁平点序列。"""
    import math as _math
    pad = pad or PAD
    chars = list(str(ans))
    if not chars:
        chars = ["?"]
    n = len(chars)
    cw = min(.5, .72 / n) * random.uniform(0.88, 1.12)  # 单字宽度抖动
    x0 = .5 - (n * cw) / 2 + random.uniform(-0.02, 0.02)
    # 整体轻微旋转（rad）
    ang = random.uniform(-0.05, 0.05)
    ca, sa = _math.cos(ang), _math.sin(ang)
    # 整体轻微缩放
    sc = random.uniform(0.94, 1.06)
    out = []
    for k, ch in enumerate(chars):
        strokes = S1.get(ch, FALLBACK)
        for st in strokes:
            # 每笔画采样点：在模板点之间插值，密度随机（每段 1-2 插值点）
            segs = []
            for i in range(len(st) - 1):
                xa, ya = st[i]; xb, yb = st[i + 1]
                inner = random.randint(0, 2)
                segs.append((xa, ya))
                for _j in range(inner):
                    t = random.uniform(0.05, 0.95)
                    segs.append((xa + (xb - xa) * t, ya + (yb - ya) * t))
            segs.append(st[-1])
            # 起笔/落笔轻微漂移
            start_j = random.uniform(-0.04, 0.04)
            end_j = random.uniform(-0.04, 0.04)
            for idx, (px, py) in enumerate(segs):
                wrap = start_j if idx == 0 else (end_j if idx == len(segs) - 1 else 0.0)
                nx = (px + wrap) * sc + x0
                ny = py * sc
                # 应用到 y 以 0.55 高度
                ny = .3 + ny * .55
                # 旋转（围绕字中心）
                cx, cy = nx - x0, ny - .55
                rx = cx * ca - cy * sa
                ry = cx * sa + cy * ca
                nx, ny = rx + x0, ry + .55
                out.append({"x": round(pad["left"] + pad["width"] * _scatter(nx), 2),
                            "y": round(pad["top"] + pad["height"] * _scatter(ny), 2)})
    return out


_sign_lock = threading.Lock()
_sign_cache = {}   # (minute, path) -> sign，避免高并发时重复拉起模拟器
_SIGN_CACHE_MAX = 512


def gen_sign(ts, path):
    # 签名按"分钟粒度"变化（sign 输入含 minute=ts//60），同分钟同路径可复用
    minute = int(ts) // 60
    key = (minute, path)
    cached = _sign_cache.get(key)
    if cached:
        return cached
    with _sign_lock:
        cached = _sign_cache.get(key)
        if cached:
            return cached
        Pc = chr((ord(path[0]) + 1) % 256) + path[1:]
        e = Emulator()
        e.time_ret = ts
        save = sys.stdout
        sys.stdout = open(os.devnull, "w")
        try:
            e.start(Pc, KEY, ts)
            sign = (e.final_sign or "").strip()
        finally:
            sys.stdout = save
        # 控制缓存体积，防止长时间运行内存增长
        if len(_sign_cache) > _SIGN_CACHE_MAX:
            _sign_cache.clear()
        _sign_cache[key] = sign
        return sign


def grab_cookie():
    c0 = c70 = None
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return None
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


def parse_ec(raw):
    try:
        return json.loads(gzip.decompress(contentcoder.run_e_c(raw)))
    except Exception:
        return None


def is_ratelimited(code, body):
    """识别服务端频控：400 请求过于频繁 / 403 error（对局接口高频时返回）。"""
    if code not in (400, 403, 429):
        return False
    try:
        t = body.decode("utf-8", "ignore") if isinstance(body, (bytes, bytearray)) else str(body)
    except Exception:
        return False
    return ("频繁" in t) or ("频繁" in t) or ("rate" in t.lower()) or (code == 403 and '"error"' in t)


def build_card(root, captured_ms, humanize=True):
    """构造答题卡；humanize=True 时 pathPoints 填入 S1 人类化轨迹（防封）。"""
    examVO = root["examVO"]
    s = []
    for q in examVO.get("questions", []):
        nq = dict(q)
        ans = nq.get("answer", "")
        paths = build_strokes(ans) if humanize else []
        nq["userAnswer"] = ans
        nq["curTrueAnswer"] = {"answer": 1, "recognizeResult": ans, "pathPoints": paths}
        nq["status"] = 1
        s.append(nq)
    now = int(time.time() * 1000)
    cost = now - captured_ms
    cost = max(2000, min(9000, cost))
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


def complete_pk_round(point_id, cookie, register_cb=None, humanize=True, doing_sec=6.0, mode="solo"):
    """完整一局：match->解密->构造答题卡(人类化轨迹)->submit->detail。
    doing_sec：match 后模拟做题耗时（秒），决定 costTime 量级；调小则更快但更激进。
    mode：'multi'=8人局(match/multi + POST multi/submit)，'solo'=1v1(match/v2 + PUT submit)。
    返回 dict：{ok, win, answered, dur_ms, pkIdStr, note, resp}，win: True胜/False负/None平或未知。"""
    match_path, submit_path, submit_method, submit_need_sign = PK_MODES.get(mode, PK_MODES["multi"])
    cap_ms = int(time.time() * 1000)
    ts = int(time.time())
    qmc = [("pointId", str(point_id))] + COMMON_Q + [("sign", gen_sign(ts, match_path))]
    murl = HOST + match_path + "?" + "&".join(f"{k}={v}" for k, v in qmc)
    st, raw = http("POST", murl, cookie, content_type="application/x-www-form-urlencoded")
    if st == 401:
        return {"ok": False, "auth": False, "ratelimit": False,
                "note": "match HTTP 401 unauthorized(登录态失效)",
                "win": None, "answered": 0, "dur_ms": 0, "pkIdStr": None, "resp": raw[:200]}
    if st != 200:
        return {"ok": False, "auth": True, "ratelimit": is_ratelimited(st, raw),
                "note": f"match HTTP {st}", "win": None, "answered": 0,
                "dur_ms": 0, "pkIdStr": None, "resp": raw[:200]}
    root = parse_ec(raw)
    if not root:
        return {"ok": False, "auth": True, "ratelimit": False, "note": "match 解密失败",
                "win": None, "answered": 0, "dur_ms": 0, "pkIdStr": None, "resp": raw[:200]}
    pk = root.get("pkIdStr")
    ex = root.get("examVO") or {}
    questions = ex.get("questions") or []
    answered = len(questions)
    if register_cb:
        try:
            register_cb(point_id, questions)
        except Exception:
            pass
    with open(SAVE_SRC, "w", encoding="utf-8") as f:
        json.dump(root, f, ensure_ascii=False)
    time.sleep(max(0.5, doing_sec))  # 模拟做题耗时，costTime 随之动态计算
    card = build_card(root, cap_ms, humanize)
    body = contentcoder.encrypt(json.dumps(card, separators=(",", ":")).encode("utf-8"))
    # multi/submit 需要 sign（实测无 sign 返回 403 forbidden）；solo 的 PUT /pk/submit 不带
    if submit_need_sign:
        sq = [("pointId", str(point_id))] + COMMON_Q + [("sign", gen_sign(int(time.time()), submit_path))]
        surl = HOST + submit_path + "?" + "&".join(f"{k}={v}" for k, v in sq)
    else:
        surl = HOST + submit_path + "?" + "&".join(f"{k}={v}" for k, v in COMMON_Q)
    # 实测：submit 存在偶发 403，同 body 立即重放即 200。故做有限次重放兜底。
    sst, sbody = None, None
    for _attempt in range(6):
        sst, sbody = http(submit_method, surl, cookie, body, content_type="application/octet-stream")
        if sst in range(200, 300):
            break
        time.sleep(1.2)
    if sst not in range(200, 300):
        return {"ok": False, "auth": (sst == 401), "ratelimit": is_ratelimited(sst, sbody),
                "note": f"submit HTTP {sst}", "win": None,
                "answered": answered, "dur_ms": 0, "pkIdStr": pk, "resp": sbody[:200]}
    time.sleep(0.6)  # 结果简短等待
    ts = int(time.time())
    dq = [("pkIdStr", pk)] + COMMON_Q + [("sign", gen_sign(ts, DETAIL_PATH))]
    durl = HOST + DETAIL_PATH + "?" + "&".join(f"{k}={v}" for k, v in dq)
    dst, dbody = http("GET", durl, cookie)
    win = None  # pkResult: 1=胜 2=负 3=平
    correct = answered
    dnote = f"detail HTTP {dst}"
    if dst == 200:
        try:
            d = json.loads(dbody.decode("utf-8", "replace"))
            # 8人局 detail 通常只有题目批改，胜负在 history 列表里（按 pkIdStr 匹配）
            correct = d.get("correctCnt", answered)
            pr = d.get("pkResult", d.get("result"))
            if isinstance(pr, int):
                win = pr == 1
            else:
                hist = fetch_history(cookie, limit=5) or []
                for h in hist:
                    if str(h.get("pkIdStr")) == str(pk) and isinstance(h.get("pkResult"), int):
                        win = (h["pkResult"] == 1)
                        dnote = f"pkResult={h['pkResult']} q={answered} +{h.get('capacity','?')}"
                        break
        except Exception:
            pass
    dur_ms = int(time.time() * 1000) - cap_ms
    return {"ok": True, "note": dnote, "win": win, "answered": correct,
            "dur_ms": dur_ms, "pkIdStr": pk, "resp": dbody[:200]}


# ---- 账号信息采集 ----
PK_HOME_PATH = "/leo-game-pk/android/math/pk/home"


def _ape_get(path, cookie, extra=None, need_udid=True, host=None, ts=None):
    """ape-api 域 GET：md5 四轮签名 + YFD_U。返回(st, raw)。"""
    host = host or _L.HOST
    ts = ts or _L.server_ts()
    q = dict(_L.COMMON)
    if need_udid or (extra and "YFD_U" in extra):
        q["YFD_U"] = str(_L.calc_udid())
    q.update(extra or {})
    q["sign"] = _L.calc_sign(path, ts)
    url = host + path + "?" + urllib.parse.urlencode(q)
    return http("GET", url, cookie)


def fetch_profile(cookie):
    """leo-profile/user-infos：昵称/年级/微信绑定状态。返回 dict。"""
    path = "/leo-profile/android/user-infos"
    q = [("isBackground", "0")] + COMMON_Q + [("sign", gen_sign(int(time.time()), path))]
    url = HOST + path + "?" + "&".join(f"{k}={v}" for k, v in q)
    st, raw = http("GET", url, cookie)
    if st != 200:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def fetch_account_phone(cookie):
    """accounts/android/current：拿绑定手机号（掩码展示用）。"""
    try:
        st, raw = _ape_get("/accounts/android/current", cookie,
                           {"YFD_U": str(_L.calc_udid()), "isBackground": "0"})
        if st == 200:
            return json.loads(raw.decode("utf-8")).get("phone") or None
    except Exception:
        pass
    return None


def mask_phone(p):
    if not p:
        return "--"
    p = str(p)
    return p[:3] + "****" + p[-4:] if len(p) >= 7 else p


def fetch_account_full(cookie, host=None):
    """ape-api accounts/android/current：返回 (cookies_dict, phone)。
    登录后必须补取 __sub_user_infos__（保存所选年级/子账号上下文），否则 xyks 业务接口(match)会 401。"""
    host = host or _L.HOST
    ts = _L.server_ts()
    q = dict(_L.COMMON)
    q["YFD_U"] = str(_L.calc_udid())
    q["sign"] = _L.calc_sign("/accounts/android/current", ts)
    url = host + "/accounts/android/current?" + urllib.parse.urlencode(q)
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": _L.UA,
                                          "Cookie": cookie or ""})
    try:
        r = urllib.request.urlopen(req, timeout=20, context=ctx)
        cookies = r.headers.get_all("Set-Cookie") or []
        raw = r.read()
        r.close()
    except urllib.error.HTTPError as e:
        return {}, None
    ck = {}
    for c in cookies:
        if "=" in c:
            name = c.split("=", 1)[0].strip()
            val = c.split(";", 1)[0].split("=", 1)[1].strip()
            if name:
                ck[name] = val
    phone = None
    try:
        phone = (json.loads(raw.decode("utf-8")) or {}).get("phone")
    except Exception:
        pass
    return ck, phone


def merge_cookie(base, extra):
    """按序合并 cookie 键值，extra 覆盖同名键；返回 '; ' 拼接字符串。"""
    order = []
    kv = {}
    for part in (base or "").split(";"):
        if "=" in part:
            k = part.split("=", 1)[0].strip()
            if k:
                kv[k] = part.split("=", 1)[1].strip()
                if k not in order:
                    order.append(k)
    for k, v in (extra or {}).items():
        kv[k] = v
        if k not in order:
            order.append(k)
    return "; ".join(f"{k}={kv[k]}" for k in order)


KEYSTONE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keystone.json")
KEYSTONE_KEYS = ("ks_persistent", "ks_r", "ks_sess", "ks_deviceid", "ks_u")


def load_keystone():
    """从 keystone.json 读取设备级 keystone（PK 业务鉴权必需），无则从抓包 cookie 现场提取。"""
    try:
        with open(KEYSTONE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        ks = d.get("keystone") or {}
        if ks:
            return dict(ks)
    except Exception:
        pass
    # 现场从抓包 cookie 提取
    gk = grab_cookie() or ""
    kv = {}
    for p in gk.split(";"):
        if "=" in p:
            k = p.split("=", 1)[0].strip()
            if k:
                kv[k] = p.split("=", 1)[1].strip()
    return {k: kv[k] for k in KEYSTONE_KEYS if k in kv}


def ensure_pk_cookie(cookie):
    """给登录 cookie 补 PK 业务 keystone(ks_*/sid)。缺则合并 keystone.json 的设备级凭证。
    作用：让 leo-game-pk match 等接口不再 401（ks_* 是设备级，可跨登录复用）。"""
    kv = {}
    for p in (cookie or "").split(";"):
        if "=" in p:
            k = p.split("=", 1)[0].strip()
            if k:
                kv[k] = p.split("=", 1)[1].strip()
    has_ks = any(k in kv for k in KEYSTONE_KEYS)
    if not has_ks:
        ks = load_keystone()
        if ks:
            kv.update(ks)
    return "; ".join(f"{k}={v}" for k, v in kv.items())


# ---- 手机号+验证码登录（替代手动抓 Cookie）----
def sms_send_code(phone, udid=None, ts=None):
    """发送短信验证码。返回 (status, msg)。"""
    udid = udid or str(_L.calc_udid())
    ts = ts or _L.server_ts()
    enc = _L.rsa_encrypt_phone(phone)
    q = dict(_L.COMMON); q["YFD_U"] = udid
    q["sign"] = _L.calc_sign("/verifier/android/sms", ts)
    url = _L.HOST + "/verifier/android/sms?" + urllib.parse.urlencode(q)
    data = urllib.parse.urlencode({"phone": enc}).encode()
    st, raw = http("POST", url, None, data, "application/x-www-form-urlencoded")
    return st, raw[:300]


def sms_login(phone, code, udid=None, ts=None):
    """验证码登录。成功返回 cookie 字符串（Set-Cookie 里的 sess/userid 等)。"""
    udid = udid or str(_L.calc_udid())
    ts = ts or _L.server_ts()
    enc = _L.rsa_encrypt_phone(phone)
    fields = {"phone": enc, "verification": _L.rsa_encrypt_phone(code), "autoRegister": "true"}
    q = dict(_L.COMMON); q["YFD_U"] = udid
    q["sign"] = _L.calc_sign("/accounts/android/safe/login", ts)
    url = _L.HOST + "/accounts/android/safe/login?" + urllib.parse.urlencode(q)
    data = urllib.parse.urlencode(fields).encode()
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "User-Agent": _L.UA})
    try:
        r = urllib.request.urlopen(req, timeout=20, context=ctx)
        cookies = r.headers.get_all("Set-Cookie") or []
        r.read()
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read()[:200]}"
    parts = []
    for c in cookies:
        if "=" not in c:
            continue
        name = c.split("=", 1)[0].strip()
        val = c.split(";", 1)[0].split("=", 1)[1].strip()
        if name:
            parts.append(f"{name}={val}")
    if not parts:
        return None, "未获得会话 Cookie(Set-Cookie 为空)"
    login_cookie = "; ".join(parts)
    # 立即带登录态补取 __sub_user_infos__（保存所选年级上下文），否则 xyks 业务接口(match)会 401
    extra, _ = fetch_account_full(login_cookie)
    if extra:
        login_cookie = merge_cookie(login_cookie, extra)
    # 补 PK 业务 keystone(ks_*/设备级凭证)：leo-game-pk match 等接口必需，缺了会 401
    login_cookie = ensure_pk_cookie(login_cookie)
    return login_cookie, None


# ---- 本周荣誉榜（手机端 PK榜·本周荣誉榜，分数旁闪电图标）----
# 真值来源：GET /leo-star/android/exercise/rank/pre-fetch → data.curWeekScore / curRank
HONOR_PATH = "/leo-star/android/exercise/rank/pre-fetch"


# ---- 荣誉榜等级：curWeekRankLevel 数值 -> 名称 ----
# 只保留【已实证】的档位，不把第三方攻略的说法当定论（小猿口算不是游戏，别套王者段位叫法）。
# 实证来源（三条互相印证）：
#   1) Lv300 且 curRank=6 时，手机界面 dump 出「黄金等级」第6名  → 300=黄金
#   2) 同一界面"本周前25名同学即将晋升钻石等级" → 高一档 400=钻石
#   3) 同一界面"以下同学即将下降白银等级"       → 低一档 200=白银
#   4) App 资源 medal-qingtong / medal-baiyin / medal-huangjin → 100=青铜
#   5) 独立产品拆解文："排行榜分为青铜、白银等多个等级……每周前三十名晋升、45名之后下降"
# ⚠️ 500/600 未实证：游戏攻略站称"星耀-王者"，但小猿口算非游戏，疑为套用叫法，故不写死；
#    遇到时按 Lv{数值} 显示，待你在 App 里见到真实文案后再补。
RANK_LEVELS = {100: "青铜", 200: "白银", 300: "黄金", 400: "钻石"}


# ---- PK 段位（称号）：来自 H5 bundle pk-config.js 的官方枚举 O.LEVEL1~LEVEL9，共 9 段 ----
# 与荣誉榜等级无关：这一套按累计胜场升级，最高「荣耀王者」
PK_TITLES = ["口算达人", "口算能手", "口算巧匠", "口算专家", "口算大侠",
             "口算精灵", "口算天才", "口算大王", "荣耀王者"]


def rank_level_name(level):
    """荣誉榜等级名；未知档位返回 Lv{level} 以免误判。"""
    try:
        lv = int(level)
    except (TypeError, ValueError):
        return "--"
    return RANK_LEVELS.get(lv, f"Lv{lv}")


def fetch_honor(cookie):
    """本周荣誉榜：curWeekScore=本周荣誉分(界面显示的那个数)、curRank=榜内名次。"""
    q = [("isBackground", "0")] + COMMON_Q + [("sign", gen_sign(int(time.time()), HONOR_PATH))]
    url = HOST + HONOR_PATH + "?" + "&".join(f"{k}={v}" for k, v in q)
    st, raw = http("GET", url, cookie)
    if st != 200:
        return None
    try:
        return (json.loads(raw.decode("utf-8")) or {}).get("data") or {}
    except Exception:
        return None


# ---- 双倍道具检测（影响每局加分）----
ITEM_STATUS_PATH = "/leo-star/android/exercise/item/status"


def fetch_item_status(cookie):
    """查询当前生效道具：双倍奖励 multiple=2 / duration(ms)。返回 dict 或 None。"""
    q = [("isBackground", "0")] + COMMON_Q + [("sign", gen_sign(int(time.time()), ITEM_STATUS_PATH))]
    url = HOST + ITEM_STATUS_PATH + "?" + "&".join(f"{k}={v}" for k, v in q)
    st, raw = http("GET", url, cookie)
    if st != 200:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def active_multiplier(cookie):
    """当前每局加分的倍率：有双倍道具则 2，否则 1。"""
    s = fetch_item_status(cookie) or {}
    if s.get("hasItem"):
        item = s.get("item") or {}
        return int(item.get("multiple") or 1)
    return 1


# ---- 榜分采集：区分"累计总分"与"本周榜分"两个口径 ----
RANK_PATH = "/leo-game-pk/android/game/rank"
ACHIEVE_PATH = "/leo-game-pk/android/math/pk/achievement"


def fetch_rank(cookie, school_id="0", region="1", country="0"):
    """榜接口：返回 userRank（含 showRank/capacity=本周榜分/title）与 period(周榜周期)。"""
    q = [("schoolId", school_id), ("region", region), ("biz", "2"),
         ("country", country), ("lat", "0"), ("lng", "0")] \
        + COMMON_Q + [("sign", gen_sign(int(time.time()), RANK_PATH))]
    url = HOST + RANK_PATH + "?" + "&".join(f"{k}={v}" for k, v in q)
    st, raw = http("GET", url, cookie)
    if st != 200:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def fetch_achievement(cookie, grade="1", user_id=None):
    """成就接口：totalScore=累计总分，winCount/loseCount/totalCount/winContinueCount（userId 必传）。"""
    if user_id is None:
        prof = fetch_profile(cookie) or {}
        user_id = prof.get("userId") or prof.get("primaryUserId")
    if not user_id:
        return None
    q = [("grade", str(grade)), ("userId", str(user_id))] \
        + COMMON_Q + [("sign", gen_sign(int(time.time()), ACHIEVE_PATH))]
    url = HOST + ACHIEVE_PATH + "?" + "&".join(f"{k}={v}" for k, v in q)
    st, raw = http("GET", url, cookie)
    if st != 200:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def fetch_history(cookie, limit=10):
    """对局历史：每局 capacity(该局得分)/pkResult/pointName。"""
    path = "/leo-game-pk/android/math/pk/history"
    q = [("cursorTime", "0"), ("limit", str(limit))] \
        + COMMON_Q + [("sign", gen_sign(int(time.time()), path))]
    url = HOST + path + "?" + "&".join(f"{k}={v}" for k, v in q)
    st, raw = http("GET", url, cookie)
    if st != 200:
        return None
    try:
        return json.loads(raw.decode("utf-8")).get("historyVO") or []
    except Exception:
        return None


def fetch_pk_home(cookie, grade):
    """拉取指定年级的口算PK首页数据：含 pointList、capacity(累计分)、title、weekWinCount、totalWinCount。"""
    q = [("grade", str(grade))] + COMMON_Q + [("sign", gen_sign(int(time.time()), PK_HOME_PATH))]
    url = HOST + PK_HOME_PATH + "?" + "&".join(f"{k}={v}" for k, v in q)
    st, raw = http("GET", url, cookie)
    if st != 200:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def pk_points(pk_home):
    """从 PK home 数据中取题型列表。"""
    return (pk_home or {}).get("pointList") or []


def fetch_homepage(cookie):
    """排行积分：data.curWeekExp；配套 curRank/curWeekRankLevel/todayObtainedPoints。"""
    path = "/leo-star/android/exercise/homepage"
    q = [("isBackground", "0")] + COMMON_Q + [("sign", gen_sign(int(time.time()), path))]
    url = HOST + path + "?" + "&".join(f"{k}={v}" for k, v in q)
    st, raw = http("GET", url, cookie)
    if st != 200:
        return None
    try:
        return json.loads(raw.decode("utf-8")).get("data") or {}
    except Exception:
        return None


def fetch_user_info(cookie):
    path = "/leo-alchemy-account/android/vip/user/info/v2"
    q = [("biz", "40"), ("biz", "41"), ("biz", "39"), ("isBackground", "0")] \
        + COMMON_Q + [("sign", gen_sign(int(time.time()), path))]
    url = HOST + path + "?" + "&".join(f"{k}={v}" for k, v in q)
    st, raw = http("GET", url, cookie)
    if st != 200:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def register_question_type(point_id, questions, registry=None, known=None):
    """对局自动补录题型名称：优先取首题 content 的题干前缀（比大小/乘法/加法…)"""
    reg = registry if registry is not None else POINT_REGISTRY
    lst = known if known is not None else KNOWN_POINTS
    key = str(point_id)
    if key in reg:
        return reg[key]
    name = key
    for q in questions[:3]:
        c = (q.get("content") or "").strip()
        if c:
            name = c[:20]
            break
    reg[key] = name
    if key not in [k["pointId"] for k in lst]:
        lst.append({"pointId": key, "name": name})
    return name


# ---- 真机伴随请求（模拟手机端会话的设备指纹行为，降低被识别概率）----
def send_device_companion(cookie):
    """模拟手机端启动/会话时的伴随请求：设备证书 + OAID证书 + 设备同步。
    真机每次会话都会打这些；电脑端补上以尽量贴近真机。返回成功计数。"""
    ok = 0
    for p in ("/leo-mis/android/conf/cert", "/leo-mis/android/conf/oaid-cert"):
        try:
            q = list(COMMON_Q) + [("sign", gen_sign(int(time.time()), p))]
            st, _ = http("GET", HOST + p + "?" + "&".join(f"{k}={v}" for k, v in q), cookie)
            if st == 200:
                ok += 1
        except Exception:
            pass
    try:
        p = "/leo-msg/android/sync/du"
        q = [("did", "DUcQeOjU71a2CBsqifH5VYmGHNyI2E4i8tg2"), ("sessionId", ""), ("lid", "0")]
        q += list(COMMON_Q) + [("sign", gen_sign(int(time.time()), p))]
        st, _ = http("POST", HOST + p + "?" + "&".join(f"{k}={v}" for k, v in q), cookie)
        if st == 200:
            ok += 1
    except Exception:
        pass
    return ok


if __name__ == "__main__":
    ck = grab_cookie()
    print("COOKIE LEN:", len(ck) if ck else 0)
    if ck:
        hp = fetch_homepage(ck)
        print("homepage:", hp if hp else None)
        ui = fetch_user_info(ck)
        print("user:", (ui or {}).get("name"), (ui or {}).get("grade"))