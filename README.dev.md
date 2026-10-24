# CampusRun 开发者文档

> **这是开发者 README，面向维护者/二次开发。**
> 普通使用者请先看 [README.md](README.md)（发行版说明）。
>
> **AI 生成声明**：代码与文档主要由 AI 编程助手生成或辅助生成，仅供学习/技术练习；
> 非学校官方；MIT License，详见 [LICENSE](LICENSE) 与 [DISCLAIMER.md](DISCLAIMER.md)。
>
> 版本 0.1.0 · 2026-10-24 · Windows + Python 标准库 + Tkinter。

## 1. 项目状态

- 账号密码登录、CAS/RSA、短信二次认证、体育平台 AES/签名 API、DPAPI 存储、GUI/CLI、规划算法均已实现。
- **78 个测试全部通过**（含本地 mock CAS、体育平台加密接口、DPAPI、GUI 冒烟）。
- 真实数据处理已验证：用用户 HAR 中的 token 调用体育平台 API 成功；用 CASTGC 重新走
  `neuLogin` 能拿到新 token。
- **真实 CAS 密码 POST** 已用本地 mock 验证；第一个真实账号已成功登录，
  第二个账号被 CAS `tp_tpass/h5?act=tpass/guide` 首次登录引导页拦截。该页面实际是
  **首次绑定邮箱**，可点“稍后绑定”跳过；程序会先尝试带会话重新进入 CAS 登录入口，
  仍被拦截时提示并打开浏览器，完成一次后重试。
- 发布方式：源码 + `.cmd`，以及 PyInstaller **one-folder EXE**（`dist/CampusRun/CampusRun.exe`）；
  已在开发机和另一台电脑启动通过。

## 2. 技术栈与约束

- Python 3.10+，**只用标准库**；不依赖 requests/cryptography。
- Tkinter 桌面（Tk 8.6/9.0 均可）。
- Windows DPAPI（`crypt32`）保存密码/会话/抓包凭据。
- 纯 Python 实现 AES-128-CBC、RSA PKCS#1 v1.5、DER 公钥解析。
- 只读：不实现提交跑步、轨迹、签名回放；不绕过验证码。
- 不常驻后台：GUI 启动时刷新一次，之后手动刷新/定时器不做轮询。

## 3. 架构

```text
┌──────────────────────────── UI (tkinter) ────────────────────────────┐
│ app / dashboard / records / connection / help / plan_dialog          │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                         CampusRunService
                ┌───────────────┼────────────────┐
                │               │                │
        AppConfig/Paths   SummaryCache      NeuStore(DPAPI)
                │               │                │
                │        ┌──────┴───────┐   credentials.dat
                │        │              │   sports_session.dat
                │   MockProvider   HttpProvider(cURL)
                │                  │
                │            CasLoginClient ──► CAS ──► 体育平台 H5 token
                │                  │
                │            SportsClient ──► 加密 API ──► RunSummary
                │
          analysis.build_plan ──► PlanResult ──► UI/CLI
```

关键点：

- `analysis.py` 是纯函数，不依赖网络/UI，便于单测和移植。
- `service.py` 是唯一编排层；GUI/CLI 不直接碰网络、文件、DPAPI。
- 三种数据源统一产出 `RunSummary`：
  1. `MockProvider`（演示）；
  2. `HttpProvider`（抓包 cURL + 自动识别）；
  3. `SportsClient`（账号登录后的体育平台 API）。
- 规划统一由 `Progress.from_summary()` + `build_plan()` 计算。

## 4. 目录结构

