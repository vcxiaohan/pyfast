# api 和 worker 用同一个镜像，只是启动命令不同：默认跑 api，compose 里给 worker 换成 python worker.py。
# 代码和依赖完全一样，分成两个镜像只会多一份构建和版本管理。

FROM python:3.13-slim

# 国内构建默认用阿里云 PyPI 镜像；GitHub Actions 的机器在国外，构建时传 --build-arg PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# PYTHONUNBUFFERED：日志立刻输出，不在缓冲区里攒着，docker logs 才能实时看到
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先只复制 requirements.txt：依赖没变时这一层直接用缓存，改代码不用重新装依赖
COPY requirements.txt .
RUN pip install --index-url "$PIP_INDEX_URL" -r requirements.txt

COPY . .

# 不用 root 运行，万一被攻破，攻击者拿到的权限也有限
RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000

# 健康检查写在 compose 里而不是这里：镜像里的 HEALTHCHECK 对 worker 也生效，worker 不监听端口，会被一直判成不健康

# 必须用 JSON 数组的写法直接启动进程，docker stop 的 SIGTERM 才能发到 uvicorn，优雅退出才会执行
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
