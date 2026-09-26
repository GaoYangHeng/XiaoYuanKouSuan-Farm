# -*- coding: utf-8 -*-
# 上传部署包到魔搭 Studio 并触发部署
# 用法: MS_TOKEN=ms-xxx XYKS_REPO=your-name/your-studio python ms_push.py
import os
import sys

from modelscope_hub import HubApi

TOKEN = os.environ.get("MS_TOKEN", "")
REPO = os.environ.get("XYKS_REPO", "your-name/your-studio")
# 上传仓库根（app.py / Dockerfile / requirements.txt / xyks/ 都在根下）
FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if not TOKEN:
    print("请设置环境变量 MS_TOKEN（https://modelscope.cn/my/access/token）")
    sys.exit(1)

api = HubApi(token=TOKEN)
print("whoami:", api.whoami())

print("uploading...")
r = api.upload_folder(REPO, "studio", FOLDER, commit_message="xyks farm deploy")
print("upload result:", str(r)[:300])

print("deploying...")
d = api.deploy_repo(REPO, "studio")
print("deploy result:", str(d)[:300])
