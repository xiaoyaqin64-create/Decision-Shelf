# Decision Shelf

一个本地运行、规则透明、可从反馈中学习的个人活动决策应用。它提供命令行和 Web 两种入口，支持半自动补全电影、书籍、专辑元数据，以及书架不足时的 AI 探索推荐。

V3.1 Web 版提供独立分类书架、Phigros 风格主题色伸缩书脊、自动增层、回收站、旧卡 AI 补全、分类受控标签、书籍/游戏手动投入时间和同类同标题自动覆盖。数据库升级前会自动生成带时间戳的备份。

## 环境

- Python 3.11+
- FastAPI、Uvicorn、httpx
- Node.js 20+ 与 npm（构建 Vue 前端）
- 可选：DeepSeek 与 TMDb 凭据

复制 `.env.example` 为 `.env` 并填写 Key，即可启用 DeepSeek：

```text
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
TMDB_READ_ACCESS_TOKEN=你的TMDb读取令牌
MUSICBRAINZ_CONTACT=你的联系邮箱或网址
```

没有 Key、网络超时或模型返回无效 JSON 时，程序会自动使用本地关键词和模板解释。

## Web 应用

首次安装和构建：

```powershell
cd "..."
python -m pip install -e .
cd frontend
npm.cmd install
npm.cmd run build
cd ..
python -m decision_shelf web
```

打开 <http://127.0.0.1:8000>。

开发模式需要两个 PowerShell 窗口：

```powershell
python -m decision_shelf web --reload
```

```powershell
cd frontend
npm.cmd run dev
```

Vite 开发界面位于 <http://127.0.0.1:5173>。

## 命令行快速上手

在项目根目录运行：

```powershell
python -m decision_shelf init
python -m decision_shelf seed-demo
python -m decision_shelf decide
```

也可以用参数快速测试，避免交互输入：

```powershell
python -m decision_shelf decide --minutes 180 --energy high --categories movie,album --preferences "被震撼,获得灵感" --text "今晚很清醒，想看点有创意的" --no-ai
```

对推荐结果记录行动：

```powershell
python -m decision_shelf action movie_inception start --session-id 1
python -m decision_shelf action movie_inception complete --session-id 1 --rating 5 --review "很费脑，但正合适"
```

## 命令

```powershell
python -m decision_shelf card add
python -m decision_shelf card list
python -m decision_shelf card show movie_inception
python -m decision_shelf card edit movie_inception
python -m decision_shelf history
python -m decision_shelf prefs show
python -m decision_shelf prefs reset
```

数据库默认保存在 `data/decision_shelf.db`。可以通过全局参数覆盖：

```powershell
python -m decision_shelf --db work/test.db seed-demo
```

## 测试

```powershell
python -m unittest discover -s tests -v
cd frontend
npm.cmd run test
npm.cmd run build
```