```text
CampusRun/
├─ README.md                 发行版说明（给使用者）
├─ README.dev.md             本文件（开发者）
├─ LICENSE                   MIT 许可
├─ DISCLAIMER.md             AI 生成/仅供练习/免责声明
├─ AGENTS.md                 项目约定/环境/当前状态/待办
├─ run.cmd                   GUI 启动入口
├─ campusrun.cmd             CLI 入口
├─ run_tests.cmd             测试入口
├─ build_exe.cmd             构建 Windows EXE（调用 tools/build_exe.ps1）
├─ packaging/
│  ├─ launcher.py            PyInstaller 入口
│  └─ requirements-build.txt 构建依赖（PyInstaller）
├─ pyproject.toml            setuptools 包配置（无第三方依赖）
├─ .gitattributes            行尾规则（.cmd=CRLF）
├─ .gitignore
├─ docs/
│  ├─ CAPTURE.md             通用抓包指南（cURL 备用）
│  ├─ CAPTURE-LOGIN-IOS.md   iPhone/iPad Reqable 抓包步骤
│  ├─ API-NOTES.md           体育平台/CAS 协议记录（字段/加密/签名）
│  ├─ LOGIN-NOTES.md         账号登录方案、实现状态、限制
│  ├─ PACKAGING.md           EXE/APK 打包路线与发布检查清单
│  ├─ screenshot-dashboard.png
│  ├─ screenshot-account.png
│  └─ screenshot-records.png
├─ src/campusrun/
│  ├─ __init__.py
│  ├─ __main__.py            python -m campusrun
│  ├─ cli.py                 login/logout/fetch/plan/import-curl/config/doctor/gui
│  ├─ service.py             应用服务编排
│  ├─ config.py              AppPaths/AppConfig/ConnectionStore/SummaryCache
│  ├─ models.py              RunRecord/RunSummary/HttpConnection/FieldMapping
│  ├─ analysis.py            PlanSettings/Progress/build_plan/schedule_for
│  ├─ formatting.py          中文格式化
│  ├─ errors.py              统一异常
│  ├─ storage.py             原子写入/JSON
│  ├─ secrets.py             DPAPI protect/unprotect
│  ├─ curlparse.py           cURL/原始 HTTP 解析
│  ├─ jsonpath.py            data.list[0] 路径
│  ├─ providers/
│  │  ├─ base.py
│  │  ├─ mock.py
│  │  ├─ http.py
│  │  └─ autodetect.py       抓包 JSON 自动识别
│  ├─ neu/
│  │  ├─ crypto.py           纯 Python AES-128-CBC / RSA PKCS#1 / DER
│  │  ├─ cas.py              CAS 登录 + 短信二次认证 + H5 token
│  │  ├─ sports.py           体育平台加密 API 客户端
│  │  └─ store.py            sports_session.dat / credentials.dat（DPAPI）
│  └─ ui/
│     ├─ theme.py            配色/字体/DPI/ttk 样式
│     ├─ widgets.py          Card/Pill/ProgressRing/ScrollFrame/NavItem
│     ├─ app.py              主窗口/导航/后台任务队列/短信弹窗
│     ├─ dashboard.py        概览/场景/计划
│     ├─ records.py          记录表/CSV
│     ├─ connection.py       账号登录 + 隐藏的抓包备用
│     ├─ onboarding.py       首次使用指南弹窗（不含抓包）
│     ├─ help.py             抓包教程
│     └─ plan_dialog.py      完整计划弹窗
├─ tests/
│  ├─ __init__.py            src 路径 + tests/.tmp
│  ├─ test_analysis.py
│  ├─ test_curlparse.py
│  ├─ test_autodetect.py
│  ├─ test_config.py         AppConfig/DPAPI/缓存/service
│  ├─ test_http.py           本地 HTTP mock
│  └─ test_neu.py            AES/RSA/CAS/Sports/Service 登录持久化
├─ tools/
│  ├─ ui_smoke.py            创建窗口/切页/计划弹窗
│  ├─ e2e_gui.py             cURL GUI 全流程（mock HTTP）
│  ├─ e2e_cli.py             CLI import→plan→doctor
│  ├─ ui_preview.py          指定页面预览（可滚动）
│  ├─ ui_plan_preview.py     计划弹窗预览
│  ├─ screenshot.ps1         窗口截图（DPI 感知，支持 -Dialog）
│  └─ build_exe.ps1          PyInstaller one-folder 构建/压缩/SHA256
└─ research/                 本地抓包/HAR（gitignore，绝不提交）
```

## 5. 数据流

### 账号登录

```text
UI/CLI
  -> CampusRunService.login_neu(username, password, remember, sms_provider)
  -> CasLoginClient.login()
       GET  /tpass/login?service=...
       解析 lt/execution + login_neu.js 的 publicKeyStr
       RSA_PKCS1(学号+密码) -> POST /tpass/login
       如 CAS 返回 phone(...) 挑战 -> /tpass/device 发码/验码（s=1 信任设备）
       跟随 302: 体育平台 neuLogin?ticket -> /login/neuLogin -> /view/db/#/...&token=...
  -> SportsSession(token, uid, school_id, student_num, card_id, ...)
  -> NeuStore.save_session()
  -> SportsClient.fetch()
       AES 加密请求 + MD5 签名
       解密响应 -> 学期/UserInfo/记录
  -> RunSummary
  -> SummaryCache.save()
  -> build_plan() -> UI
```

### 数据刷新 / 过期

- `auth_mode=password` 时 `refresh()` 用保存的 token 调 API。
- 响应 `status` 为 101/102/103 时抛 `SportsSessionExpired`。
- 有保存密码：自动重新 CAS 登录；如遇短信挑战，通过 `sms_provider` 回调 UI/CLI。
- 无保存密码：提示重新登录。

