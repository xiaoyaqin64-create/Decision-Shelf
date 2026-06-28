# Decision Shelf｜决策书架

Decision Shelf 是一个本地运行的个人内容库与日常决策工具。你可以把想看的电影、想读的书、想听的专辑和想玩的游戏放进书架，再根据当前时间、精力、心情和偏好，从全部候选中选出此刻最适合的一项。

应用采用“规则过滤与本地评分优先，DeepSeek 负责理解和解释”的方式：时间不足、已经完成或今天不想体验的内容会先被排除，AI 不会绕过规则擅自改变排序。

## 主要功能

- 电影、书籍、专辑和游戏四类独立书架。
- V3.2 现代精装书脊界面：实体木书架、响应式自动分层、悬浮展开海报。
- 通过 TMDb、Open Library 和 MusicBrainz 搜索并半自动填写卡片。
- DeepSeek 补充受控类型标签、适合场景和推荐解释。
- 三种推荐范围：
  - `shelf_only`：只从已有书架推荐一项。
  - `shelf_first`：优先推荐书架内容；冷启动或匹配不足时补充 AI 探索建议。
  - `free`：不受书架限制，直接探索新内容。
- 开始、完成、跳过、今天不想、近期优先和移入回收站。
- 书籍与游戏支持手动记录每次投入时间和累计总时长。
- 决策历史、评分、感想以及长期偏好学习。
- 同分类重复标题或相同外部 ID 自动覆盖资料，同时保留状态、历史和时间记录。
- SQLite 本地持久化，数据库迁移前自动备份。
- DeepSeek 不可用时，书架评分仍可正常工作。

## 技术结构

```text
Vue 3 + TypeScript + Vite
            │
            ▼
      FastAPI + Pydantic
       │              │
       ▼              ▼
SQLite 决策核心    DeepSeek / 外部元数据源
```

- 后端：Python 3.11、FastAPI、Uvicorn、httpx、Pillow。
- 前端：Vue 3、TypeScript、Vite、Vue Router。
- 数据库：SQLite，启用 WAL 和 busy timeout，可供 CLI 与 Web 共用。
- AI：DeepSeek OpenAI 兼容 API。

## 快速开始

以下命令适用于 PowerShell。

### 1. 安装后端

```powershell
cd "项目地址"

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

如果已经在可用的 Python 3.11+ 环境中，可以直接执行最后一条安装命令。

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
notepad .env
```

最小配置如下：

```dotenv
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_JSON_RETRIES=1

TMDB_READ_ACCESS_TOKEN=
MUSICBRAINZ_CONTACT=

APP_HOST=127.0.0.1
APP_PORT=8000
# DECISION_SHELF_DB=data/decision_shelf.db
```

配置说明：

| 变量 | 用途 | 是否必需 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | AI 状态理解、标签补全、探索建议和自然语言解释 | 可选 |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | 使用 AI 时需要 |
| `DEEPSEEK_MODEL` | 模型名称，可通过环境变量切换 | 使用 AI 时需要 |
| `DEEPSEEK_JSON_RETRIES` | 空响应或无效 JSON 的自动纠正重试次数 | 可选 |
| `TMDB_READ_ACCESS_TOKEN` | 搜索电影、导演、片长、简介与海报 | 搜索电影时需要 |
| `MUSICBRAINZ_CONTACT` | MusicBrainz 合规 User-Agent 中的邮箱或网址 | 搜索专辑时需要 |
| `APP_HOST` / `APP_PORT` | Web 服务监听地址与端口 | 可选 |
| `DECISION_SHELF_DB` | 自定义 SQLite 文件路径 | 可选 |

Open Library 搜索书籍不需要 API Key。当前未接入 IGDB，因此游戏探索建议会标记为“AI 建议、未经外部验证”，保存前必须人工确认。

不要把填写了真实密钥的 `.env` 上传到 Git 仓库。

### 3. 初始化数据库

```powershell
python -m decision_shelf init
```

如需体验示例数据：

```powershell
python -m decision_shelf seed-demo
```

### 4. 构建并启动 Web 应用

```powershell
cd frontend
npm.cmd install
npm.cmd run build
cd ..

python -m decision_shelf web
```

浏览器打开：<http://127.0.0.1:8000>

再次启动前应先关闭原来的服务窗口。如果端口被占用，可以改用：

```powershell
python -m decision_shelf web --port 8001
```

## Web 使用流程

### 半自动加入卡片

1. 点击“加入新内容”。
2. 选择电影、书籍、专辑或游戏。
3. 输入至少两个字符搜索标题。
4. 选择外部候选并检查自动生成的草稿。
5. 可调用 DeepSeek 补充场景标签。
6. 修改后保存到书架。

卡片保存后不会重新加载整页，书架会保持在原来的浏览位置。

### CSV 批量导入

1. 在“加入新内容”页面切换到“批量导入”。
2. 下载 UTF-8 CSV 模板，填写分类、标题以及需要的选填字段。
3. 上传文件并检查错误行、重复项和外部资料候选。
4. 为有候选的条目选择正确结果或按 CSV 原文导入。
5. 确认后只会新增有效且不重复的卡片；单次最多 50 条、文件最大 256 KB。

电影、书籍和专辑可以在预览阶段匹配外部资料，CSV 中明确填写的值不会被候选覆盖。游戏或数据源不可用时会按原文导入。

