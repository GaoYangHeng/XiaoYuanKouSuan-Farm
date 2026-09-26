#!/bin/bash
# 入口：后台 farm + 前台状态页（8080 提供日志/分数，兼作平台访问保活目标）
cd /root/xyks
nohup python -u crack_sign/farm_solo.py 10000 > /root/xyks/farm_stdout.log 2>&1 &
echo "farm started pid=$!"
python -u /root/xyks/web_status.py
