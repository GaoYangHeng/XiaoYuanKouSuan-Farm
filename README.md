# XiaoYuanKouSuan-Farm

> 小猿口算 PK 荣誉分自动刷分工具：请求签名 / 内容加密的纯 Python 还原 + 配额感知的刷分循环 + 人（TUI）/ AI（JSON CLI）双驱动接口。
>
> 🔐 逆向原理与改包 APK 见姊妹仓库 **[XiaoYuanKouSuan-1s-Answer](https://github.com/GaoYangHeng/XiaoYuanKouSuan-1s-Answer)**（技术报告、so patch、smali 工程都在那边，本仓库不重复收录，只引用）。

## 项目定位

```mermaid
mindmap
  root((XiaoYuanKouSuan<br/>Farm))
    🧰 工具
      match→答题→加密submit→查分 闭环
      配额感知节奏 10min/局稳态
      本机 / Docker / 魔搭 三套部署
    📚 教材
      Native 签名链 → 纯 Python 复现
      contentcoder 加密 → XOR 查表
      方法论见 1s-Answer TECHNICAL_REPORT
    🤖 AI 协作
      xyks_ai.py 结构化 JSON 输出
      诊断 / 单局 / 日志 / 控制
      人看 xyks_tui.py 仪表盘
```

## 总体架构

```mermaid
flowchart TB
    subgraph CLI["🖥 人机入口"]
        TUI["xyks_tui.py<br/>终端仪表盘（零依赖）"]
        AI["xyks_ai.py<br/>AI 操作接口（JSON 输出）"]
    end

    subgraph CORE["⚙️ 核心库 xyks/crack_sign"]
        FARM["farm_solo.py<br/>刷分循环 · 配额节奏 · 零风暴退避"]
        ENG["core_engine.py<br/>match → 答题卡 → 加密 submit → detail"]
        SIGN["emulator.py + sign<br/>四轮 md5 链 + T410 时间流<br/>（Unicorn 模拟 so / 纯函数双后端）"]
        CRYPTO["ec_pure.py<br/>contentcoder XOR 自逆加解密"]
    end

    subgraph DEP["🚀 部署"]
        WIN["本机 pythonw<br/>无窗口 + 开机自启"]
        DOCKER["Dockerfile"]
        MS["魔搭 Studio<br/>app.py + requirements.txt"]
    end

    SERVER["☁️ xyks.yuanfudao.com<br/>10 分钟配额节流"]

    TUI --> FARM
    AI --> FARM
    AI --> ENG
    FARM --> ENG --> SIGN & CRYPTO
    ENG --> SERVER
    DEP -.承载.-> FARM

    classDef key fill:#fff4d6,stroke:#e0a800,color:#000
    class FARM,ENG,SIGN key
```

## 配额模型（实测结论）

```mermaid
flowchart LR
    A["成功一局 +15"] --> B{"配额桶<br/>约 10 分钟回填 1 层"}
    B -->|"静默 10.5 分钟后<br/>一发命中"| A
    B -.->|"密集探测 ❌<br/>400 风暴会升级限流"| C["惩罚窗口<br/>数分钟不解冻"]
    D["突发桶攒满<br/>（停刷 1-3 天）"] -.->|"首跑可能出现"| E["快档 61s/局连刷<br/>（每小时级，机制未全明）"]

    classDef ok fill:#e6ffed,stroke:#2da44e,color:#000
    classDef bad fill:#ffebe9,stroke:#cf222e,color:#000
    class A,E ok
    class C bad
```

> 详见 [docs/QUOTA.md](docs/QUOTA.md)：两层锁、solo/multi 共享配额、失败请求降权证伪等 6 条实测定论。

## AI 操作接口

```mermaid
flowchart LR
    AGENT["AI Agent"] -->|"xyks_ai.py status"| J1["{\"score\":3245,<br/>\"pace\":\"10.5min\",<br/>\"health\":\"ok\"}"]
    AGENT -->|"diagnose"| J2["{\"issues\":[],<br/>\"advice\":\"...\"}"]
    AGENT -->|"round --once"| J3["单局执行结果"]
    AGENT -->|"logs --tail 50"| J4["最近日志数组"]
    J1 & J2 & J3 & J4 --> AGENT
    AGENT -.->|"决策后写回"| CTRL["start / stop / 调参"]
```

| 命令 | 作用 | 退出码 |
|---|---|---|
| `xyks_ai.py status` | 分数/节奏/进程健康（JSON） | 0（advice 字段提示异常） |
| `xyks_ai.py score` | 仅查周荣誉分 | 0 成功 / 1 失败 |
| `xyks_ai.py round --once` | 手动跑一局（含逐步耗时） | 0 胜 / 1 失败 |
| `xyks_ai.py logs --tail N` | 最近日志（JSON 数组） | 0 |
| `xyks_ai.py diagnose` | 自动诊断 + 处理建议 | 0 无需处理 / 2 需人工 |
| `xyks_ai.py start / stop` | 本机常驻 farm 控制 | 0 |

## 快速开始

```bash
# 1) 依赖（Python ≥ 3.10）
pip install -r requirements.txt

# 2) 自备签名 so（版权原因不随仓库分发）
#    从官方 APK 提取：
unzip -j <小猿口算.apk> "lib/armeabi-v7a/libRequestEncoder.so" -d xyks/so/
#    签名校验 patch 脚本：见 1s-Answer 仓库 opensource/snippets/sign/

# 3) 登录拿 cookie（短信验证码）
XYKS_PHONE=138xxxx  XYKS_SMS_CODE=xxxxxx python xyks/crack_sign/login136.py
#    已有 cookie？直接 cp xyks/crack_sign/login136.example.json xyks/crack_sign/login136.json 填入

# 4) 跑一局验证
python xyks_ai.py round --once

# 5) 常开刷分
python xyks_tui.py        # 人：仪表盘
# 或
python xyks_ai.py start   # AI/后台
```

部署矩阵（本机 / Docker / 魔搭）见 [docs/DEPLOY.md](docs/DEPLOY.md)，架构细节见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 声明

本项目为安全研究与教育用途的逆向工程与自动化笔记，详见 [DISCLAIMER.md](DISCLAIMER.md)（完整声明引用自 [1s-Answer](https://github.com/GaoYangHeng/XiaoYuanKouSuan-1s-Answer/blob/main/opensource/DISCLAIMER.md)）。PK 对局中有真人玩家，自动化会直接影响他人体验，请自行评估使用场景。
