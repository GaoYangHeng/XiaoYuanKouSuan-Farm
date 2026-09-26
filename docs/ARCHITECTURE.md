# 架构与逆向链

## 一、请求签名链（从抓包到纯 Python）

```mermaid
flowchart TB
    A["📱 App / 本工具发起请求"] --> B["Java 层 ds/c5.b(path)<br/>注入 key=wdi4n2t8edr + 秒级 ts"]
    B --> C["JNI: e.zcvsd1wr2t(path, key, ts)"]
    C --> D["libRequestEncoder.so @0x414E8"]
    D --> D1["签名校验：APK 证书指纹<br/>不匹配 → 污染 path 首字节 → 417"]
    D --> D2["uidivmod(ts,60) → minute"]
    D2 --> D3["T410 编码器 @0x44280<br/>78 个 %lu 段无分隔拼接<br/>410 字节，仅依赖 minute"]
    D3 --> E["四轮 md5 链:<br/>h1=md5(P+K)<br/>h2=md5(P+K+h1+P)<br/>h3=md5(P+K+h1+P+h2+T410)<br/>sign=md5(P+K+h1+P+h2+T410+h3+K)"]

    E --> F["✅ 纯 Python 复现<br/>xyks/crack_sign（emulator 后端）"]
    D1 -.->|"仓库附带 xyks/so/<br/>（可选：APK 提取核验 / patch 脚本）"| F

    classDef key fill:#fff4d6,stroke:#e0a800,color:#000
    class E,F key
```

> T410 与 path/设备无关（实验验证），因此**同一分钟内所有接口共享同一份 T410**，签名计算可按分钟缓存。

## 二、内容加密链（contentcoder）

```mermaid
flowchart LR
    RAW["明文 JSON"] --> G["gzip 压缩"] --> X["XOR 固定密钥流<br/>ec_keystream.bin 32KB<br/>out[i]=in[i]^KS[i%len]"]
    X --> NET["HTTP body（自逆，加解密同一函数）"]
    NET --> X2["XOR 同密钥流"] --> G2["gzip 解压"] --> OUT["明文"]
```

纯 Python 实现见 `xyks/crack_sign/ec_pure.py`（CPython / MicroPython 双端可跑）。

## 三、一局的完整数据流

```mermaid
sequenceDiagram
    participant F as farm_solo
    participant E as core_engine
    participant S as sign/emulator
    participant C as ec_pure
    participant SV as 服务端

    F->>E: complete_pk_round(pointId)
    E->>S: sign(ts, match_path)
    S-->>E: sign
    E->>SV: POST match/v2
    SV-->>E: 加密对局包
    E->>C: run_e_c + gzip → 题目/答案
    Note over E: 模拟做题 6s + 人类化轨迹
    E->>C: 答题卡 → gzip + XOR
    E->>SV: PUT submit（octet-stream）
    SV-->>E: 200
    E->>SV: GET detail → 胜负/批改
    F->>E: fetch_honor → 周荣誉分
```

## 四、模块地图

```mermaid
mindmap
  root((xyks/))
    crack_sign/
      core_engine.py 引擎
      farm_solo.py 刷分循环
      emulator.py 签名模拟 Unicorn
      ec_pure.py 加解密
      login136.py 登录入口
      pc_pk_round.py HTTP 基础
    mod_apk/work/
      login_sms.py 短信登录协议
    so/ 用户自放签名 so
    apply_server.py Linux 路径适配
    web_status.py 状态页
  入口层
    xyks_ai.py AI JSON CLI
    xyks_tui.py 仪表盘
    app.py 魔搭入口
```
