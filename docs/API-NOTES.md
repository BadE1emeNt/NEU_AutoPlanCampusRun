# 校园乐跑接口记录

> 状态：**账号登录 + 数据接口已实现**（2026-10-24）。
> 数据来自官方 H5 `tybzhtypt.neu.edu.cn/bdlp_h5_fitness_test` 与学校 CAS。
> 本文用合成数据举例，不包含任何真实学号/姓名/token。

## 1. 客户端 / 入口

| 项目 | 值 |
|---|---|
| 入口 | 「智慧东大」App 内“校园乐跑”H5 |
| H5 根路径 | `https://tybzhtypt.neu.edu.cn/bdlp_h5_fitness_test/view/db/` |
| 认证 | 学校统一身份认证 CAS（`pass.neu.edu.cn`） |
| 协议确认时间 | 2026-10-24 |
| 工具 | 用户提供的 HAR（登录后页面 + 体育平台 API） |

## 2. 登录链路

```text
GET  https://pass.neu.edu.cn/tpass/login?service=<体育平台 neuLogin>
  -> 解析 lt / execution / login_neu.js 里的 RSA publicKeyStr
POST https://pass.neu.edu.cn/tpass/login?service=...
  form: un, pd, rsa=RSA_PKCS1(学号+密码), ul, pl, lt, execution, _eventId=submit
  -> 302 体育平台 /login/neuLogin?ticket=ST-...
GET  https://tybzhtypt.neu.edu.cn/bdlp_h5_fitness_test/public/index.php/index/login/neuLogin?ticket=...
  -> 302 /login/neuLogin -> 302 /view/db/#/pages/index/index?...&token=<32hex>&uid=...&student_num=...
```

- `service`：`https://tybzhtypt.neu.edu.cn/bdlp_h5_fitness_test/public/index.php/index/login/neuLogin`
- CAS RSA：2048-bit，JSEncrypt/PKCS#1 v1.5，Base64；明文是 `学号 + 密码` 直接拼接。
- `ul` / `pl`：学号/密码长度。
- 短信二次认证：CAS 登录返回页若出现 `phone(murmur, details)`，先 `POST /tpass/device {m:2}` 发送，
  再 `POST /tpass/device {d,i,m:3,u,c,s:1}` 校验；`s=1` 表示信任设备。
- 登录成功最终 URL 参数：`token, uid, school_id, student_num, card_id, term_id, user_type`。

> 实测：用 HAR 中的 CASTGC 可以重新走 `neuLogin` 拿到新 token；token 单独即可调用 API（不需要 Cookie）。

## 3. 体育平台 API

- Base：`https://tybzhtypt.neu.edu.cn`
- 路径前缀：`/v3/api.php/`
- 方法：全部 `POST`
- Content-Type：`application/x-www-form-urlencoded`
- 请求体：`ostype=5&data=<AES-128-CBC(JSON)>`
- 响应：`{"status":1,"is_encrypt":1,"data":"<AES(JSON)>"}`

### 加密参数（客户端静态常量）

| 项目 | 值 |
|---|---|
| AES | AES-128-CBC / PKCS#7 |
| key | `Wet2C8d34f62ndi3` |
| iv | `K6iv85jBD8jgf32D` |
| 签名盐 | `rDJiNB9j7vD2` |

### 签名

```text
sign = MD5( 按 key 升序拼接 (key + value) + salt )
```

`value` 使用 JSON 里的原始类型（数字/字符串）；签名时不含 `sign` 字段。

### 基础字段

```json
{
  "uid": "1000001",
  "token": "<32 hex>",
  "school_id": "833",
  "term_id": "4771",
  "course_id": 0,
  "class_id": 0,
  "student_num": "20260001",
  "card_id": "20260001",
  "timestamp": 1792851859,
  "version": 1,
  "nonce": "163557",
  "ostype": "5",
  "role": 1,
  "sign": "<md5>"
}
```

### 用到的端点

| 端点 | 用途 | 额外字段 |
|---|---|---|
| `WpLogin/UserInfo` | 姓名、uid、学院、role | — |
| `WpRun/getTermList` | 学期列表（`status=1` 为当前） | `term_id=0` |
| `WpRun/getTermRunRecord` | 当前学期记录 | `term_id`, `page` |
| `Run2/beforeRunV260` | 跑步规则/场地/学期起止（可选） | — |
| `WpIndex/index` | 首页模块（含“校园乐跑”入口） | — |

### 记录字段

```json
{
  "id": "100001",
  "start_time": "1792406628",
  "end_time": "1792408267",
  "distance": "3.47",
  "record_status": "1",
  "title": "东北大学某体育场",
  "tag": "定向乐跑"
}
```

- `start_time` / `end_time`：Unix 秒。
- `distance`：公里。
- `record_status`：`1` 有效。
- 学期汇总：`total_num` 次数、`total_distance` 公里（可能含未计分/历史）。

## 4. 规则核对

| 规则 | 观察 |
|---|---|
| 单次有效 | 2–5 km（`beforeRunV260.time_rule_arr.min_distance/max_distance`） |
| 每天有效 | 1 次 |
| 学期目标 | 96 km（工具默认，待按学校当期确认） |
| 配速 | 3–10 min/km（`min_pace/max_pace`，单位秒） |

## 5. 实测记录

| 日期 | 操作 | 结果 |
|---|---|---|
| 2026-10-24 | HAR 解析 token + API | 成功，5 次 / 17.38 km |
| 2026-10-24 | token 单独请求（无 Cookie） | 成功 |
| 2026-10-24 | CASTGC 重新走 neuLogin | 成功拿到新 token |
| 2026-10-24 | CAS 密码 POST | 本地 mock 通过；**待真实账号验证** |
| 待填 | 短信二次认证 | 待验证 |

## 6. 后续

- [ ] 用真实账号验证 CAS 密码 + 短信流程；
- [ ] 如学校改版，更新 CAS publicKey 动态读取/API 端点；
- [ ] 从 `beforeRunV260` 自动读取学期结束日/目标；
- [ ] 增加真实接口 fixture（脱敏）到测试。
