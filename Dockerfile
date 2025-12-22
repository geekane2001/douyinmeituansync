# 使用 Python 3.10 slim 版本基础镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装 Node.js 和 Tk 支持库
RUN apt-get update && apt-get install -y \
    curl \
    libtk8.6 \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件到容器
COPY . /app

# 安装 Python 依赖（关键修复：使用 python -m pip 避免 apt 装的 python3 干扰）
RUN python -m pip install --no-cache-dir -r requirements.txt

# 设置 Python 输出不缓冲，UTF-8 编码
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

# 暴露 Gradio 默认端口
EXPOSE 7860

# 启动命令
CMD ["python", "main.py"]
