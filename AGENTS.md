# AGENTS.md · CampusRun 项目记录

> 给后续会话/开发者：先读本文件，再读 `README.md` 与 `docs/CAPTURE.md`。

## 1. 项目是什么

Windows 桌面工具 + 纯 Python 核心库：

- 从东北大学“校园乐跑”（体育平台 H5）读取**只读**跑步统计；
  支持“本机学号/密码 → CAS → 体育平台 token”的账号登录，也保留抓包 cURL 备用；
- 按目标 km / 截止日期 / 休息日，计算每日摊平里程、2/3/4/5 km 完成天数、逐日计划；
- Tkinter GUI（演示模式开箱可用）+ CLI；
- 密码/会话/抓包凭据用 Windows DPAPI 加密；不提交跑步、不伪造轨迹。

**约束**：只读；不常驻后台；不绕过验证码；登录协议以抓包/官方页面为准。

## 2. 环境

- 本机 Python：`C:\Users\luna\AppData\Local\Python\pythoncore-3.14-64\python.exe`（3.14.7，tkinter/Tk 9.0）。
  不要假设 `python` 命令可用（PATH 里可能是 Microsoft Store 占位）。
- 本机屏幕 DPI 150%：Tk 字体缩放 2.0；窗口 geometry 已按 `winfo_fpixels("1i")/96` 放大。
  新增固定像素尺寸（ring、rowheight、wraplength）时注意高 DPI 表现。
- 沙箱 `workspace-write` 下：
  - `%TEMP%` 里由 Python 创建 `mode=0700` 的目录会拒绝访问；测试临时目录固定为 `tests/.tmp`（默认权限）。
  - 工作区曾因 ACL 缺 `WRITE_OWNER` 无法启动 pwsh；已用 `diagnose-windows-sandbox-acl` 修复，
    备份在 `.acl-recovery/`（已 gitignore），不要提交。
- `.cmd` 必须 **纯 ASCII + CRLF**；`.ps1` 若含中文必须 UTF-8 BOM。
- 测试运行：
  ```bat
  run_tests.cmd
  ```
  或：
  ```powershell
  $env:PYTHONPATH='C:\zwjm\CampusRun\src'
  & 'C:\Users\luna\AppData\Local\Python\pythoncore-3.14-64\python.exe' -m unittest discover -s tests -t .
  ```

## 3. 目录与职责

```text
src/campusrun/
  models.py        RunRecord / RunSummary / HttpConnection / FieldMapping
  analysis.py      PlanSettings / Progress / build_plan / schedule_for（纯函数）
  service.py       配置 + 数据源 + 缓存 + 规划的应用服务
  config.py        AppPaths / AppConfig / ConnectionStore(DPAPI) / SummaryCache
  secrets.py       CryptProtectData / CryptUnprotectData
  neu/             CAS 登录、AES/RSA、体育平台 API、DPAPI 会话/密码存储
  curlparse.py     cURL、Windows ^ 续行、原始 HTTP 请求
  jsonpath.py      data.list[0] 之类路径
  providers/       MockProvider / HttpProvider / autodetect
  cli.py           plan / fetch / import-curl / config / doctor / gui
  ui/              theme, widgets, app, dashboard, records, connection, help, plan_dialog
tests/             74 个测试（analysis/curl/autodetect/config/DPAPI/http/neu/CAS/GUI e2e）
tools/             ui_smoke.py, e2e_gui.py, e2e_cli.py, ui_preview.py, ui_plan_preview.py, screenshot.ps1
docs/              CAPTURE.md, API-NOTES.md, LOGIN-NOTES.md, 截图
```

数据目录：`%APPDATA%\CampusRun`（或 `CAMPUSRUN_HOME`）：
`config.json`、`connection.dat`、`sports_session.dat`、`credentials.dat`、
`cache/summary.json`、`logs/app.log`、`exports/`。

## 4. 当前状态（2026-10-24 晚）

