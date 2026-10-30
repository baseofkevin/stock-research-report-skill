# 接入 WeStock（腾讯自选股）MCP

> 什么时候需要看这篇：**agent 环境里没有挂上 `data_*` 工具**（在终端 / DSH / 别的 IDE 里跑），
> 但本机装了 WorkBuddy 并且已经连接过「腾讯自选股」。
> 如果工具已经能用，直接跳到 `scripts/render_report.py`，这篇不用看。
>
> **本文只写过程，不含任何本机凭据。** 换电脑照做一遍即可，凭据靠本机授权重新生成。

---

## 零、先决条件（缺一个都走不通）

| 条件 | 怎么确认 |
|---|---|
| 本机装了 WorkBuddy，且**在「连接器」里点过「连接腾讯自选股」** | `~/.workbuddy/connectors/*/.credentials.v3.json` 里有 `mcpOAuth` 且 key 以 `westock-mcp` 开头 |
| 插件缓存里有 westock-mcp 的 `mcp.json` | `~/.workbuddy/plugins/cache/workbuddy-connector-plugins-official/westock-mcp/*/mcp.json` |
| Node ≥ 18（脚本用内置 `crypto` + `node:https` / `node:http`，**不用全局 `fetch`**） | `node -v` |

**OAuth 必须人工点一次**，脚本不负责登录：换机器、换账号、token 过期，都要回
WorkBuddy 的「连接器」里重新授权。

---

## 一、三个关键位置

```bash
WB=~/.workbuddy

# ① MCP 端点（streamable-http）
cat $WB/plugins/cache/workbuddy-connector-plugins-official/westock-mcp/*/mcp.json
#   → mcpServers["westock-mcp"].url

# ② 账号目录（名字是账号 id，里面有两个文件）
ls -d $WB/connectors/*/           # 有 .credentials.v3.json 和 .master.key 的那个就是
#   .credentials.v3.json  → 加密后的 OAuth token（信封结构）
#   .master.key           → 32 字节主密钥（本机文件权限 0600）

# ③ 用脚本一次看清
node scripts/westock_client.js check
```

`check` 输出端点、账号、授权项、token 有效期，并做一次 `initialize` 验证连通性。
**它不会打印 token。**

---

## 二、凭据是怎么存的（看懂才能排查）

`connector-states.json` 里 `encryption` 段给出算法：

```json
{ "scheme": "aes-256-gcm", "kdf": "hkdf-sha256", "salt": "<base64>", ... }
```

`mcpOAuth` 里每一项的 `accessToken` / `refreshToken` 都是信封：

```json
{ "iv": "<base64, 12B>", "tag": "<base64, 16B>", "ct": "<base64>" }
```

推导方式（WorkBuddy 版本 2026-10 实测）：

| 项 | 值 |
|---|---|
| `ikm` | `masterKey` 字节 ‖ `userId` 的 UTF-8 字节 |
| `salt` | 信封所在文件的 `encryption.salt` |
| `info` | `"workbuddy-oauth-credentials-v1"`（写死） |
| `key` | `HKDF-SHA256(ikm, salt, info, 32)` |
| `aad` | `` `${userId}|${serverKey}|${fieldName}` `` |
| 解密 | AES-256-GCM，`iv` / `ct` / `tag` 均为 base64 |
| `userId` | **就是 `~/.workbuddy/connectors/` 下的目录名**（不带 `||enterprise` 后缀） |
| `serverKey` | `mcpOAuth` 的 key，形如 `westock-mcp|<hash>` |
| `fieldName` | `accessToken` / `refreshToken` |

> **AAD 是绑定的**：把 A 连接器的密文搬到 B 连接器、或把 `accessToken` 的密文搬到
> `refreshToken` 字段，都会解不开。所以四要素必须一一对应，不要自己拼。
>
> 如果哪天解密失败（`Unsupported state or unable to authenticate data`），说明 WorkBuddy
> 改了信封格式：在 `/opt/WorkBuddy/resources/app.asar` 里搜 `HKDF_INFO` 或
> `workbuddy-oauth-credentials-v1`，重新确认派生参数与 AAD 规则再改脚本。

---

## 三、调 MCP 的协议细节（踩过的坑）

1. **必须带 `Accept: application/json, text/event-stream`**，否则可能被拒。
2. 顺序：`initialize` → `notifications/initialized` → 任何业务调用。
   `notifications/initialized` **返回空体**（202），解析时要容忍空字符串。
3. **响应是 SSE**：真正的 JSON 在 `data: ` 那一行；有的接口直接返回 JSON，
   所以两种都要处理。
4. `Mcp-Session-Id` 在**响应头**里返回，后续请求要带上；不带上一般也能跑，但会话会重开。
5. `tools/call` 的结果在 `result.content[].text` 里，**text 本身又是一段 JSON 字符串**，
   要再解析一次。
6. 工具清单以 `tools/list` 为准（`data_search`、`data_quote`、`data_finance`、`data_consensus`…）。
   **不存在 `data_valuation`**：历史 PE/PB 只能靠 `data_quote(date=…)` 采样自建。

