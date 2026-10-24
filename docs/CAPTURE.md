# 校园乐跑抓包指南

本程序不实现账号密码登录、验证码或签名算法。它复用你**已经登录**的小程序会话：
你抓一条查询请求，程序用同样的地址和请求头再请求一次，读取返回的 JSON。

因此只需要成功抓 **一条** 请求。下面按成功率从高到低给出三种路线。

---

## 0. 先确认要抓什么

在小程序里进入“跑步记录 / 我的里程 / 统计 / 本学期进度”页面，下拉刷新一次。
你要找的请求，返回内容通常是 JSON，里面能看到：

- 总里程：`totalDistance`、`totalMileage`、`distance`、`mileage`、`totalKm`；
- 总次数：`totalCount`、`runCount`、`totalRuns`、`times`；
- 或逐条记录数组：`records`、`list`、`rows`、`runList`，每条含 `runDate`、`distance`、`duration`。

只要响应里有这些字段之一，就说明找对了。**不需要**抓登录、提交跑步、上传轨迹的请求。

---

## 1. Windows 微信 + mitmproxy / Fiddler（推荐）

适用：微信 PC 版能打开该小程序，电脑和手机在同一网络。

### mitmproxy

1. 安装（任选其一）：
   ```bat
   py -3 -m pip install mitmproxy
   ```
   或从 <https://mitmproxy.org/> 下载 Windows 安装包。
2. 启动 `mitmweb`（默认监听 `127.0.0.1:8080`）。
3. Windows 设置 → 网络和 Internet → 代理 → 手动设置代理：
   `127.0.0.1:8080`，并勾选“请勿对本地地址使用代理服务器”。
4. 浏览器打开 <http://mitm.it>，下载 Windows 证书并按提示安装到“受信任的根证书颁发机构”。
5. 打开微信 PC 版 → 进入该小程序 → 跑步记录页 → 下拉刷新。
6. 在 mitmweb 里按域名过滤，找到返回跑步数据的请求。
7. 选中请求 → 右键/菜单 → **Copy as cURL**（没有该菜单就复制 URL + 请求头，按第 5 节整理）。

### Fiddler Classic

1. 安装 Fiddler Classic，`Tools → Options → HTTPS` 勾选 Decrypt HTTPS traffic，并安装根证书。
2. Fiddler 默认会设置系统代理（端口 8888）；保持 `Capture Traffic` 开启。
3. 微信 PC 打开小程序，刷新跑步记录页。
4. 在左侧会话列表找到 JSON 响应，右键 → `Copy` → `Copy as cURL`（不同版本菜单名可能不同）。

> 部分小程序会检测代理或直接拒绝 PC 端打开。先关闭代理进入页面，再开代理刷新；仍不行就走 Android/iOS。

---

## 2. Android 手机

适用：小程序只能在手机端打开。

1. 安装支持 VPN 抓包的工具：**Reqable**（推荐）、HttpCanary、mitmproxy 的 Android 客户端等。
2. 启动抓包，按工具提示安装 CA 证书。
3. 打开小程序 → 跑步记录页 → 下拉刷新。
4. 在抓包列表里找响应为 JSON、含里程/次数字段的请求。
5. 长按/菜单 → **Copy as cURL** / 导出 HAR，发送到电脑。

### Android 7+ 的证书问题

Android 7 起，应用默认**不信任用户安装的 CA 证书**。表现为：抓包工具里看不到 HTTPS 明文、请求显示 0 字节或 CONNECT 隧道。

可选办法：

- 优先用 Windows 微信路线（PC 端信任系统证书）；
- 使用带 root 的旧手机/模拟器，把 CA 装进系统证书区；
- 使用工具提供的“系统证书模式”（需要 root）；
- 如果小程序做了 SSL Pinning，普通代理无法解密，需要 Frida/逆向，成本较高——这时请把需求反馈给开发者。

---

## 3. iPhone / iPad + Charles

1. 电脑安装 Charles，手机 Wi-Fi 的 HTTP 代理指向电脑的 `8888` 端口。
2. 手机 Safari 打开 `chls.pro/ssl`，安装描述文件。
3. 设置 → 通用 → 关于本机 → **证书信任设置** → 打开 Charles 的完全信任。
4. 打开小程序刷新记录页。
5. Charles 中找到请求 → 右键 → **Copy cURL Request**。

---

## 4. 在抓包工具里定位请求

一次下拉刷新会发出很多请求（埋点、配置、登录态、资源）。建议：

