# Decision Shelf

一个本地运行、规则透明、可从反馈中学习的个人活动决策应用。它提供命令行和 Web 两种入口，支持半自动补全电影、书籍、专辑元数据，以及书架不足时的 AI 探索推荐。

Web 版提供独立分类书架、主题色伸缩书脊、批量导入、分类完成收藏馆、回收站、可审计 AI 补全、书籍/游戏投入时间和同类同标题自动覆盖。数据库升级前会自动生成带时间戳的备份。

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

## 桌面应用

发布页提供无需安装 Python 或 Node.js 的便携桌面版：

- Windows 10/11 x64：解压 `Decision-Shelf-windows-x64.zip`，双击 `Decision Shelf.exe`。
- Apple Silicon macOS：解压 `Decision-Shelf-macos-apple-silicon.zip`。首版未签名，第一次需按住 Control 点击应用并选择“打开”。

每位用户在应用内“设置”页面填写自己的 DeepSeek 与 TMDb 凭据。密钥保存在 Windows Credential Manager 或 macOS Keychain，不会打入应用、写入数据库或显示在页面中。用户数据保存在系统应用数据目录，替换便携应用文件夹不会丢失书架。

本地打包、系统要求与 GitHub Release 流程见 [桌面版发布说明](docs/DESKTOP_RELEASE.md)。

## Android 应用

Android 版使用原生 WebView + Chaquopy，在手机本地运行同一套 Python 决策逻辑与 SQLite 数据库。触屏书脊第一次点击展开、第二次进入详情，并提供底部导航和完整数据库备份。

Android 7.0 以上的 ARM64 手机可直接安装签名 APK。手机与桌面通过 `.dsbackup` 手动迁移书架、历史和偏好，API Key 始终留在各自设备的系统凭据库。构建与固定签名说明见 [Android 文档](docs/ANDROID.md)。

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
python -m decision_shelf action movie_inception complete --session-id 1 --rating 8.7 --review "很费脑，但正合适"
```

评分统一使用 `0～10` 分制，最多保留一位小数。已完成电影、书籍、专辑和游戏分别使用海报档案、完成书脊、黑胶收藏和游戏光盘陈列。

### AI 简介补全规则

- 已有简介永不覆盖。
- 已匹配外部条目时优先采用外部原始简介。
- 有可靠结构化事实时，AI 只能基于这些字段生成概述。
- 只有标题时仅生成不含具体人物、年份、数字或情节的保守草稿，并永久标记“AI 辅助·未核验”。
- 所有简介先进入编辑草稿，人工保存后才写入数据库；模型失败时保持为空，不生成虚假兜底文本。

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
