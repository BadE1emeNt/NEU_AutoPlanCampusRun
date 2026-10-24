# iPhone 抓登录 + 跑步统计（Reqable 增强模式）

> 目标：抓 **一次登录请求** 和 **一次跑步统计请求**，用来实现“本机账号密码 → 自动登录 → 拉数据”。
> 不需要把账号密码发给我；抓包里密码是 RSA 密文。
> 抓包文件放到 `C:\zwjm\CampusRun\research\`，该目录已被 git 忽略。

## 为什么不用 Charles / Fiddler 直接连 Wi-Fi 代理

「智慧东大」是 Flutter 应用。Flutter 的 Dart 网络库有两个特点：

1. **不走 iOS/Android 的 Wi-Fi 代理**，普通 HTTP 代理看不到它的请求；
2. Android 上只信任 `/system/etc/security/cacerts` 里的系统证书，不信任用户证书。

所以手机上推荐用 **Reqable 的“增强模式”（VPN 抓包）**；iOS 安装并信任证书比 Android 简单得多。

参考：<https://reqable.com/zh-CN/blog/2024/06/27/post>

## 准备

- iPhone / iPad（已安装「智慧东大」并能登录）；
- Windows 电脑，和手机连同一个 Wi-Fi；
- Reqable 电脑版：<https://reqable.com/zh-CN/download/>
- Reqable iOS 版：App Store 搜索 **Reqable**（或 <https://apps.apple.com/us/app/id6473166828>）
- 本仓库的 `research` 目录：`C:\zwjm\CampusRun\research\`

## 第一步：电脑和手机协同

1. 安装并打开 Reqable 电脑版。
2. 点击顶部“手机”图标，出现二维码。
3. iPhone 打开 Reqable App → 选择 **协同模式** → 扫描电脑上的二维码。
4. 连接成功后，电脑端应显示手机已连接。

## 第二步：在 iPhone 安装并信任证书

1. Reqable iOS App 里进入 **证书管理 / 设置 → 安装根证书**，按提示下载描述文件。
2. iPhone **设置 → 通用 → VPN 与设备管理 → 已下载的描述文件** → 安装。
3. iPhone **设置 → 通用 → 关于本机 → 证书信任设置** → 打开 Reqable 的完全信任开关。
4. 回到 Reqable App，确认“证书已安装”。

## 第三步：打开增强模式（关键）

1. 保持手机与电脑协同连接。
2. 在 Reqable iOS App 主界面/标题菜单里打开 **增强模式**（开启后标题旁会有钥匙 🔑 标记）。
3. 电脑端点击 **启动 / 开始抓包**。
4. 如果手机端也显示“调试已开启”，说明正常。

> 不开增强模式，Flutter 的请求很可能一条都抓不到。这是最容易漏的一步。

## 第四步：抓登录请求

1. 在手机上打开「智慧东大」，**退出登录**（如果已登录），回到登录页。
2. 输入学号、密码，点登录；如果弹出短信验证码，正常完成。
3. 在电脑 Reqable 中按域名过滤：`personal.neu.edu.cn`。
4. 找这些请求（不同版本可能只出现其中几条）：
   - `POST /portal/manage/common/app_login/check`
   - **`POST /portal/manage/common/app_login/commit`** ← 最关键
   - 如果弹了短信：`smsSend`、`verifyCommit`
5. 点开 `commit`，确认：
   - Request Body 里有 `account`、`password`、`encryptionType` 等字段；
   - `password` 应该是一长串 Base64（RSA 密文），不是明文；
   - Response 是 JSON，形如 `{"e":0,"m":"...","d":{...}}`；
   - Response Headers 里有 `Set-Cookie`（可能包含登录态）。

## 第五步：抓跑步统计请求

1. 登录成功后，在 App 里进入 **校园乐跑 → 我的 / 统计 / 跑步记录**。
2. 下拉刷新，让数据请求出现。
3. 在 Reqable 里找返回 JSON 含以下字段的请求：
   - `distance`、`totalDistance`、`mileage`、`records`、`runList`、`totalCount`、`semester`
4. 这条请求的域名不一定是 `personal.neu.edu.cn`，也可能是 `*.neu.edu.cn` 或小程序自己的域名；
   可以按 App/进程过滤，或搜索响应里的 `distance`。
5. 点开确认 Response 里能看到你的次数/公里数。

## 第六步：保存给我

推荐：**导出 HAR**（包含请求头、请求体、响应、Cookie，最完整）。

1. 在 Reqable 电脑端按住 `Ctrl` 选中这两条请求（登录 + 统计）。
2. 右键 → **Export / 导出 → HAR**。
3. 保存到：
   ```text
   C:\zwjm\CampusRun\research\capture.har
   ```

如果找不到 HAR 导出：

- 右键登录请求 → **Copy as cURL**，保存为 `research\login.curl.txt`；
- 右键统计请求 → **Copy as cURL**，保存为 `research\run.curl.txt`；
- 再把两条请求的 **Response Body** 分别保存为 `login.response.json`、`run.response.json`。

保存后告诉我一声即可，我会在本机读取，不需要你把内容贴到聊天里。

## 可以打码的内容

HAR 里有你的登录令牌，属于敏感信息。如果不想让我看到真实值，可以只替换**值**，保留**字段名/结构**：

- 请求头 `Cookie`、`Authorization`、`token` 的值 → `<REDACTED>`；
- 响应 JSON 里的 `access_token`、`token`、`ticket`、`loginFreeSecret` 的值 → `<REDACTED>`；
- 密码字段 `password` 的密文可以保留（它是 RSA 密文），也可以替换成 `<REDACTED>`；
- **不要改字段名、URL、请求方法、`encryptionType`、状态码、`e/m` 消息**。

即使令牌打码，我也能实现登录流程；测试时你自己在本机用真实密码登录即可。

## 常见问题

| 现象 | 处理 |
|---|---|
| Reqable 里看不到 App 的请求 | 确认开了 **增强模式**；关掉再开；确认电脑端已“启动抓包”。 |
| App 提示网络错误 / SSL handshake failed | 证书没装好或没信任；重做第二步。若仍失败，可能是证书固定，告诉我。 |
| 抓到的是明文 HTTP/2 但没有 JSON | 可能只抓到了埋点；按 `personal.neu.edu.cn` 和 `app_login` 过滤，或按 App 过滤。 |
| 登录成功但找不到统计请求 | 在 App 里多刷新几次；搜索响应关键字 `distance`；小程序可能是 WebView，域名会变。 |
| 弹了短信验证码 | 正常输入，并把 `smsSend` / `verifyCommit` 一起导出。 |
| 不想装 Reqable | iOS 也可用 Stream/Shadowrocket 等支持 VPN + MITM 的工具，但要能导出 HAR；不推荐 Charles（Flutter 不走 Wi-Fi 代理）。 |

## 安全注意

- `capture.har` 含登录令牌，等同于密码；只放在本机 `research/`，不要上传、不要发群。
- 抓完后可以在 App 里退出登录，让旧令牌失效；不需要改密码。
- 密码在请求里是 RSA 密文；但我仍然不需要你的明文密码。

## 抓完后我会做什么

1. 解析 HAR，确认 `commit` 的字段、RSA 填充方式、`encryptionType` 取值；
2. 确认登录成功返回的是 Cookie 还是 JSON token；
3. 确认统计接口的域名、请求头、字段映射；
4. 实现本机账号密码登录（DPAPI 保存、可选不保存密码）、自动刷新、过期重登；
5. 你本地输入自己的账号密码测试，不需要发给我。
