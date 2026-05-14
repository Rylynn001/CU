# 云服务器部署文档

## 架构说明

```
用户浏览器
    │  HTTP :80
    ▼
comfy-web (nginx)       ← 前端静态文件 + 反向代理
    │  /api/* → :8188
    │  /ws    → :8188
    ▼
comfyui                 ← ComfyUI + comfy_api_proxy（GPU 直通）
    ├── mysql           ← MySQL 8.0
    └── redis           ← Redis 7
```

全部服务跑在 Docker Compose 里，**对外只暴露 80 端口**。

---

## 一、服务器要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu 20.04 / 22.04 |
| GPU | 不需要（生图走外部 API） |
| 内存 | ≥ 16 GB |
| 磁盘 | ≥ 100 GB（模型文件较大） |
| 开放端口 | 80（HTTP），22（SSH） |

---

## 二、上传代码

在本地执行，将整个 CU 目录上传到服务器：

```bash
scp -r ./CU user@your-server-ip:/opt/comfy
```

或者用 git：

```bash
ssh user@your-server-ip
git clone <your-repo-url> /opt/comfy
```

目标目录结构：

```
/opt/comfy/
  ComfyUI/
    Dockerfile
    models/          ← 模型文件（大，单独上传）
    custom_nodes/
      comfy_api_proxy/
        .env         ← 需要配置
  comfy-web/
    Dockerfile
    nginx.conf
  docker-compose.yml
  deploy.md
```

---

## 三、安装 Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

---

## 四、配置 comfy_api_proxy 环境变量

编辑 `.env` 文件：

```bash
nano /opt/comfy/ComfyUI/custom_nodes/comfy_api_proxy/.env
```

内容如下：

```
DB_HOST=mysql
DB_USER=root
DB_PASSWORD=123456
DB_NAME=comfyui

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

OSS_ACCESS_KEY_ID=<你的阿里云 AccessKey ID>
OSS_ACCESS_KEY_SECRET=<你的阿里云 AccessKey Secret>
OSS_BUCKET_NAME=<你的 Bucket 名称>
OSS_ENDPOINT=https://oss-cn-beijing.aliyuncs.com
```

> 注意：`DB_HOST` 填 `mysql`，`REDIS_HOST` 填 `redis`，这是 Docker 内部服务名，不是 localhost。
> `DB_PASSWORD` 需要与 docker-compose.yml 中 `MYSQL_ROOT_PASSWORD` 保持一致。

---

## 五、上传模型文件

模型文件较大，单独上传：

```bash
scp -r ./ComfyUI/models user@your-server-ip:/opt/comfy/ComfyUI/models
```

---

## 六、启动所有服务

```bash
cd /opt/comfy
docker compose up -d --build
```

首次构建需要较长时间（下载 CUDA 镜像、安装 PyTorch 等）。

查看启动进度：

```bash
docker compose logs -f
```

---

## 七、安全组配置

在云服务商控制台配置入站规则：

| 端口 | 协议 | 来源 | 说明 |
|------|------|------|------|
| 22 | TCP | 你的 IP | SSH |
| 80 | TCP | 0.0.0.0/0 | HTTP 访问前端 |

**不要开放** 8188、3306、6379 端口。

---

## 八、验证部署

```bash
# 检查所有容器状态
docker compose ps

# 测试前端
curl -I http://localhost

# 测试 API 代理
curl http://localhost/api/api-proxy/config

# 查看 ComfyUI 日志
docker compose logs -f comfyui
```

浏览器访问 `http://<服务器公网IP>` 即可使用。

---

## 九、常用运维命令

```bash
# 查看所有服务状态
docker compose ps

# 查看某个服务日志
docker compose logs -f comfyui
docker compose logs -f comfy-web

# 重启某个服务
docker compose restart comfyui
docker compose restart comfy-web

# 前端代码更新后重新构建
docker compose up -d --build comfy-web

# ComfyUI 代码更新后重新构建
docker compose up -d --build comfyui

# 全部重启
docker compose restart

# 进入 MySQL
docker compose exec mysql mysql -uroot -p comfyui

# 停止所有服务
docker compose down

# 停止并删除数据卷（慎用，会清空数据库）
docker compose down -v
```