### 开始一次决策

决策页可以输入：

- 当前可用时间。
- 当前精力。
- 允许推荐的内容类型。
- 类型细分标签。
- 想要轻松、专注、灵感、挑战、沉浸等场景。
- 一段自由状态描述。
- 推荐范围：只看书架、书架优先或自由探索。

本地引擎会完成硬过滤和全量评分，DeepSeek 只负责理解自由描述、生成探索候选和解释最终结果。

### 反馈和学习

- `开始`：卡片进入进行中，小幅增加相关偏好。
- `完成`：卡片进入已完成书架，可记录评分和感想。
- `跳过`：只在七天内降低该内容的推荐权重。
- `今天不想`：当天不再推荐，次日恢复。
- `近期优先`：提高有限的行为修正权重。
- `移入回收站`：退出普通书架与推荐，可恢复或永久删除。

所有长期偏好权重限制在 `-5～5`，永久删除单张卡片不会被推断为讨厌整个分类。

## 命令行使用

CLI 与 Web 使用同一个数据库。

```powershell
# 初始化和示例数据
python -m decision_shelf init
python -m decision_shelf seed-demo

# 卡片管理
python -m decision_shelf card add
python -m decision_shelf card list
python -m decision_shelf card list --category movie --status todo
python -m decision_shelf card show movie_inception
python -m decision_shelf card edit movie_inception

# 决策
python -m decision_shelf decide
python -m decision_shelf decide --minutes 180 --energy high --categories movie,album --preferences "科幻,摇滚" --moods "震撼,灵感" --text "今晚很清醒" --no-ai

# 反馈
python -m decision_shelf action movie_inception start --session-id 1
python -m decision_shelf action movie_inception complete --session-id 1 --rating 5 --review "很费脑，但正合适"
python -m decision_shelf action movie_inception skip
python -m decision_shelf action movie_inception not-today
python -m decision_shelf action movie_inception prioritize
python -m decision_shelf action movie_inception remove

# 历史与长期偏好
python -m decision_shelf history --limit 20
python -m decision_shelf prefs show
python -m decision_shelf prefs reset
```

可以通过全局参数临时使用另一个数据库：

```powershell
python -m decision_shelf --db work/test.db seed-demo
```

## 本地数据

默认数据库位置：

```text
data/decision_shelf.db
```

卡片、决策历史、反馈、偏好、AI 探索建议和书籍/游戏时间记录都保存在该 SQLite 文件中。应用重启不会清空数据。

数据库结构升级前会在同一目录生成时间戳备份，例如：

```text
decision_shelf.db.v3-20260628-103000.bak
```

如需手动备份，在服务停止后复制 `data/decision_shelf.db` 及同目录的 `-wal`、`-shm` 文件即可。

## 开发模式

打开两个 PowerShell 窗口。

后端：

```powershell
python -m decision_shelf web --reload
```

前端：

```powershell
cd frontend
npm.cmd run dev
```

开发界面位于 <http://127.0.0.1:5173>，Vite 会将 `/api` 请求代理到 `127.0.0.1:8000`。

生产构建由 FastAPI 直接托管 `frontend/dist`。

## 测试

```powershell
# Python 全量测试
python -m unittest discover -s tests -v

# Vue 单元测试、类型检查与生产构建
cd frontend
npm.cmd run test
npm.cmd run typecheck
npm.cmd run build
```

## 项目目录

```text
decision_shelf/          Python 决策引擎、数据库、CLI 与 FastAPI
decision_shelf/metadata/ 外部元数据源适配与缓存
frontend/src/            Vue 页面、组件和样式
frontend/dist/           生产构建文件
tests/                   Python 测试
data/                    本地 SQLite 数据库与迁移备份
.env.example             环境变量模板
pyproject.toml           Python 项目与依赖配置
```

## 常见问题

### 端口 8000 已被占用

错误通常类似：

```text
[Errno 10048] 通常每个套接字地址只允许使用一次
```

这表示已有一个服务占用了 8000 端口。可以关闭之前的服务窗口，或者换一个端口：

```powershell
python -m decision_shelf web --port 8001
```

### DeepSeek 返回格式无效

程序要求 DeepSeek 返回结构化 JSON。空响应、余额不足、模型网关异常、超时或模型附带非 JSON 文本都可能造成解析失败。

当前实现会自动进行一次纠正重试；仍然失败时：

- 普通书架决策继续使用本地评分和模板解释。
- AI 标签补全保留原草稿并显示错误。
- 自由探索不会伪造本地候选，会明确提示 DeepSeek 不可用。

可检查 `.env` 中的 Key、模型名称、账户余额和网络状态，并重启服务让配置重新加载。

### 修改 `.env` 后没有生效

环境变量在后端启动时读取。保存 `.env` 后需要停止并重新运行：

```powershell
python -m decision_shelf web
```

### 没有配置外部 API

手动建卡、已有书架管理、本地决策和反馈学习仍然可用；只会缺少对应的标题搜索、事实字段补全或 AI 探索能力。

## 当前边界

- 本机单用户，不含登录、云同步和公开部署配置。
- 暂未接入 IGDB、豆瓣、Markdown 和批量粘贴。
- 外部事实数据优先由元数据源验证；验证不足时不会为了凑数虚构内容。