最小请求体：

```json
{"jsonrpc":"2.0","id":1,"method":"initialize",
 "params":{"protocolVersion":"2025-03-26","capabilities":{},
           "clientInfo":{"name":"my-client","version":"1.0"}}}
```

---

## 四、用脚本（推荐）

```bash
node scripts/westock_client.js check                     # 端点/有效期/连通性
node scripts/westock_client.js tools                     # 工具清单
node scripts/westock_client.js call data_quote '{"code":"sz301101"}'
node scripts/westock_client.js call data_finance \
     '{"code":"sz301101","fields":"all","num":16}' > /tmp/fin.json
node scripts/westock_client.js selftest          # 离线自检：不发请求、不读凭据
```

脚本做的事：找端点 → 找已授权账号 → 解密 token（只进内存）→ 走 MCP → 输出格式化 JSON。
两个环境变量：`WORKBUDDY_HOME`（换 WorkBuddy 安装位置）、
`WESTOCK_INTERVAL`（调用间隔毫秒，默认 1600，防限频）。

---

## 五、限频与重试（会真的踩到）

- 连续快速调用约 **80 次**后，服务端开始返回纯文本：
  `查询财报异常：error_type=2 suggest=2 msg=服务限频`
  此时**连 `data_finance` 也会被拒**。
- 需要**退避 ≥ 60 秒**，否则继续失败。
- **失败返回的不是 JSON**——脚本必须显式断言，否则会把「被限频」当成「那天没有数据」，
  静默产出一份缺数据的报告。`westock_client.js` 在这一步直接报错退出。
- **取数脚本的铁律**：`JSON.parse` 成功 **且** `ok === true` 才算拿到数据；否则 `exit` 非 0。
  `westock_client.js call` 在工具返回纯文本时以 **exit 3** 退出，并把原文同时写 stderr 和 stdout——
  不要用 `2>/dev/null` 把唯一的现场信息丢掉。
- **两层判定别混**：`ok:true` + 空数组是**合法空返回**（不重试、记 `data_gaps`）；
  非 JSON 是**调用失败**（报错、别当没数据）。两者的处理规则见 `westock-接口.md` 5.0。
- 批量采样（例如历史估值分位）**间隔 ≥1.6 秒，建议月末采样 40~85 个点（最多 120）**；
  上市不足 4 年就采上市以来全部月末，满 4 年采最近 48 个月末。不要逐交易日（1200+ 次必然限频，
  对分位精度也没有实质提升）。

---

## 六、安全红线

1. **token 只在内存里用**，不打印、不写进报告、不进 git、不贴进对话。
2. 需要临时落盘时（例如把 token 交给另一个进程），用 `/tmp` 下的临时文件并**用完即删**。
3. **不要把 `.master.key` + `.credentials.v3.json` 拷到别的机器**——那等于把账号权限一起搬走，
   而且违背了「凭据随本机授权生成」的设计。换机器就重新点一次授权。
4. 本脚本只读本机已有凭据，**不做任何绕过鉴权**的事；它拿到的权限和你在 WorkBuddy 里
   授权的一致（当前是 `read write`）。
5. 只在**自己的机器、自己的账号**上用。给别人跑报告时，让对方自己授权。

---

## 七、排查表

| 现象 | 原因 | 处理 |
|---|---|---|
| `没找到 westock-mcp 插件` | 没装连接器，或版本路径变了 | 在 WorkBuddy 连接器里装/更新；或手动找 `mcp.json` |
| `没有找到已授权的 westock-mcp 凭据` | 没点过「连接」 | 在 WorkBuddy 里授权一次 |
| `HTTP 401 / missing or malformed Authorization` | token 过期或被吊销 | 重新授权；脚本 `check` 会显示有效期 |
| `Unsupported state or unable to authenticate data` | AAD/uid 不匹配，或信封格式变了 | 用账号目录名当 userId；仍失败则按第二节重新确认规则 |
| 返回纯文本「服务限频」 | 调太快 | 退避 60 秒，间隔调到 ≥1.6 秒 |
| `返回不是 JSON` 但内容是「请提供搜索关键词」「成分股查询需要 code 或 codes」 | 参数写错（不是没数据） | 按 `westock-接口.md` 6.5 补参数；`call` 此时 exit 3 |
| `返回不是 JSON` 但内容像 HTML | 被网关拦了 | 检查网络/代理；确认 `Accept` 头 |
| `RangeError: WebAssembly.instantiate(): Out of memory` | 沙箱里 undici 的 llhttp WASM 分配失败（与账号无关） | v2.7.1+ 已改用 `node:https`，确认脚本是最新的；旧版必崩 |
| 工具名不存在 | 记错名字了 | `tools` 看真实清单 |
| `call` 输出正常但脚本下游报 JSON 解析错 | 工具返回纯文本、旧版还会 exit 0 | 升级脚本；自查 `node scripts/westock_client.js selftest` |
