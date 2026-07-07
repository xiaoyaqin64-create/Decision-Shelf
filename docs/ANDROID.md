# Decision Shelf Android

Android 版在应用内部运行 Python、FastAPI 和 SQLite，不需要云服务器。手机数据库位于 Android 私有应用目录，其他 App 无法读取；卸载会删除数据，使用“设置 → 数据备份”可导出 `.dsbackup`。

## 安装与升级

- 最低 Android 7.0（API 24），发行 APK 支持主流 64 位 ARM 手机。
- 首次安装需要允许当前文件来源安装应用。
- 后续使用同一固定 keystore 签名的 APK 可直接覆盖升级，书架数据会保留。
- `.dsbackup` 可在桌面版和 Android 版之间导入导出；备份包含书架、历史和偏好，不包含 API Key。

## 固定签名

在 Windows PowerShell 中运行：

```powershell
.\scripts\init_android_signing.ps1
```

脚本默认在 `%USERPROFILE%\.decision-shelf-signing\decision-shelf-release.jks` 创建固定签名。请将 keystore 和密码分开备份，绝不能提交到 Git。

GitHub Actions 需要四个仓库 Secrets：

- `ANDROID_KEYSTORE_BASE64`：keystore 文件的 Base64 内容
- `ANDROID_KEY_ALIAS`：默认 `decision-shelf`
- `ANDROID_STORE_PASSWORD`
- `ANDROID_KEY_PASSWORD`

## 本地构建

需要 JDK 17、Android SDK 35、Build Tools 35.0.0 和 Gradle 8.x。本机准备好环境变量后运行：

```powershell
.\scripts\build_android.ps1 -Debug
.\scripts\build_android.ps1
```

当前仓库的 GitHub Actions 会自动配置 Android 构建环境、运行模拟器测试、验证 APK 签名并生成 `Decision-Shelf-android-arm64.apk`。