- 核心算法、配置、DPAPI、cURL、自动识别、CLI、GUI 均完成；74 个测试通过。
- **账号登录已实现**：
  - CAS 登录页解析 `lt/execution` + RSA(PKCS#1 v1.5) 加密 `学号+密码`；
  - 支持短信二次认证（`phone(...)` 挑战 → `tpass/device` 发送/校验，勾选信任设备）；
  - H5 `neuLogin?ticket=...` → 从最终跳转 URL 取 token/uid/学号；
  - 体育平台 API：AES-128-CBC、MD5 签名、token 调用；
  - `sports_session.dat` / `credentials.dat` DPAPI；token 过期可自动重登。
- **真实账号密码登录尚未由用户实测**（2026-10-24 仅用用户提供的 HAR
  验证了 token/API 与 CAS 页面解析；CAS 密码 POST 用本地 mock 验证）。
- 用户数据（2026-10-24，体育平台 2026~2027 上学期）：5 次 / 17.38 km；
  接口字段见 `docs/API-NOTES.md`。
- 下一步：用户运行 `campusrun.cmd login --remember` 或 GUI 登录，报告是否需要短信/错误码；
  若真实 CAS 表单与 mock 有差异，按错误页面微调。
- 交互约定：抓包备用方式默认隐藏；账号登录连续失败 2 次自动显示并提示抓包教程；
  登录成功/退出后恢复隐藏（已有 cURL 连接时保持显示）。

## 5. 设计决策

- **登录**：账号密码走 CAS（不逆向 App Flutter 层）；CAS 表单/公钥从官方页面动态读取。
  短信二次认证用回调；勾选 `saveDevice` 信任设备。失败/验证码不支持时回退 cURL。
- **体育平台 API**：AES-128-CBC key/iv + MD5(排序 key+value + salt)；
  token 单独即可调用（实测无需 Cookie），但请求仍带浏览器 UA/Origin/Referer。
- **存储**：账号密码、体育平台 token、cURL 各自 DPAPI 文件；密码不写日志。
- 只读数据层：自动识别 + 手工 JSON 路径；识别结果必须显示“N 次 / X km”供用户核对。
- 规则可配置：单次 2–5 km、每天 1 次、目标与截止日、每周休息日。
- 每天去重取最远一次，避免接口返回多次尝试时高估里程；`count_mode=sum` 可切换。
- DPAPI 降级：非 Windows 或 DPAPI 失败时明文保存并明确警告；目标平台 Windows 下应加密。
- GUI 不常驻、不轮询；启动时若有连接则刷新一次，失败保留缓存。

## 6. 开发注意

- 改 `.cmd` 后检查 CRLF 与 ASCII：
  ```powershell
  $t=[IO.File]::ReadAllText($p); [IO.File]::WriteAllText($p, ($t -replace "`r?`n","`r`n"), (New-Object Text.UTF8Encoding($false)))
  ```
- 改 UI 后至少跑 `python tools\ui_smoke.py`；视觉检查用 `ui_preview.py` + `screenshot.ps1`
  （screenshot 已处理 DPI awareness；弹窗用 `-Dialog`）。
- 新增按钮/标签时避免超出卡片：设置页曾因 7 个 Checkbutton 单行被裁，现为 4+3 两行。
- 计划算法改动必须补 `tests/test_analysis.py` 的手算用例。
- 抓包字段识别改动补 `tests/test_autodetect.py`；网络改动补 `tests/test_http.py`。

## 7. Git

- 用户要求用 git 管理，但不要过度主动操作。
- 只在明确的里程碑提交（如核心完成、真实接口适配完成），不要每改一个文件就 commit。
- 不提交 `.dev-home/`、`tests/.tmp/`、`.acl-recovery/`、`%APPDATA%` 数据、抓包原文、令牌、截图中的个人信息。

## 8. 待办

- [ ] 用户用真实账号跑一次 `campusrun.cmd login --remember`，确认 CAS 密码/短信流程；
- [ ] 根据真实错误页微调 CAS 错误/短信解析；
- [ ] 学期目标/截止日从 `Run2/beforeRunV260` 自动读取（可选）；
- [ ] 与小程序页面数字对照验证；
- [ ] 可选：PyInstaller 打包（需先确认不引入常驻进程）；
- [ ] 可选：计划导出日历/提醒。
