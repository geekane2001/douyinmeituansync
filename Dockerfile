# 使用 Python 3.10 基础镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装 Node.js (用于运行 sign_generator.js) 和基础支持库
RUN apt-get update && apt-get install -y \
    curl \
    libtk8.6 \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 将当前目录下的所有文件复制到容器中
COPY . /app

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 设置环境变量，确保 Python 输出不会被缓冲，且字符编码为 UTF-8
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

# Gradio 默认端口是 7860
EXPOSE 7860

# 启动命令
CMD ["python", "main.py"]
