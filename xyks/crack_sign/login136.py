# -*- coding: utf-8 -*-
# 短信验证码登录并保存 cookie 到 login136.json，随后验证登录态与积分字段。
# 用法: XYKS_PHONE=138xxxx XYKS_SMS_CODE=xxxxxx python login136.py
# 凭证不入库：手机号/验证码仅从环境变量读取；login136.json 已在 .gitignore
import sys, json, time, os
sys.stdout = sys.stderr
_D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _D)
sys.path.insert(0, os.path.join(os.path.dirname(_D), "mod_apk", "work"))
import core_engine as C
import login_sms as _L

PHONE = os.environ.get("XYKS_PHONE", "")
CODE = os.environ.get("XYKS_SMS_CODE", "")

# 第一段：--send-code 仅触发下发短信验证码（用户随后把 6 位码报回给操作者）
if "--send-code" in sys.argv:
    if not PHONE:
        print("请设置环境变量 XYKS_PHONE 后再执行 --send-code")
        sys.exit(1)
    st, msg = C.sms_send_code(PHONE)
    print("send_code http=%s resp=%s" % (st, msg))
    print("OK: 短信已发出，请等待用户回传 6 位验证码，再执行：")
    print("    XYKS_PHONE=... XYKS_SMS_CODE=<验证码> python login136.py")
    sys.exit(0 if st == 200 else 1)

if not PHONE or not CODE:
    print("请设置环境变量 XYKS_PHONE / XYKS_SMS_CODE")
    print("（首次登录先执行 --send-code 下发短信）")
    sys.exit(1)

ck, err = C.sms_login(PHONE, CODE)
if err:
    print("登录失败:", err); sys.exit(1)
print("登录成功 cookie len=", len(ck))
# 找userid
kv = {}
for p in ck.split(";"):
    p = p.strip()
    if "=" in p:
        k, v = p.split("=", 1); kv[k] = v
print("userid=", kv.get("userid"))
json.dump({"phone": PHONE, "cookie": ck},
          open(os.path.join(_D, "login136.json"), "w", encoding="utf-8"),
          ensure_ascii=False)
print("已保存 login136.json")


# 验证: 荣誉分 + 几个关键接口
def get(path, qextra=None):
    q = list(C.COMMON_Q)
    if qextra:
        q += qextra
    q.append(("sign", C.gen_sign(int(time.time()), path)))
    url = C.HOST + path + "?" + "&".join("%s=%s" % (k, v) for k, v in q)
    st, raw = C.http("GET", url, ck)
    try:
        return st, json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return st, None


st, d = get(C.HONOR_PATH, [("isBackground", "0")])
data = (d or {}).get("data") or {}
print("== pre-fetch:", {k: v for k, v in data.items()
                        if isinstance(v, (int, float)) or k in ("curRank", "curWeekScore")})

st, d = get("/leo-star/android/exercise/homepage", [("isBackground", "0")])
data2 = (d or {}).get("data") or {}
print("== homepage:", {k: v for k, v in data2.items() if isinstance(v, (int, float))})
