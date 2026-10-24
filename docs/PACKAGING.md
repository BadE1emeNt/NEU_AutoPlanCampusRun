# 发布与打包规划

> 当前 0.1.0 的发布物是**源码目录 + `.cmd`**。
> 目标：Windows 最终提供可双击的 EXE；后续再移植 Android APK。
> 本文记录可行路线、约束和发布检查项，避免把“Python 脚本”直接误当成可移植 App。

## 1. Windows EXE

### 推荐形态

- **one-folder**（`dist/CampusRun/CampusRun.exe` + 依赖目录），压缩为 zip；
- 可选 Inno Setup 做安装包；
- 不推荐单文件 `--onefile`：Tkinter/Tcl 每次解压慢、杀毒误报更高；
- 代码签名可选；没有签名时 Windows SmartScreen 可能提示“未知发布者”。

### PyInstaller 方案

- 入口：`packaging/launcher.py`（调用 `campusrun.cli.main` 或 GUI）；
- `--windowed`（GUI 无控制台）；另做一个 `CampusRun-console.exe` 便于排错；
- Tkinter/Tcl 由 PyInstaller hook 收集；不需要手工 `--add-data`；
- DPAPI、`%APPDATA%\CampusRun`、网络请求在 EXE 下保持原行为；
- 不打包 `research/`、`tests/`、`docs/`、抓包/令牌；
- 图标/版本信息放在 `packaging/`；
- 构建在干净 venv 中，避免把开发机路径带进去。

示意（后续会落成脚本）：

```bat
py -3 -m venv .venv-build
.venv-build\Scripts\python -m pip install pyinstaller
.venv-build\Scripts\pyinstaller --noconfirm --clean --windowed ^
  --name CampusRun --paths src packaging\launcher.py
```

### EXE 验收

- [ ] 在**没有 Python** 的干净 Windows 10/11 上双击可启动；
- [ ] 演示模式、账号登录、token 刷新、抓包备用、CSV 导出正常；
- [ ] DPAPI 保存/重启解密正常；
- [ ] 150% / 200% DPI 下界面不裁切；
- [ ] 杀毒软件扫描无误报（至少记录结果）；
- [ ] 卸载/删除数据目录行为明确；
- [ ] zip 内含 README（发行版）、版本号、SHA256。

## 2. Android APK

### 关键结论

**Tkinter 不能直接打包成 APK。** 当前 Windows UI 必须重写；可以复用协议、规划算法和数据模型。

### 路线对比

| 路线 | 复用 | 成本 | 适合 |
|---|---|---|---|
| **Kivy + python-for-android** | Python 核心/算法/协议可大量复用 | 中；UI 重写，WebView/Keystore 集成较麻烦 | 想保留 Python 技术栈 |
| **Flutter** | 协议/算法需移植到 Dart；文档可复用 | 中高；UI 原生体验好 | 长期维护、想要好 UI |
| **Kotlin + Jetpack Compose** | 协议/算法移植到 Kotlin；文档可复用 | 高；最原生 | 只做 Android、追求稳定 |
| **WebView 壳** | 直接加载现有 H5/网页版 | 低；但不是完整离线 App | 过渡验证 |

建议：**先 EXE，再决定 APK 路线**。如果要“尽快有 APK”，Kivy 最快；
如果要“长期可维护、界面像 App”，选 Flutter 或 Kotlin。

### APK 必须替换的实现

| Windows | Android |
|---|---|
| Tkinter UI | Kivy / Flutter / Compose |
| DPAPI | Android Keystore + EncryptedSharedPreferences |
| `%APPDATA%\CampusRun` | 应用私有目录 / Room / DataStore |
| `http.client` | OkHttp / Dart http / Ktor |
| `run.cmd` | APK 启动 Activity |
| 文件对话框/CSV | SAF / share intent |

### APK 登录注意

- CAS 登录可用 **WebView** 打开 `pass.neu.edu.cn`，完成“首次绑定邮箱/稍后绑定”更自然；
- 从 WebView 最终 URL 捕获 token；或继续用 HTTP + RSA（需移植 AES/RSA）；
- 密码不要注入 WebView JS 明文；优先让 WebView 自己处理；
- token/密码存 Android Keystore；
- 不要 `android:allowBackup=true` 默认备份凭据；
- 校园网/证书问题需要 network security config；
- 签名 APK：正式 keystore、`versionCode`/`versionName`、arm64-v8a。

### APK 验收

- [ ] 真机（非模拟器）安装、登录、刷新、规划；
- [ ] 首次绑定邮箱“稍后绑定”流程；
- [ ] 杀进程/重启后 token 恢复；
- [ ] 无 Python/无 Termux 依赖；
- [ ] 不申请无关权限（短信/通讯录/定位非必需）；
- [ ] 签名与升级路径明确。

## 3. 发布检查清单

- [ ] 版本号统一：`campusrun.__version__`、README、EXE/APK version；
- [ ] 77 个测试通过 + GUI 冒烟；
- [ ] 真实账号登录回归（含首次绑定邮箱跳过）；
- [ ] 不含 `research/`、HAR、token、密码、个人数据；
- [ ] README（发行版）与 README.dev.md 链接正确；
- [ ] 发布说明写清“只读、非官方、不要代跑”；
- [ ] Git tag + 构建产物 SHA256；
- [ ] 保留源码构建脚本，保证可复现。