### cURL 备用

```text
curlparse.parse_capture -> HttpProvider.fetch_json -> autodetect.detect
  -> summary_from_payload -> RunSummary -> SummaryCache
```

`auth_mode=curl`，与账号登录互斥；保存 cURL 时会把 `auth_mode` 切到 `curl`。

## 6. 协议摘要

详细字段/常量见 [docs/API-NOTES.md](docs/API-NOTES.md)；登录方案见
[docs/LOGIN-NOTES.md](docs/LOGIN-NOTES.md)。

- CAS 登录页：`https://pass.neu.edu.cn/tpass/login?service=<体育平台 neuLogin>`
- CAS 公钥：从 `login_neu.js` 的 `publicKeyStr` 动态读取，失败才用内置兜底
- 密码：JSEncrypt 兼容的 RSA PKCS#1 v1.5；明文 `学号+密码`；`ul/pl` 为 JS 字符串长度
- H5：`tybzhtypt.neu.edu.cn/bdlp_h5_fitness_test/public/index.php/index/login/neuLogin`
- 最终 token：H5 跳转 URL 的 `token/uid/school_id/student_num/card_id/term_id`
- 体育平台 API：`POST /v3/api.php/...`，`ostype=5&data=AES(...)`
- AES-128-CBC key/iv、MD5 签名盐在 `docs/API-NOTES.md`，代码中集中在 `neu/sports.py`
- 响应：`{"status":1,"is_encrypt":1,"data":"..."}`

## 7. 配置与存储

数据目录：`%APPDATA%\CampusRun`，可用 `CAMPUSRUN_HOME` 覆盖。

| 文件 | 内容 | 保护 |
|---|---|---|
| `config.json` | 目标/截止/休息日/auth_mode/窗口状态/用户名 | 非秘密 |
| `sports_session.dat` | 体育平台 token + uid/学号 | DPAPI |
| `credentials.dat` | 可选的学号/密码 | DPAPI |
| `connection.dat` | 可选的抓包 cURL | DPAPI |
| `cache/summary.json` | 最近一次 RunSummary | 普通 |
| `logs/app.log` | 运行日志（不含密码/token） | 普通 |
| `exports/*.csv` | 导出记录 | 普通 |

`secrets.py` 用 `CryptProtectData/CryptUnprotectData`，熵为 `CampusRun.credentials.v1`。
DPAPI 不可用时降级为明文并返回 `secure=False`；Windows 目标环境应始终加密。

`NeuStore._ProtectedFile` 使用 magic 头区分加密/明文，读写均校验。

## 8. 本地开发

```powershell
$env:PYTHONPATH = 'C:\zwjm\CampusRun\src'
$env:PYTHONUTF8 = '1'
py -3 -m campusrun --help
py -3 -m campusrun doctor
```

启动 GUI：

```powershell
py -3 -m campusrun gui
```

或：

```bat
run.cmd
campusrun.cmd login --remember
campusrun.cmd login --no-save
campusrun.cmd fetch
campusrun.cmd plan
```

### 环境注意

- 本机 Python 3.14 / Tk 9.0；不要假设 `python` 命令可用（可能是 Store 占位）。
- 150% DPI：窗口尺寸按 `winfo_fpixels("1i")/96` 放大；Tk 字体自动缩放。
  新增固定像素尺寸（ring、Treeview rowheight、wraplength）时注意高 DPI。
- `%TEMP%` 下 Python `mode=0700` 目录在受限环境可能无法访问，测试统一用 `tests/.tmp`。
- `.cmd` 必须 ASCII + CRLF；`.ps1` 含中文时用 UTF-8 BOM。
- 截图脚本需要 DPI 感知；窗口被最小化时会先 `ShowWindow(SW_RESTORE)`。

## 9. 测试

```bat
run_tests.cmd
```

或：

```powershell
$env:PYTHONPATH = 'C:\zwjm\CampusRun\src'
py -3 -m unittest discover -s tests -t .
```

GUI 冒烟（会短暂打开窗口）：

```powershell
python tools\ui_smoke.py
python tools\e2e_gui.py
python tools\e2e_cli.py
```

测试覆盖：

- `test_analysis.py`：可跑日、休息日、2/3/4/5 场景、最快计划、今日已跑、截止日边界。
- `test_curlparse.py`：Linux/Windows cURL、cookie、GET 查询、原始 HTTP、脱敏。
- `test_autodetect.py`：记录数组/汇总、单位、epoch、去重、映射失败。
- `test_config.py`：配置校验、DPAPI 连接、缓存、service。
- `test_http.py`：本地 HTTP mock、401/403、gzip、聚合。
- `test_neu.py`：AES 已知向量、RSA、签名、体育平台 mock、CAS 成功/密码错/短信、登录持久化。

