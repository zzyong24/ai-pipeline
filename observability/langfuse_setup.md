# Langfuse 自部署指南

## 前置条件

- Docker + Docker Compose 已安装
- 至少 2GB 可用内存

## 步骤

### 1. 克隆 Langfuse 仓库

```bash
git clone https://github.com/langfuse/langfuse.git
cd langfuse
```

### 2. 启动服务

```bash
docker compose up -d
```

服务会在后台启动，包含：
- Langfuse Web UI (端口 3000)
- PostgreSQL (端口 5432)

### 3. 初始化

浏览器访问 `http://localhost:3000`，按提示注册管理员账号。

### 4. 创建项目并获取 Keys

1. 登录后点击 "New Project"
2. 进入项目 Settings → API Keys
3. 点击 "Create new API keys"
4. 复制 Public Key 和 Secret Key

### 5. 配置 .env

在 `ai-pipeline/01-video-md/.env` 中添加：

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx
LANGFUSE_HOST=http://localhost:3000
```

### 6. 验证

```bash
cd ai-pipeline
python3 -c "
import os
os.environ['LANGFUSE_PUBLIC_KEY'] = 'pk-lf-xxx'
os.environ['LANGFUSE_SECRET_KEY'] = 'sk-lf-xxx'
os.environ['LANGFUSE_HOST'] = 'http://localhost:3000'
from subgraphs.shared.observability import get_langfuse
lf = get_langfuse()
print(f'Langfuse client: {lf}')
"
```

## 生产环境

如需云端部署，可使用 Langfuse Cloud: https://cloud.langfuse.com

配置方式相同，只需将 `LANGFUSE_HOST` 改为 `https://cloud.langfuse.com`。

## 故障排除

- **连接失败**：检查 Docker 是否正常运行 `docker ps`
- **数据丢失**：确保 PostgreSQL volume 挂载正确
- **Pipeline 不受影响**：即使 Langfuse 挂了，Pipeline 正常运行（observability 模块设计为 fail-safe）
