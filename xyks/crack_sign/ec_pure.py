# -*- coding: utf-8 -*-
# ec_pure.py — 纯 Python 复刻 libContentEncoder.so 的 e.c 变换（无 Unicorn 依赖）。
# 算法（已破解并验证）: out[i] = in[i] ^ KS[i]，自逆，加解密同一函数，长度不变。
# KS 为固定位置密钥流（已从全0输入经 Unicorn 实测提取并验证）。可双端运行(CPython / MicroPython)。
import sys, os
import gzip, zlib

_HERE = os.path.dirname(os.path.abspath(__file__))

# 内置 64B KS 头（用于快速自检）；完整 KS 从 ec_keystream.bin 加载
KS_HEAD = bytes([
    0xd4,0x39,0xa1,0xb7,0x29,0xe0,0xa4,0x6b,0xa0,0x1a,0x4a,0xa6,0x5b,0xc1,0x5d,0xc0,
    0x96,0xce,0xc6,0x60,0x0f,0x7b,0x37,0xae,0xb8,0x1a,0xc0,0x47,0x85,0x05,0xa3,0x4c,
    0x58,0x3d,0xa6,0x11,0x59,0xf8,0xce,0xa5,0x2f,0xe5,0x94,0xf0,0x87,0x8e,0x73,0xe5,
    0xaf,0x4b,0x73,0xd9,0xee,0x65,0xc3,0x5d,0x02,0xd6,0xcb,0xb0,0x5e,0x5e,0x17,0xa0,
])

_KS = None
_KS_LEN = 0


def _ensure_ks():
    global _KS, _KS_LEN
    if _KS is not None:
        return
    p = os.path.join(_HERE, "ec_keystream.bin")
    try:
        with open(p, "rb") as f:
            _KS = f.read()
    except Exception:
        _KS = KS_HEAD
    _KS_LEN = len(_KS)


def run_e_c(data):
    """自逆变换：out[i]=in[i]^KS[i%len]。加解密同一函数。"""
    _ensure_ks()
    n = len(data)
    out = bytearray(n)
    ksl = _KS_LEN
    for i in range(n):
        out[i] = data[i] ^ _KS[i % ksl]
    return bytes(out)


def decrypt(raw):
    gz = run_e_c(raw)
    return gzip.decompress(gz)


def encrypt(json_bytes):
    comp = gzip.compress(json_bytes, 1)
    return run_e_c(comp)


def encrypt_fixed(json_bytes, wbits=0):
    """与引擎一致的 gzip(level1)+XOR；wbits 预留。"""
    return encrypt(json_bytes)


if __name__ == "__main__":
    # 与旧 Unicorn 引擎交叉验证（仅 CPython）
    sys.path.insert(0, _HERE)
    import contentcoder as old
    _ensure_ks()
    print("KS len:", _KS_LEN)
    ok = True
    for j in range(15):
        raw = os.urandom(800)
        comp = gzip.compress(raw, 1)
        o = old.run_e_c(comp)
        m = run_e_c(comp)
        if o != m:
            ok = False
            print(f"trial{j} MISMATCH"); break
    print("encrypt == old Unicorn :", ok)
    back = decrypt(old.run_e_c(gzip.compress(b'{"x":1}', 1)))
    print("decrypt round roundtrip:", back)