**未覆盖真实网络**：CAS 真实密码 POST、短信二次认证、学校改版。不要用真实账号跑自动化测试。

## 10. 打包与发布

Windows 发布使用 PyInstaller **one-folder**：

```bat
build_exe.cmd
```

等价于：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_exe.ps1
```

产物：

- `dist/CampusRun/CampusRun.exe` + `_internal/`（约 26 MB）；
- `dist/CampusRun-0.1.0-win64.zip`（含 README/CAPTURE/截图）；
- 构建脚本末尾输出 zip 的 SHA256。

构建依赖只有 `pyinstaller==6.22.3`，见 `packaging/requirements-build.txt`。
PyInstaller 使用 one-folder，避免单文件每次解压 Tk/Tcl 和更高杀毒误报。
Android APK（Tkinter 不能直接转 APK，需要重写 UI）的路线、约束和验收清单见
[docs/PACKAGING.md](docs/PACKAGING.md)。

`run.cmd` 查找顺序：

1. `.venv\Scripts\pythonw.exe`
2. `pyw -3`
3. `py -3`
4. `python`

`campusrun.cmd` 同理（console）。

## 11. 调试

- 登录失败时 `CasLoginClient` 会生成**脱敏跳转链**：只保留 host/path/status/page 提示，
  `ticket/token/uid/student_num/card_id` 均替换为 `<hidden>`。
- `campusrun.cmd --debug login --remember` 会输出完整异常堆栈（全局 `--debug` 要在子命令前）。
- 日志：`%APPDATA%\CampusRun\logs\app.log`，只记状态/异常，不记密码/token。
- 账号登录失败 2 次会在 UI 自动展开抓包备用并提示教程。
- 如果 CAS 页面改版：优先检查 `_login_page` 的 `lt/execution` 解析、
  `_fetch_public_key` 的脚本/公钥正则、`_parse_sms_challenge` 的 `phone(...)`。

## 12. 已知限制 / TODO

- **单账号**：`sports_session.dat/credentials.dat` 只保存一个账号；多账号切换未实现。
- **第二个真实账号**被 CAS 首次绑定邮箱引导页（`tp_tpass/h5?act=tpass/guide`）拦截；
  页面可点“稍后绑定”跳过。当前会提示并打开浏览器，完成后重试；纯 HTTP 不自动点页面。
- 图形验证码/滑块/扫码不支持，需抓包备用。
- 学期目标/截止日仍手动设置；`Run2/beforeRunV260` 可提供学期起止/规则，尚未接入。
- 无 PyInstaller 单文件包；当前为 one-folder，`_internal` 必须一起分发。
- EXE 已在开发机和另一台电脑启动验证；尚未在无 Python 的干净 Windows VM 上单独回归。
- 真实 CAS 密码流程只验证了一个账号；短信二次认证未真实触发验证。
- 自动刷新只在启动/手动点击时发生，没有后台定时器。

## 13. Git

- 远端：`https://github.com/BadE1emeNt/NEU_AutoPlanCampusRun.git`
- 主分支：`main`
- 当前提交以 `git log -1` 为准；发布说明见 [README.md](README.md)。
- 不应提交：`research/`、`*.har`、`tests/.tmp/`、`.dev-home/`、`.acl-recovery/`、
  `%APPDATA%` 数据、抓包/令牌/截图中的个人信息。
- `.gitattributes` 固定 `.cmd` 为 CRLF；源码/文档 LF。
- GitHub 访问可能需要本机代理；不要把代理或凭据写入仓库/文档。

## 14. 安全约定

- 密码/令牌只在内存与 DPAPI 文件中；不写日志、不进异常、不进测试夹具。
- 测试使用合成账号 `20260001`、合成 token；禁止把真实 HAR 放入 `tests/`。
- 错误信息可以包含 URL，但必须脱敏 query；`_redact_url` 已覆盖 ticket/token/uid 等。
- 只读 API；不要新增提交跑步/轨迹/成绩的代码。
- 发现凭据泄露：删除 `sports_session.dat/credentials.dat/connection.dat`，重新登录。

## 15. 声明与许可

- 代码/文档由 AI 生成或辅助生成，仅供学习与技术练习；不是学校官方工具。
- 禁止代跑、刷里程、伪造记录、学术不端或商业用途。
- 开源许可：MIT，见 [LICENSE](LICENSE)；完整免责声明见 [DISCLAIMER.md](DISCLAIMER.md)。
