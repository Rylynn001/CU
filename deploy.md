# 部署文档

## 架构

```
用户浏览器 :80
    ↓
comfy-web (nginx)   静态文件 + 反向代理
    ↓ /api/* /ws → :8188
comfyui             ComfyUI + comfy_api_proxy
    ├── mysql
    └── redis
```

对外只暴露 80 端口。

---

## 服务器要求

| 项目 | 要求 |
|------|------|
| 系统 | Ubuntu 20.04 / 22.04 |
| 内存 | ≥ 16 GB |
| 磁盘 | ≥ 100 GB |
| 端口 | 80、22 |

---

## 部署步骤

### 1. 上传代码

```bash
git clone <your-repo-url> /opt/comfy
cd /opt/comfy
```

### 2. 安装 Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
```

### 3. 配置环境变量

```bash
nano /opt/comfy/ComfyUI/custom_nodes/comfy_api_proxy/.env
```

```env
DB_HOST=mysql
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=comfyui

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

OSS_ACCESS_KEY_ID=<AccessKey ID>
OSS_ACCESS_KEY_SECRET=<AccessKey Secret>
OSS_BUCKET_NAME=<Bucket 名称>
OSS_ENDPOINT=https://oss-cn-beijing.aliyuncs.com
```

> `DB_PASSWORD` 需与 `docker-compose.yml` 中 `MYSQL_ROOT_PASSWORD` 一致。

### 4. 上传模型文件

```bash
scp -r ./ComfyUI/models user@your-server-ip:/opt/comfy/ComfyUI/models
```

### 5. 启动服务

```bash
docker compose up -d --build
docker compose logs -f
```

---

## 安全组配置

| 端口 | 说明 |
|------|------|
| 22 | SSH（限制来源 IP） |
| 80 | HTTP |

不要开放 8188、3306、6379。

---

## 常用命令

```bash
# 查看状态
docker compose ps

# 查看日志
docker compose logs -f comfyui
docker compose logs -f comfy-web

# ComfyUI 代码更新后
docker compose restart comfyui

# comfy-web 代码更新后
docker compose up -d --build comfy-web

# 进入 MySQL
docker compose exec mysql mysql -uroot -p comfyui

# 停止（保留数据）
docker compose down

# 停止并清空数据库（慎用）
docker compose down -v
```