1. 先清空会话，再刷新页面，只看新请求。
2. 按域名分组，逐个查看 **Response**，而不是只看 URL。
3. 搜索响应里的关键字：`distance`、`totalDistance`、`mileage`、`records`、`runList`、`semester`。
4. 如果响应是压缩/加密的（Base64、乱码、`data` 是长字符串），说明接口做了加密，自动识别无法工作；
   需要 JS 逆向或让开发者适配，先不要反复抓。

---

## 5. 没有 “Copy as cURL” 时

程序也接受**原始 HTTP 请求文本**。在抓包工具里复制请求，整理成：

```http
GET /api/xxx/list?page=1 HTTP/1.1
Host: example.edu.cn
Authorization: Bearer 你的令牌
Cookie: session=...
Accept: application/json

```

注意：

- 第一行必须是 `METHOD 路径 HTTP/1.1`；
- 必须有 `Host`；
- 请求头与空行之间不能少空行；
- 如果有 POST 请求体，放在空行之后。

也可以自己拼 cURL：

```bat
curl "https://example.edu.cn/api/xxx/list?page=1" ^
  -H "authorization: Bearer 你的令牌" ^
  -H "cookie: session=..." ^
  -H "content-type: application/json" ^
  --data-raw "{\"page\":1}"
```

Windows `cmd` 的续行符是 `^`，Linux/macOS 是 `\`，程序两种都支持。

---

## 6. 粘贴到程序里

1. 打开 CampusRun → “连接设置”。
2. 把 cURL 粘贴到“① 粘贴抓包请求”。
3. 点 **解析并测试**。程序会：
   - 解析方法、URL、请求头、请求体；
   - 用同一请求请求一次；
   - 自动寻找记录数组或汇总字段；
   - 显示“解析成功：N 次 / X km”。
4. 如果次数/公里数和小程序页面一致：
   - 直接点 **保存连接**；
   - 程序会关闭演示模式，用这份数据重新计算。
5. 如果数字不对：
   - 展开“③ 字段映射”，检查“记录数组路径”“里程字段”“日期字段”；
   - 点“按当前映射重新解析”；
   - 仍不对，把响应 JSON 的**字段结构**（数值打码）发给开发者。

---

## 7. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| HTTP 401 / 403 / “登录失效” | 令牌过期。重新进小程序刷新页面，重抓一条覆盖。 |
| 返回 HTML / 登录页 / 网关页 | 请求被重定向到登录，或电脑网络访问不了校园接口。重抓；必要时连校园网/VPN。 |
| 抓包工具里 0 字节 / 全是 CONNECT | 证书没信任，或 App 不走系统代理。优先用 Windows 微信路线。 |
| 小程序打不开 / 一直转圈 | 小程序检测代理。先关代理进入页面，再开代理下拉刷新。 |
| Android 看不到明文 | Android 7+ 不信任用户证书。用 PC 微信，或 root/模拟器装系统证书。 |
| 识别不出记录 | 接口可能只返回汇总字段（程序会自动切汇总模式），或字段名很特殊。手工填 JSON 路径。 |
| 保存后换电脑/账户失效 | DPAPI 绑定当前 Windows 账户。重新抓包保存即可。 |
| 接口返回加密字符串 | 需要逆向 JS 的加解密逻辑，当前版本不支持。 |

---

## 8. 安全与合规

- cURL 里的 `Authorization`、`Cookie`、`token` 等同于密码。
- 程序用 Windows DPAPI 加密保存，文件在 `%APPDATA%\CampusRun\connection.dat`；
  同一台机器、同一个 Windows 用户才能解密。
- 不要把 cURL 原文、完整响应、预览截图发到公开群聊或 Issue。
- 需要作废令牌时，在小程序里退出登录/重新登录即可让旧令牌失效。
- 本程序只读，不提交跑步、不修改成绩、不伪造轨迹。请遵守学校规定。

---

## 9. 如果自动识别失败，请提供这些信息

把值打码，只保留结构：

1. 客户端：微信 PC / Android / iOS，小程序名称与版本（如果能看到）。
2. 请求：方法、域名、路径（query 里的 token 打码）。
3. 响应 JSON 结构，例如：
   ```json
   {
     "code": 0,
     "data": {
       "records": [
         {"runDate": "2026-10-20 19:30:00", "distance": 3200, "duration": 1200}
       ],
       "totalDistance": 9600,
       "totalRuns": 3
     }
   }
   ```
4. 程序显示的报错文本，或“解析并测试”的识别结果。
5. 你的目标里程与截止日期，以及学校当前学期的有效规则（是否仍是每次 2–5 km、每天 1 次、96 km）。

---

## 10. 参考工具

- mitmproxy：<https://docs.mitmproxy.org/stable/>
- Reqable：<https://reqable.com/>
- Fiddler：<https://www.telerik.com/fiddler>
- Charles：<https://www.charlesproxy.com/>
