FROM python:3.11-slim

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    unicorn pyelftools pycryptodome

WORKDIR /root/xyks
COPY xyks/ /root/xyks/
# cookie 注入：构建前把 login136.json 放到 xyks/crack_sign/（已被 .gitignore，不会入库）
# 签名 so 已随仓库附带于 xyks/so/，随 COPY 进镜像

EXPOSE 8080
ENTRYPOINT ["bash", "/root/xyks/entry.sh"]
