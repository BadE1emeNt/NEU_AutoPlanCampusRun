# AGENTS.md · CampusRun 项目记录

> 给后续会话/开发者：先读本文件，再读 `README.md` 与 `docs/CAPTURE.md`。

## 1. 项目是什么

Windows 桌面工具 + 纯 Python 核心库：

- 从东北大学“校园乐跑”小程序读取**只读**跑步统计（抓包 cURL，复用登录态）；
- 按目标 km / 截止日期 / 休息日，计算每日摊平里程、2/3/4/5 km 完成天数、逐日计划；
- Tkinter GUI（演示模式开箱可用）+ CLI；
- 凭据用 Windows DPAPI 加密，不实现登录、签名、提交跑步。

**约束**：只读、不伪造轨迹、不自动刷里程；不常驻后台；不做账号密码登录。

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
  curlparse.py     cURL、Windows ^ 续行、原始 HTTP 请求
  jsonpath.py      data.list[0] 之类路径
  providers/       MockProvider / HttpProvider / autodetect
  cli.py           plan / fetch / import-curl / config / doctor / gui
  ui/              theme, widgets, app, dashboard, records, connection, help, plan_dialog
tests/             66 个测试（analysis/curl/autodetect/config/DPAPI/http/GUI e2e）
tools/             ui_smoke.py, e2e_gui.py, e2e_cli.py, ui_preview.py, ui_plan_preview.py, screenshot.ps1
docs/              CAPTURE.md, API-NOTES.md, 截图
```

数据目录：`%APPDATA%\CampusRun`（或 `CAMPUSRUN_HOME`）：
`config.json`、`connection.dat`（DPAPI）、`cache/summary.json`、`logs/app.log`、`exports/`。

## 4. 当前状态（2026-10-24）

- 核心算法、配置、DPAPI、cURL 解析、自动识别、HTTP Provider、CLI、四个 GUI 页面、计划弹窗均已完成。
- 66 个测试通过（含本地 HTTP 服务器与 GUI 端到端：
  粘贴 cURL → 抓取 → 自动识别 → DPAPI 保存 → 重启 → 刷新）。
- 演示数据固定 38.4 km / 12 次；规划结果已与手算核对。
- **真实东北大学接口尚未抓包**。`docs/API-NOTES.md` 是待填模板。
  下一步需要用户提供：客户端类型、脱敏后的请求路径、响应 JSON 字段结构。
  拿到后优先补 `profiles/neu.json` 默认映射与 fixture 测试，而不是写死不可维护的解析。

## 5. 设计决策

- 不做登录/签名逆向：复用用户抓到的已登录请求，换取低风险与低维护成本。
- 自动识别 + 手工 JSON 路径：接口未知时仍可用；识别结果必须显示“N 次 / X km”供用户核对。
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

- [ ] 用户抓包后填 `docs/API-NOTES.md`；
- [ ] 视字段稳定性增加 NEU 默认 profile 与 fixture；
- [ ] 与小程序页面数字对照验证；
- [ ] 可选：PyInstaller 打包（需先确认不引入常驻进程）；
- [ ] 可选：计划导出日历/提醒。
