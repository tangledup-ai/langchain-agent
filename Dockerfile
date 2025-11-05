FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY pyproject.toml ./
COPY fastapi_server/requirements.txt ./fastapi_server/
COPY lang_agent/ ./lang_agent/
COPY fastapi_server/ ./fastapi_server/

# download req files
RUN curl -o ./.env http://6.6.6.86:8888/download/resources/.env
RUN curl -o ./assets.zip http://6.6.6.86:8888/download/resources/assets.zip
RUN unzip assets.zip
RUN rm assets.zip

# 安装Python依赖
RUN pip install --no-cache-dir -r fastapi_server/requirements.txt
RUN pip install --no-cache-dir -e .

# 暴露端口
EXPOSE 8488

# 启动命令
CMD ["python", "fastapi_server/server_dashscope.py"]