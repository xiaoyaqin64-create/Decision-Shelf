# Decision Shelf 桌面版发布说明

## 使用便携包

### Windows 10/11 x64

1. 下载 `Decision-Shelf-windows-x64.zip` 并完整解压。
2. 双击文件夹中的 `Decision Shelf.exe`。
3. 如果系统缺少 Microsoft Edge WebView2 Runtime，按照启动提示安装或修复后重新打开。

### Apple Silicon macOS

1. 下载 `Decision-Shelf-macos-apple-silicon.zip` 并解压。
2. 首版没有 Apple 签名。首次打开时按住 Control 点击 `Decision Shelf.app`，选择“打开”，再确认一次。
3. 后续可以像普通应用一样双击启动。

桌面包不包含任何 API Key。打开“设置”后填写自己的 DeepSeek Key、TMDb Read Access Token 和 MusicBrainz 联系信息。DeepSeek 与 TMDb 密钥分别保存在 Windows Credential Manager 或 macOS Keychain，页面和普通配置文件都不会回显密钥。

用户数据库与设置不会放在应用目录，因此替换整个便携应用文件夹不会丢失书架：

- Windows：`%LOCALAPPDATA%\Decision Shelf`
- macOS：`~/Library/Application Support/Decision Shelf`

“设置 → 数据备份”可以导出完整 `.dsbackup`，并在 Windows、macOS 与 Android 之间恢复书架、历史和偏好。API Key 不会进入备份；恢复前会自动保留当前数据库副本。

## 本地构建

Windows PowerShell：

```powershell
.\scripts\build_windows.ps1
```

Apple Silicon macOS：

```bash
bash scripts/build_macos.sh
```

脚本会安装桌面构建依赖、运行 Python/Vue 测试、构建前端、生成图标并在 `release/` 下创建便携 ZIP。

## GitHub 发布

- 在 Actions 中手动运行 `Desktop builds`，可分别下载两个构建产物。
- 推送 `v*` 标签（例如 `v0.3.1`）时，两个平台构建成功后会自动创建 GitHub Release 并附加 ZIP。
- 当前产物不做 Windows 或 Apple 商业代码签名；不要从不可信来源重新分发修改后的压缩包。
