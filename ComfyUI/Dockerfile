FROM python:3.11-slim

# 换阿里云 apt 镜像（国内服务器必须）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install torch torchvision torchaudio \
    -i https://pypi.tuna.tsinghua.edu.cn/simple/

COPY requirements.txt .
RUN pip install -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

RUN pip install pymysql redis openai google-genai volcengine-python-sdk oss2 bcrypt PyJWT \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

EXPOSE 8188
CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--cpu"]
