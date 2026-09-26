# -*- coding: utf-8 -*-
# 小猿口算 PC 短信登录：发验证码 + 验证码登录拿 token
# 链路来源（v52 反编译）：
#   host    = mg/h.A(mg/h.x(z())) = https://ape-api.yuanfudao.com
#   发码    = YtkApiService.smsVerify  POST /verifier/android/sms   Form: phone=RSA(phone)
#   登录    = YtkApiService.smsLogin   POST /accounts/android/safe/login  Form: phone/verification/autoRegister
#   RSA     = kv/k.b(): RSA/ECB/PKCS1PADDING(BC), 公钥硬编码, 输出 Base64(NO_WRAP)
#   YFD_U   = kv/f.a(ds/i3.d()): MD5(伪设备串) 前 8 字节大端 long
#   sign    = ds/c5.b(path) → 4 轮 md5 链，P' = chr(path[0]-1)+path[1:]，minute = str(ts//60)
#             （sign.py 自测真机样本 匹配=True；cq/o 把 sign 加进 query）
#   UA      = vp/c.b(): Leo/<ver> (<brand+model>; Android <rel>; Scale/<density>)
import hashlib, struct, base64, json, time, uuid, sys, os, urllib.request, urllib.parse, urllib.error
from email.utils import parsedate_to_datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KEY = "wdi4n2t8edr"
HOST = "https://ape-api.yuanfudao.com"
PHONE = os.environ.get("XYKS_PHONE", "13800138000")
RSA_PUB_B64 = ("MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDSovT1rrwzrGoMCFb6z8e+5lzVdAD5o8krGIwdfxrVE2OnMijUZdkQk7e"
               "tPJvZ2JOVXghthAGUUJkDUE8n2ZMNFKPjMrQJI49ewVzqWOKOvgU6Iu60Sn0xpeietP1wWXBkszdV1WfNBJUo2hhPDnIPM"
               "GzzdfLW5rMu+tczeUriJQIDAQAB")
UA = "Leo/3.141.1 (samsungSM-G9910; Android 14; Scale/2.75)"

COMMON = {
    "_productId": "611",
    "platform": "android34",
    "version": "3.141.1",
    "vendor": "tencent",
    "deviceCategory": "phone",
    "av": "5",
    "webviewVersion": "131",
    "whRatio": "2.06",
    "isBackground": "0",
}


def md5_hex(s):
    if isinstance(s, str):
        s = s.encode()
    return hashlib.md5(s).hexdigest()


def calc_sign(path, ts):
    """复刻 sign.py（真机 5/5 命中）：P' 首字节 -1，minute=ts//60"""
    pm = chr((ord(path[0]) - 1) & 0xFF) + path[1:]
    minute = str(ts // 60)
    s = pm + KEY
    h1 = md5_hex(s)
    s = pm + KEY + h1 + pm
    h2 = md5_hex(s)
    s = pm + KEY + h1 + pm + h2 + minute
    h3 = md5_hex(s)
    return md5_hex(pm + KEY + h1 + pm + h2 + minute + h3 + KEY)


def calc_udid():
    """复刻 ds/i3.d()：伪设备串 → UUID v3 → MD5 前 8 字节大端 long"""
    s1 = "armeabi-v7a_armeabi"          # CPU_ABI_CPU_ABI2
    s2 = "qcom_sdmg7101_a14x_qcom"      # HARDWARE_BOARD_DEVICE_PRODUCT
    s3 = "samsung_SM-G9910_samsung"     # BRAND_MODEL_MANUFACTURER
    s4 = "null_R58N0XXXXX_0123456789abcdef"  # "null"+_SERIAL+_androidId
    combined = "|".join([s1, s2, s3, s4])
    u = str(uuid.UUID(bytes=hashlib.md5(combined.encode()).digest(), version=3))
    h = md5_hex(u)
    return struct.unpack(">Q", bytes.fromhex(h)[:8])[0]


def rsa_encrypt_phone(phone):
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5
    key = RSA.import_key(base64.b64decode(RSA_PUB_B64))
    return base64.b64encode(PKCS1_v1_5.new(key).encrypt(phone.encode())).decode()


def server_ts():
    """对齐服务器时间（cq/l 的 Date 头逻辑）：取 ape-api 响应 Date"""
    try:
        req = urllib.request.Request(HOST + "/", method="GET",
                                     headers={"User-Agent": UA})
        try:
            r = urllib.request.urlopen(req, timeout=10)
            d = r.headers.get("Date")
            r.close()
        except urllib.error.HTTPError as e:
            d = e.headers.get("Date")
        if d:
            ts = parsedate_to_datetime(d).timestamp()
            print("[时间对齐] 服务器时间:", d, "偏移 %.1fs" % (ts - time.time()))
            return int(ts)
    except Exception as e:
        print("[时间对齐失败] 用本地时间:", e)
    return int(time.time())


def api_post(path, fields, label):
    ts = server_ts()
    q = dict(COMMON)
    q["YFD_U"] = str(calc_udid())
    q["sign"] = calc_sign(path, ts)
    url = HOST + path + "?" + urllib.parse.urlencode(q)
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", UA)
    print("\n[%s] POST %s" % (label, url))
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
            print("HTTP", r.status)
            print("Set-Cookie:", r.headers.get_all("Set-Cookie"))
            print(body[:4000])
            return r.status, body
    except urllib.error.HTTPError as e:
        print("HTTP", e.code)
        print(e.read().decode("utf-8", "replace")[:4000])
        return e.code, ""
    except Exception as e:
        print("网络错误:", e)
        return -1, ""


def send_code():
    enc = rsa_encrypt_phone(PHONE)
    print("[发码] RSA(phone) =", enc)
    return api_post("/verifier/android/sms", {"phone": enc}, "发验证码")


def do_login(code):
    # wo/d.smali L630-638: phone 与 verification 均经 kv/k.b() RSA 加密，autoRegister=true
    enc = rsa_encrypt_phone(PHONE)
    return api_post("/accounts/android/safe/login",
                    {"phone": enc, "verification": rsa_encrypt_phone(code),
                     "autoRegister": "true"}, "登录")


if __name__ == "__main__":
    udid = calc_udid()
    print("[设备] YFD_U =", udid)
    if len(sys.argv) >= 2:
        st, body = do_login(sys.argv[1])
    else:
        st, body = send_code()
    out = {"status": st, "body": body}
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_resp.json"),
              "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
