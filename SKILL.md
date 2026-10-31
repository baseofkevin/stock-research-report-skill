---
name: stock-research-report
version: 2.11.0
schema_version: "2"
updated: 2026-10-31 16:10
description: 输入股票代码或名称，从腾讯自选股（WeStock）调取行情、季K线、三大报表、机构预期等数据，按用户私人笔记的解读范式完成企业分析，输出美化布局的 HTML 企业信息解读报告；远程原始返回与 skill 计算结果合并保存为同名 JSON，三件套路径由 skill 根目录 env 配置。触发词：企业信息解读、个股分析、解读一下、股票分析、帮我看看 XXXX、财报解读、研报式个股分析。
---

# 企业信息解读报告（个股分析 Skill）

把「股票代码」变成一篇**像人写的、有明确结论的**企业信息解读报告，输出为美化的 HTML。

> 分析范式来自用户的私人笔记（「公司财务解读」B 系列，路径随机器不同，以本地笔记为准），
> 指标体系来自《企业财务分析指标体系手册》。
> **三条铁律贯穿全程：现金流 > 利润；趋势 > 时点；结构 > 总量。**

---

## 何时使用

用户给出股票代码、名称或「帮我看看 XXX」时触发。典型输入：

- `解读一下 sz300470`
- `帮我看看 600519` / `分析下贵州茅台`
- `给我出一份 中远海控 的企业信息解读报告`
- `这只票怎么样？002519`

> 同一家公司再次研究：先查 `env` 输出目录，已有报告就只更新 `.json/.html/.md` 三件套，
> **不要重跑全量取数**；只有第一次研究的公司才完整获取信息。详见「两条路线」。

**不支持港股、美股**。碰到 `00700`、`AAPL` 这类代码直接说明，不要用 A 股口径（扣非、合同负债、商誉）硬套。

---

## 前置条件

**主要数据源：腾讯自选股（WeStock）Connector。**
工具前缀 `data_*` / `tool_*`。

**如果 `data_*` 工具没挂在当前环境里**（在终端 / 别的 agent 里跑），但本机 WorkBuddy
已经连接过腾讯自选股，直接用 `scripts/westock_client.js` 取数：

```bash
node scripts/westock_client.js check        # 端点 / token 有效期 / 连通性
node scripts/westock_client.js tools        # 真实工具清单
node scripts/westock_client.js call data_finance '{"code":"sz301101","fields":"all","num":16}'
```

接入原理、凭据位置、协议细节、限频与排查表见 `references/接入WeStock.md`。
**该文档只写过程，不含任何本机凭据**；换电脑重新在 WorkBuddy 里授权一次即可。

> **`check` 报 `RangeError: WebAssembly.instantiate(): Out of memory`** 说明当前容器/沙箱里
> undici 的 llhttp WASM 分配失败，**与账号、网络都无关**。v2.7.1 起脚本已改为 `node:https`
> 直连（不再用全局 `fetch`），先确认拿到的是最新脚本；仍是旧版就更新，不要自己去绕 WASM。

**只做 A 股**（沪 / 深 / 北交所），不覆盖港股、美股。
代码规范：沪 `sh600519`、深 `sz000001`、北交所 `bj830799`。
用户给的是港股/美股代码（如 `00700`、`AAPL`）时，**直接说明本 skill 不支持，不要硬套 A 股口径**。
用户只给名称或 6 位数字时，**必须先 `data_search` 拿到带前缀的代码**。

---

## 报告骨架（八节，顺序不要变）

六段式是**思考路径**，成稿展开为八节。写之前先看这张表，别漏节、别乱序：

| 节 | 标题 | 内容 | 必备图/表 | JSON 键 |
|---|---|---|---|---|
| 一 | 股价位置 | 历史区间、当前分位、均线状态 | 季度收盘价走势 | `price` |
| 二 | 主要指标初步研判 | 摘要卡片（≥10 项）+ **一句初步判断（`core_summary`）** | 指标卡网格 | `core_metrics` / `core_summary` |
| 三 | 生意本身 | 卖什么、产业链地位、**护城河** | 分部表 + **五指标表 + 两张趋势图 + ROIC/WACC 卡 + 来源表** | `business` / `business.moat` |
| 四 | 财务全景与跨年趋势 | 单季 + 同季同比 + TTM 三层口径 | 多张趋势图 + 资产负债明细 | `financials` |
| 五 | 排雷扫描 | 25 条清单只列命中项；**零命中也要输出 0 / 25** | — | `redflags` / `redflags_checked` |
| 六 | 七步研判与打分卡 | 七步留痕 + 16 项加权 | 七步表 + 评分条 | `scorecard` |
| 七 | 企业估值 | **PE/PB/PS 当前在历史曲线上的位置** | **三条走势曲线（横轴时间，末端标当前值）** | `valuation` |
| 八 | 综合研判与跟踪清单 | 结论 + 触发条件 | — | `conclusion` |

- 三节的护城河、七节的估值图是 **v2.3/v2.4 起的新硬要求**，缺了 `validate.py` 会报错、报告会缺块。
- **八节的职责不重叠，别在一节里把话说尽**：
  **二**摆数 + 一句初判（「初步看，增收不增利，现金流比利润好看」）；
  **六**摊开推导（七步 + 打分卡，让人能反驳）；
  **七**只判贵不贵（三条曲线 + 三个分位）；
  **八**定性和跟踪（stance、触发条件）。
  二节把结论说死，六、八节就没得写；七节写成「PE 多少倍所以贵」，就把历史位置丢了。
- **v2 必须给 `valuation` 块**：哪怕样本不足 20 个点，也要给 `current` + 已有 series + 注明「样本不足」；
  `validate.py` 把八节都当必需块，整节省略会直接报错。v1 旧数据没有 `valuation` 时，编号仍按实际节连续生成；**不要手写死编号**。
- 节标题编号由渲染器按实际存在的节连续生成；`conclusion_title` 等只覆盖标题文字，不覆盖编号。

---

## 第 0 步 · 先确认三件事（决定走增量还是全量）

1. **有没有研究过**：先查 `env` 输出目录，**不要一上来就调 16 个接口**。
   ```bash
   python3 scripts/report_cache.py lookup --code {code} --name {名称} --json
   ```
   - `cached: true` + `has_data: true` → 已研究过：默认走**增量更新**，复用旧 JSON 里的
     `raw_data` 和计算结果，只更新 `.json` / `.html` / `.md` 三件套（见下方「两条路线」）。
   - `cached: true` + `legacy_only: true` → 只有旧 HTML/MD、没有数据 JSON：先完整取数一次补齐 JSON。
   - `cached: false` → 以前没研究过：走完整五步取数。
   - 用户只给名称或 6 位数字也能查（`--name` / `--code 301101`），**不必先联网 `data_search`**。
   - **只更新三件套时，下面第 2、3 条也不用重新确认**：沿用旧 JSON 的 `report_date` / `price_at`；
     只有要刷新行情或新财报，才重新确认报告期和行情时点。
2. **报告期**：调 `data_disclosure`，它会返回最新定期报告的 `reportEndDate`（报告期）
   和 `disclosureDate`（披露日）。**别把上一期当「最新一期」**，也别在披露前抢跑。
   报告里必须写明「{报告期} · {M 月 D 日}披露」。三季报集中在 10 月下旬、年报 3–4 月、中报 8 月。
3. **行情时点**：盘中取价要写成 `YYYY-MM-DD HH:MM 盘中`（`meta.price_at`）。
   PE / PB / 历史分位 / PEG / 股息率 / 买卖区间**全部由这个价格推出**，
   收盘后要按收盘价复核一遍，两个时点的数字不一致时以收盘为准。

**日期口径（别把报告日、行情时点、财报期、披露日混用）**：

| 字段 / 数据 | 含义 |
|---|---|
| `meta.report_date` | 行情/报告基准日（`YYYY-MM-DD`），决定文件名里的 `{date}` 和估值末点 |
| `meta.price_at` | 具体时点描述（`2026-10-30 收盘` / `2026-10-30 09:42 盘中`） |
| `financials.latest.period` / `periods[-1]` | 财报报告期（如 `2026-09-30`） |
| `data_disclosure.disclosureDate` | 法定预约披露日 |
| `data_notice[].time` | 公告实际发布时间 |

`disclosureDate` 与 `data_notice.time` 不一致时（例如预约 10-29、公告 10-28 盘后），
**两个都写**：“公告 10-28 盘后发布，法定披露日 10-29”，不要只留一个。

---

## 两条路线：已研究过 vs 第一次研究（v2.9.0 起）

**先查缓存，再决定要不要取数。** 输出目录里已有这家公司的 JSON（按 `meta.code` 优先、
`meta.name` 兜底匹配），就不要再跑一遍完整取数。

| 情形 | 做法 | 命令 |
|---|---|---|
| **已研究过 · 只更新三件套**（不取新数） | 复用旧 JSON（含 `raw_data` 与计算结果），按 `env` 重写同名 `.json/.html/.md` | `python3 scripts/save_report.py --reuse --code {code}` |
| **已研究过 · 要刷新行情/新财报** | 只补变化项（如 `data_disclosure` + `data_quote`；报告期变了再加 `data_finance`），把新返回追加进采集包；**不要重跑 16 类接口和 40~85 次月末采样** | `python3 scripts/save_report.py new.json --reuse --raw new-raw.json` |
| **第一次研究** | 完整走五步：16 类接口 + 月末采样 + 跨源补数 + 计算 + 研判 | `python3 scripts/save_report.py data.json --raw full-raw.json` |

- 增量更新时，旧 JSON 的 `raw_data` 会自动保留，新采集包会**追加**到 `calls`，不会覆盖旧证据。
- 估值月末采样只在需要新增月份时补最近几个月，不全量重采；`data_kline` 同理，别为了一个季度重拉 40 根。
- 旧报告没有 `raw_data`（v2.8.0 之前）时：先完整取数一次补齐，再改走增量。
- **输出目录里只有旧 `.html/.md`、没有 JSON**（v2.8.0 之前的历史报告）：`lookup` 会返回
  `legacy_only: true`，并从文件名/首行标题识别公司。这种报告**不能直接 `--reuse`**，
  先按完整取数一次生成同名 JSON（旧 HTML/MD 保留，按新报告日命名，不覆盖旧文件），
  之后就进入增量路线。
- 同公司有多份历史 JSON 时，`report_cache.py` 按 `report_date` / 修改时间取最新；文件名带旧日期不影响识别。
- 用户明确说「重新完整研究一遍」时，才允许走全量路线。

---

## 执行流程（首次研究走五步；已研究过的公司按上方增量路线，不要重跑）

### 第 1 步 · 取数

按 `references/westock-接口.md` 第二节的清单调用。**16 次接口调用 + 1 轮历史采样**（`data_kline`、`data_quote` 各用两次；采样那一行本身要跑 40~85 次）：

```
data_search       → 名称转代码
data_quote        → 现价、涨跌幅、市值、PE/PB、股息率
data_kline        → period=season, limit=40, fq=qfq   （季K线，判断股价位置）
data_kline        → period=year,   limit=10, fq=qfq   （年K线，补长周期）
data_profile      → 主营业务、行业、股本
data_disclosure   → 最新定期报告的 reportEndDate + disclosureDate（第 0 步用）
data_finance      → fields="all", num=16               （三大报表全字段，至少 16 期）
                     ※ fields 不传 = "core"（实测 24 个字段），会缺应付/存货/应收/合同负债/股本的绝对额
data_quote        → 再按 date=YYYY-MM-DD 做**月末采样**（上市不足 4 年就采上市以来全部月末；
                     满 4 年采最近 48 个月末；总量约 40~85 个点，不足 40 就用全部），
                     自建 PE/PB/PS 历史曲线
                     ※ 没有 data_valuation 这个工具；必须间隔 ≥1.6 秒，约 80 次后触发「服务限频」，
                       退避 ≥60 秒再续；脚本要断言返回是 JSON，别把限频当成「那天没数据」
                     ※ data_quote 的 total_market_cap：当前值是「亿元」，历史 date 查询返回「元」；
                       用历史市值算 PS 时必须 /1e8，否则会差 1 亿倍
                     ※ PS 需要分母：同一次 `data_finance` 里的 `OperatingRevenueTTM`，
                       按 `InfoPublDate` 做前视过滤（不用未来的报表算过去的 PS）
data_consensus    → 机构一致预期（动态 PE 的来源）
                     ※ netProfit / revenue 单位是「万元」，eps 是「元」；用前先 /1e4 换成亿元
data_rating       → 机构评级
data_dividend     → years=5                            （分红连续性）
data_shareholder  → 股东结构
data_risk         → 质押、解禁、诉讼、ST
data_notice       → limit=20                           （公告：重组/减持/业绩预告）
data_news         → limit=20
data_sector       → mode=search 后 constituent         （同业对比）
data_score        → 诊股评分（只作交叉参考，不替代自己的判断）
```

**护城河要 ≥5 年，16 期不够**：`num=16` 是 4 个年报。§9 要求至少 5 年，
再补一次 `data_finance(fields="all", num=28)`（7 年）；或第一次就直接用 `num=28`。
护城河表里的 `years` 与 `metrics.rows[].values` 必须按这次 28 期的年报铺开。

**取数预算（计划值，不是硬上限）**：基础 16 + 东财 F10 2 + 护城河补数 1 + 同业 2~4 + 月末采样 N。
服务端约 80 次触发限频，因此 **16 + 2 + 1 + 4 + N ≤ 75 → N ≤ 52**；
若必须采 60 个月，就砍掉同业或分批跑（采样放最后，限频后退避 ≥60 秒再续）。

**月末采样不要手写循环**，直接跑：

```bash
python3 scripts/sample_valuation.py --code {code} --raw "$RAW" --years 5
# 先看会采哪些月份
python3 scripts/sample_valuation.py --code {code} --raw "$RAW" --start 2021-11-01 --end 2026-10-31 --dry-run
```

脚本只补采集包里缺的月份；空返回自动回退前一个交易日，超时/限频分开退避，
每成功一次立即落盘。**采集包必须先 `init`**；`collect_raw.py run/add` 默认不再静默新建。

**采样脚本运行期间不要用 `collect_raw add/run` 写同一个采集包。** 现在两边都走
`raw_bundle.locked()` + 锁内「重读 → 追加 → 写回 → 回读」，「已记录」也不再是空话；
但并发写只会让你排在锁上等，串行做更省事（这也是 v2.10.1 之前那次丢数据的直接原因）。

**另有三个补充动作，不属于 WeStock 接口，但同样必须做**：

| 动作 | 做法 | 为什么必需 |
|---|---|---|
| 估值月末采样 | `data_quote(date=YYYY-MM-DD)` 逐月跑 40~85 次（见上面第 8 行） | 第七节的 PE/PB/PS 曲线全靠它，没有它这一节出不来 |
| 资本支出 | 东财 F10 `RPT_F10_FINANCE_GCASHFLOW.CONSTRUCT_LONG_ASSET`，按年报取 | WeStock 现金流量表无此科目；没有它算不出 FCF，第三节护城河缺一半 |
| 主营构成 | 东财 F10 `RPT_F10_FN_MAINOP`（`MAINOP_TYPE`：1 产品 / 2 行业 / 3 地区） | WeStock 没有分部收入；没有它第三节的分部表只能定性，算不出各业务毛利额占比 |

**为什么是 16 期（4 年），不是 8 期**：单季倒挤、同季同比、TTM 三件事同时要数据——
算 2026Q3 单季要 2026 中报；算同季同比要 2025Q3 累计；算 TTM 要 2025 年报。
**16 期只有 4 个年报，护城河 ≥5 年不够**；护城河另补一次 `num=28`（7 年报），不要拿 4 年报硬撑。
8 期只够两年季报，连第 4 节「财务全景」的门槛（≥10 期）都到不了。

**实测边界（2026-10-30，别踩）**
- `fields="all"` 的资产负债表字段数**随公司科目有无变化**：`sz301101` 49 个、`sh600315` 51 个、`sh600519` 53 个。
  常见的 `NotAccountsPayable`（应付账款）、`OtherReceivableED`（其他应收）、`TradingAssets`（交易性金融资产）、
  `ContractLiability`（合同负债）、`TConstruInProcess`（在建工程）、`RetainedProfit`、`CapitalReserveFund`、
  `PaidInCapital`（股本）、`NonCurrentLiabilityIn1Year`（一年内到期非流动负债）都在 `all` 里。
  **别用默认 `core`（实测 24 个字段）然后写「接口拿不到」——那是没传参。**
- 商誉字段是 **`GoodWill`**（大写 W），不是 `Goodwill`；`sh600315` 2026-09-30 为 14.55 亿、占归母净资产 19.57%。
  长期借款 **`LongtermLoan`** 也在（`sh600315` 3.20 亿）。某只股票缺 key 通常是该科目为 0/无，不是接口没有；
  拿不到就标 0 并在 `data_gaps` 注明「接口未返回，按 0 处理，待 F10 复核」。
- **不保证返回**的字段：短期借款 `ShortTermLoan`（**常见但非必然**：000629 的
  `fields="all"` 返回了 1.20 亿，600519/600315 未返回）、存货的产成品/发出商品拆分、
  前五大客户集中度。未返回时短期借款可用
  `InterestBearDebt − LongtermLoan − NonCurrentLiabilityIn1Year − LeaseLiabilities` 估算，
  取不到就用合计保守替代；这三项走 `data_finsearch` 或年报附注，拿不到就标「不可评」。
- `data_finance` 的 `_Q` 单季字段与倒挤一致，可互验；**仍以倒挤为准**，顺带当一致性检查。
- 服务端限频：连续快速调用约 80 次后报 `服务限频`，之后需要退避 ≥60 秒。
  采样脚本必须断言返回是 JSON，否则会把限频当成「那天没数据」。

**取数纪律**
- 同一市场、支持 `codes` 的工具只调一次，逗号分隔。
- `ok:false` 时**原样转述 message，禁止编造**。
- **`ok:true` 但 `data` 是空数组/空对象 = 合法空返回**（例如 `data_shareholder` 对部分标的
  三个列表全空、`data_dividend` 返回 `{"ok":true,"data":{}}`）：**不要重试**（只会烧限频额度），
  该指标判「无数据」、写 `data_gaps`。分红空对象还要用 `data_quote.dividend_ratio_ttm`
  交叉判断是「零分红」还是「无数据」，别直接写 0。
- **返回不是 JSON 要分两种**：
  - **③a 调用失败**：限频 / 参数错 / 鉴权失败 / 工具不存在 → 立刻停或退避重试，保留原文；
  - **③b 文本形式的「业务无数据」**：`未找到…` / `暂无…` / `无数据`（如
    `data_consensus` 返回 `未找到一致预期数据`）→ 按合法空返回处理，**不重试**，
    写 `data_gaps`，不要当成参数写错。
  `westock_client.js call` 对纯文本统一 exit 3，所以要看原文语义再分类。
- 接口拿不到的字段，先同源替代（consensus → 动态PE，rating → 反推预测净利），
  **覆盖机构 < 3 家时 PEG 只能作参考、不得单独作为估值档位的主依据**；
  `data_rating.ratingCnt` 是**评级记录条数**，不是覆盖机构数（两者会打架，见接口文档 §6.4）。
  再用 `data_report` / `data_news` 的文字口径；**仍没有就写「暂无披露」，判定置为「无数据」**。
  **绝对不能用训练记忆或常识补具体数字。**
- **把每一条原始返回都收进同一个采集包**，最后由 `save_report.py` 并入交付 JSON 的
  `raw_data` 字段；报告是可复算的，不是一次性聊天产物。**不要再散成多个
  `{code}-raw-{YYYYMMDD}.json`，也不要另起「数据源 JSON」的名字**（见下方「原始返回怎么留」）。

**原始返回怎么留（v2.8.0 起，硬要求）**

WeStock 的 `data_*`、月末采样的每一次 `data_quote`、东财 F10 补数、网页补数，
**全部进同一个 `raw-v1` 采集包**：

```bash
RAW="${PWD}/.raw/{code}-raw.json"
mkdir -p "$(dirname "$RAW")"
python3 scripts/collect_raw.py init "$RAW" --code {code}

# 走脚本取数：run 会调 westock_client.js，并把完整返回写进采集包（推荐）
python3 scripts/collect_raw.py run "$RAW" --tool data_quote --params '{"code":"{code}"}'

# 走 data_* connector 工具：把返回原样存成文件，再 add
python3 scripts/collect_raw.py add "$RAW" --tool data_finance \
  --params '{"code":"{code}","fields":"all","num":16}' --response-file /tmp/finance.json

# 东财 F10 / 网页补数同样留痕
python3 scripts/collect_raw.py add "$RAW" --source eastmoney \
  --tool RPT_F10_FN_MAINOP --url "$F10_URL" --response-file /tmp/mainop.json

python3 scripts/collect_raw.py status "$RAW"
```

- **`ok:false` 也要记**：`response` 原样保留；非 JSON（限频原文、参数错）用
  `--text` 或 `--response-file` 记录成 `raw_text`，不能丢。
- 月末采样的 40~85 次 `data_quote` 也逐条进 `calls`；`collect_raw.py run` 沿用客户端的
  1.6 秒间隔，**不要自己并发**。
- 采集包只是临时中转；**最终只交一个 JSON**：根节点是计算结果，`raw_data` 是原始返回。

### 第 2 步 · 计算

对照 `references/指标体系.md`（章节编号与手册十四章对齐）逐项算出，**不要跳项**：

- **§1 安全四项**：现金短债比、净现比（四档）、应收增速差、速动比率 + 流动比率、营运资本
- **§2 改善三项**：单季毛利率序列（先用「本期累计 − 上期累计」倒挤，别直接用累计口径字段）、
  合同负债同比与规模、OCF_TTM 与 `OCF_TTM ÷ NP_TTM`
- **§4 盈利质量**：毛利率（**并拆分产品/地区，算各业务毛利额占比**）、净利率、
  扣非占归母比、扣非增速 vs 归母增速缺口、ROE/ROA/ROIC、**股本占净资产比**（家底来源）、
  **每股营收/每股经营现金流/每股净资产**（看穿股本扩张）
- **§5 成长**：营收增速、净利增速、二者四象限定性、三费率、**费用增速 vs 营收增速**
- **§6 现金流**：OCF、FCF、三流组合正负组合
- **§7 资产质量**：货币资金占比、应收占营收/占总资产、存货周转天数、存货增速 vs 营收增速、
  **营运资本占用（应收 + 存货 − 应付）与产业链地位**、在建工程趋势、商誉占净资产比、
  **其他应收款占总资产比**
- **§8 安全**：资产负债率（**剔合同负债**）、有息负债及其趋势、**毛利额 ÷ 利息费用**
- **§9 护城河**：① 五指标按年铺开（**FCF、FCF/营收、净利率、ROE、ROA**，≥5 年）；
  ② 两张趋势图（FCF 柱 + FCF/营收 线；净利率/ROE/ROA 三线）；
  ③ **ROIC 减 WACC**（贴出 Rf / ERP / β 假设，看差值正负与是否收窄）；
  ④ 来源五类（无形资产/转换成本/网络效应/成本优势/有效规模）逐条给证据，
  **一条都占不到就写「无护城河」**，不要拿管理层优秀或行业景气凑数。
  ※ FCF 的资本支出用「购建固定资产、无形资产和其他长期资产支付的现金」，
  不能用投资活动现金流净额（后者含买理财，会算出巨额负数），**更不能用接口的 FCFE/FCFF**
  （口径不明，上海家化 2024 年差 16 亿）；WeStock 现金流量表没有这个科目，
  从东财 F10 `RPT_F10_FINANCE_GCASHFLOW.CONSTRUCT_LONG_ASSET` 补，并注明跨源。
- **§3 估值**：静态/滚动/动态 PE 三者及**梯度解读**、PB、**经营性 PB**（剔理财与商誉；理财口径见 §7.1：交易性金融资产 + 其他流动资产中的理财 + 一年内到期大额存单，**不含货币资金**）、
  PEG、股息率
- **估值分位（第七节，成图）**：PE / PB / PS 三个都要，各画一条**走势曲线**
  （横轴时间、纵轴倍数，当前值标在曲线末端，加中位虚线），并给出分位百分比。
  **三个分位要一起读**：全在低位才是全面便宜；只有 PB/PS 低而 PE 高（或反之）说明分母被扭曲了。
  口径必须交代（统一见 `references/指标体系.md` §3.5 的「分位口径表」）：PE 为负的年份不进样本；
  **一次性收益、商誉减值污染分母时要给出「剔除后 PE」并重算分位**；**样本含极端值
  （>100 倍或 >3 倍中位）时必须另给缩尾分位 `percentile_trimmed`**，并在 `note` 写明
  「样本内最高 X 倍、出现在何时、为什么」——名义便宜 ≠ 真便宜。

口径规则：
- 同比要标清楚：**年报对年报，半年报对半年报**；
  单季 = 本期累计 − 上期累计；TTM = 本期累计 + 上年全年 − 上年同期累计。
- **每个比率都要同时给分子分母的绝对额**，只给百分比等于没说。
- **拿不到数据的项：判定写「无数据」，报告里写「暂无披露」，并进入 `data_gaps` 清单；
  但打分卡不计 0 分**——0 分是「中性」，缺数据是「不知道」，两者混起来会把数据不全的公司
  判成「公司变差」。缺项一律**从分母里剔除**（归一化，见 §13「缺项处理」）。

### 第 3 步 · 研判

按 `references/指标体系.md` §0 的**七步流程**走，每一步都要留痕（报告里的 `scorecard.steps`）：

1. 验真伪 → 2. 看趋势 → 3. 查质量 → 4. 排雷 → 5. 定性质 → 6. 交叉验证 → 7. 问价格

**必须完成的三件事（缺一不可）**：

1. **逐条过 §12 排雷清单 25 条**，把命中的写进 `redflags`（**只写命中的**，每条带 `id`=清单编号），
   每条都要给出证据数字（分子分母绝对额 + 阈值对照）；**一条都没命中也要写 `redflags_checked: 25`，
   报告里固定输出「命中 0 / 25 条」。**
   **零命中时 `redflags_note` 必填**（≥10 字）：说明为什么一条都没中、点名最接近命中的三条
   （现金流 / 商誉 / 应收），并把「沾边但不够阈值」的观察写在这里——301087 的
   「OCF −55.2% 却没命中任何一条」就是典型：**清单没命中 ≠ 没有问题**。
2. **跑 §10 科目变动矩阵**：先用「收入↑↓ × 毛利↑↓」定象限（A/B/C/D），
   再逐行核对现金、应收周转天数、存货周转天数、三费、应付周转天数、长短借款、合同负债
   这七类科目的变动是否"讲得通"。这一步的结果写进 `scorecard.steps` 第 6 步和 `conclusion`。
3. **填 §13 打分卡**（16 项 × 权重，满分 66），然后**用 §13 的结论矩阵推出 stance**——
   **不许拍脑袋定结论**。矩阵只有三轴：**有没有一票否决 → 得分率档位 → 估值档位**
   （PEG / 经营口径 PB 分位）。落在格子之间时，选**更保守**的那一档，并在 `conclusion` 里说明理由。

**三个已知的机械口径陷阱，必须人工复核**：
- **应收增速差**：营收塌方型企业会误报（应收绝对额没涨、营收大跌，差值反而大正）。
  回看应收**绝对额**再定性。
- **静态 PE 为负**：亏损年份的 PE_LYR 是负数，不代表便宜，只能看 PB 和 TTM。
- **历史分位**：上市不足 5 年的公司，「近 5 年分位」的分母是上市以来全样本，
  必须在报告里注明样本区间与天数，不能拿次新股上市初期的泡沫当基准。

### 第 4 步 · 撰写

严格按 `references/解读范式.md` 第二节的**八节写法模板 + 句式**写（那一节按成稿顺序排，跟着走就不会漏节）。
核心要求：

- **有明确结论，不骑墙**（看好 / 谨慎观望 / 不看好 / 等安全边际），
  stance 由第 3 步的打分卡映射推出，不是写文章时再想。
- 每个判断后面必须跟数字；矛盾点（净利增但现金流降、毛利升但应收暴增）要指出来。
- **资产负债表明细必须给全**（四节的最低要求）：货币资金、短期借款、长期借款、
  应收、存货、**应付账款**、在建工程、商誉、未分配利润、资产负债率。
  拿不到的写「暂无披露」，并进 `data_gaps`。
- **二节收尾必须有一句初步判断**（`core_summary` 字段，渲染在指标卡之后，如「初步看，增收不增利，
  现金流比利润好看」）。**这一节不下结论**——定性归六节推导、八节收口，摘要卡上把话说死，
  后面两节就空了。`validate.py` 会检查 `core_summary` 非空。
- **生意那一段要说出产业链议价地位**（`应收 + 存货` 与 `应付` 谁大）——
  这决定了公司是占用别人的钱做生意，还是自己垫资做生意。
- **护城河按四步写**（`business.moat` 对象）：结论先行（宽/窄/无 + 一句话）→
  五指标按年列表（FCF、FCF/营收、净利率、ROE、ROA）→ 两张图（FCF 柱 + FCF/营收 线；
  净利率/ROE/ROA 三线）→ ROIC 减 WACC（贴参数假设）→ 来源五类逐条给证据，
  收尾反问「对手拿 10 个亿进来，能不能抢走这门生意」。
- **企业估值单独成节**（`valuation`）：三张走势曲线，每张图下面写「这张图怎么读」，
  三个分位并排给结论，并回答「便宜的原因是什么」——市场没发现，还是利润已经塌了。
- 区分事实与推测：财报数字是事实；机构预测写「隐含的假设是…」；自己的判断写「这么看来…」。
- 推演句式：「这么看来…」「这也说明…」「后续关键看 xxx，若 A 将 X，若 B 将 Y」。
- **禁止**套话（未来可期 / 助力腾飞）与编造；**禁止**把主观感慨混进财务分析正文。
- **`data_gaps` 必须写**：把拿不到的指标列成清单（含「这个缺口会导致哪个判断无法成立」），
  不允许让区块自动消失——读者看不到缺口，就等于被隐藏了。

### 第 5 步 · 出报告

把第 2–4 步的结果填进 JSON，**先校验、再合并原始数据、一次写出三件套**：

```bash
S=<skill目录>/scripts
RAW="${PWD}/.raw/<code>-raw.json"         # 第 1 步的采集包（跨命令持久）

python3 $S/validate.py data.json         # ① 结构+算术自检，必须 0 error
python3 $S/save_report.py data.json --raw "$RAW"
# ② 合并 raw_data → 再次校验（含 raw_data 闸门）→ 按 env 写 .json/.html/.md
#    三个文件主名完全相同，只是后缀不同；终端会打印三个绝对路径

python3 $S/lint_encoding.py "<save_report 打印的 .html 路径>" "<... .md 路径>"
# ③ 产物编码自检，必须 0 error
```

`save_report.py` 是正式交付入口：它从 skill 根目录的 `env` 读 `REPORT_OUTPUT_DIR`，
写 `{basename}.json` / `.html` / `.md`；JSON 根节点是计算结果、`raw_data` 是远程原始返回。
`render_report.py` / `render_md.py` 仍可单独用，但**只有排障时才手写 `-o`**——
正式交付不要绕过 env，否则三个文件会散在不同目录。

**已研究过的公司不要重跑第 1 步**：

```bash
# 只更新三件套（复用旧 JSON，不取新数）
python3 $S/save_report.py --reuse --code {code}

# 补了增量数据（如新行情 / 新财报）后更新：旧 raw_data 自动保留，新返回追加
python3 $S/save_report.py new.json --reuse --raw new-raw.json
```

`--reuse` 会按 `meta.code`（6 位数字也认）在 `env` 输出目录里找最新旧报告；
找不到就报错并提示走完整取数。**第一次研究不要加 `--reuse`**。

**`lint_encoding.py` 的判定分两级**：`[error]` 全小写/怪拼的拉丁串 = 必须改；
`[warn]` CamelCase / 首字母大写单词 = 大概率是品牌名或产品代号，人工确认即可，不算失败。
白名单**不用改代码**：公司/行业专名写进 `scripts/allow_words.txt`（一行一词），
或在该行加 `<!-- lint-allow: SmartVitals -->`、文件顶部加
`<!-- lint-allow-file: 飞利浦 -->`。

**`validate.py` 兜住的是渲染器的静默降级**：图表值混进字符串 → 图整块消失；
`state_text` 漏填 → MD 版七步表整列空白；打分卡 `total` 与 `items` 对不上 → 分数造假。
脚本不会替你判断逻辑，但算术、长度、枚举、编号这些必须过。

**如果你改的是 skill 本身**（不是某一家公司的数据），交付前再跑一次文档对账：

```bash
python3 $S/check_docs.py           # 文档里的数字/工具名/字段名/章节号 ↔ 代码常量
python3 $S/check_docs.py --refresh # 工具名或字段有变动时，先重建快照再查
python3 evals/run.py               # 回归用例 + 上面这一项，一起跑
```

它专抓「改了 A 处忘了 B 处」：SKILL 说 16 项而表里 18 行、文档引用了不存在的
`data_xxx`、字段名拼错、`§` 编号指向空章节、骨架声明的 JSON 键渲染器根本没读。

**JSON 字段清单**（v2；字段大多可省略，但 v2 的八节必需块缺了会直接报错。
完整示例见 `scripts/sample.json`，那份示例可直接再渲染；`raw_data` 结构见 `scripts/sample-raw.json`）：

| 键 | 内容 | 对应报告区块 |
|---|---|---|
| `schema_version` | 固定 `"2"`。v1（trends/latest/balance 三块）仍能渲染，但会丢掉整个「财务全景」 | — |
| `meta` | name / code / tagline / price / **price_at** / change_pct / chg_note / market_cap / **cap_note** / industry / report_date。`report_date` 是**行情/报告基准日**（不是财报报告期）。**市值的单位只写一次**：`market_cap` 自带单位（如「118.20 亿」），`cap_note` 只写股本与每股口径（如「总股本 9.31 亿股（流通 9.27 亿股）」）；两处都写「亿元」会渲染成「118.20 亿　亿元」，`validate.py` 会把重复单位判为错误 | 顶部横幅 + 页脚时点 |
| `verdict` | stance / level(good·mid·bad·watch) / headline / summary / tags[] | 结论卡 |
| `price` | `records[{name, range, note}]`（历史区间表，**不是 label/value**）/ `chart_data[{label,value}]` / `chart_title` / `comment` | 一、股价位置 + SVG 走势图 |
| `core_metrics` | [{label, value, note, flag(ok·warn·bad)}]，**v2 至少 10 项** | 二、主要指标初步研判 |
| `core_summary` | 字符串：二节收尾的一句初步判断（**v2 必填**，≥8 字） | 二、指标卡之后 |
| `business` | intro / segments[{name,rev_pct,margin,comment}] / moat（**对象，见下行**）/ policy / upstream / downstream | 三、生意本身 |
| `valuation` | title / lead / metrics[{key(pe·pb·ps), name, unit, current, series[{d,v}], tone?, badge?, note}] / comment / note。**series 是带日期的历史样本（`[{"d":"2021-06-30","v":60.2},…]`，也兼容纯数值数组），渲染器自己算分位、中位、区间并画走势图**；`tone`（ok·mid·high）用来覆盖徽章配色，`badge` 覆盖文案（比如「名义 0% 分位（口径失真）」）。分位 = 低于当前值的样本数 ÷ 有效样本数（校验器与渲染器共用 `scripts/report_stats.py`，不再各算一遍）。**`percentile_trimmed`（剔除极端点后的分位：`v > min(100, 3×中位)` 的点不进样本，无极端点时退回两端各 5% 缩尾）在样本里有极端点时必填**：利润塌陷期的 100 倍以上 PE 会把分位压平，两个口径相差 ≥10pct 时渲染器并排显示，区间外的点画成空心圈；出现极端样本却没给缩尾口径，`validate.py` 会告警。**`series` 末点用报告日/最新交易日的读数**（同日两点相差 >5% 报错；末点日期早于报告日只提醒，但 `note` 要写明月末采样频率） | 七、企业估值：三条历史走势曲线 |
| `business.moat` | **对象**：text / strength(wide·narrow·none) / strength_text / strength_note / years[] / metrics{rows[{key,name,unit,values[]}], judge, consistency} / charts[{title,labels?,unit_l,unit_r,series}] / roic{value,wacc,spread,note} / sources[{type,strength(strong·mid·weak·none),evidence}] / verdict。**纯字符串仍然兼容，但会告警**（缺表、缺图、缺 ROIC/WACC）。rows 的 key 必须是 fcf / fcf_margin / net_margin / roe / roa 五个 | 护城河：五指标表 + 两张趋势图 + ROIC/WACC + 来源表 |
| `financials` | **财务全景（合并块，见下表）** | 四、财务全景与跨年趋势研判 |
| `data_gaps` | [] 字符串列表：拿不到的指标 + 它对哪个判断的影响 | 数据缺口与口径风险 |
| `redflags` | [{**id**(1~25), level, text, evidence, hit}]，**只列命中项**；零命中时为 `[]` | 五、排雷扫描（分母固定 25） |
| `redflags_checked` | 整数，v2 固定写 `25`：声明 25 条已逐条过；零命中必须靠它输出「0 / 25」 | 五、排雷扫描标题与正文 |
| `redflags_note` | 字符串：**零命中时必填**（≥10 字）——说明为什么一条都没中、点名最接近的三条，并把「沾边但不够阈值」的观察写这里（如「OCF 同比 −55.2%，但扣非健康、应收周转在改善，未命中任何一条」）。有命中项时可选，写了会渲染在命中列表之后 | 五、排雷扫描正文 |
| `scorecard` | steps[{no,name,state(pass·warn·fail·na),**state_text**,conclusion}] / items[{dim,value,weight}] / total / total_note。**拿不到数据的项保留 16 行、写 `value: null`（不可评）**，渲染时画灰条、自动从分母剔除并算出归一化得分率。`total` 是**展示字符串，不是数字**：格式 `+得分 / 满分 = 得分率%`，实例 `47 / 66（得分率 71.2%）`（`+25 / 66 = 37.9%` 也合法）；数值真源是 `items[].value × weight`，`total` 只是给人看、给校验器对账的**冗余表达**——写成纯数字 `25` 会被 `validate.py` 判「格式无法解析」，括号里得分率与实算差 >0.2pct 也会报错。**`total_note` 必须点明「本卡只评质地不评成长；成长见第八节」**——16 项里没有成长维度（§5 整章未进卡），不说明会让强周期/强改善型公司被静默判低 | 六、七步研判 + 评分条 |
| `conclusion` | paragraphs[] / watchlist[] / triggers[]，**三者都是字符串数组**；watchlist/triggers 每项写成「指标：阈值 → 含义（频率）」，**不要写成 `{item,threshold,freq}` 这类对象**（渲染器会打印 Python 字面量，`validate.py` 直接报错） | 八、综合研判 + 跟踪清单（编号按实际节数自动生成） |
| `sources` | [{name, detail}] | 数据来源 |
| `raw_data` | 远程原始返回包：`schema`(raw-v1) / `code` / `generated_at` / `call_count` / `calls[{source,tool,params,at,ok,response|raw_text}]`。由 `collect_raw.py` 采集、`save_report.py` 合并；**交付 JSON 必须有**，渲染器不读 | 不单独渲染（数据可复算凭证） |
| `_data_package` | 合并说明：`saved_at` / `basename` / `output_dir` / `raw_data` 键名。由 `save_report.py` 自动写 | 不渲染 |
| `charts_title` / `redflags_title` / `scorecard_title` / `conclusion_title` | 只覆盖标题文字，不覆盖编号；编号由渲染器按实际存在的节连续生成。`charts_title` 推荐放在 `financials.charts_title`（顶层同名键也兼容） | 各区块标题 |

**`financials` 子字段**（把旧版的 trends / latest / balance 三块合成一整块）：

| 键 | 内容 |
|---|---|
| `title` / `lead` | 标题 + 导读（说明数据来源、期数、口径与反推方法） |
| `periods` | 主表的期标签，**至少覆盖最近 2 年的全部季报**（10 期起，接口给到 16 期就用满） |
| `quarterly_title` / `quarterly[]` / `quarterly_note` | 单季主表：每行 {name, values[]}，值与 periods 严格等长，行数建议 16~20 |
| `charts[]` | 每张图：{title, labels[], series[{name,type:bar·line,axis:l·r,color,values[]}], unit_l, unit_r, height, note}。`labels` 可省（默认等于 periods）；**年度长镜头图可以给 7 年这种更短的 labels，只要求该图 `series[].values` 与它自己的 labels 等长**，校验器不再拿它跟 periods 比。**`values` 必须是纯数字**——带 `%` 或 `亿` 的字符串画不出来，图会整块消失 |
| `yoy` | {title, headers[], first_col?, series[{name,values[]}], note} —— 同季同比对照。**`headers` 只放数据列**，首列名用 `first_col`（默认「对照项」），`values` 长度必须等于 `headers` |
| `cumulative` | {title, headers[], first_col?, series[], note} —— 年报 / 中报累计口径的长镜头；`headers` 同样只放数据列，首列默认「指标」 |
| `latest` | {title, period, comment, items[{label,value,yoy,note}], signals[{name,state,result,reason}]} —— 最新一期解读 + 三项改善信号 |
| `balance` | {title, comment, items[{label,value,note}], risks[{name,value,level,threshold}]} —— 资产负债明细 + 四项安全判定 |
| `insights_title` / `insights[]` | 跨年趋势归纳：每张卡 {tag, kind(ok·warn·bad), title, points[]}，**必须覆盖产品与价格、管理层口径（研发/费用）、营运资本、财务策略、现金流质量、股东回报、阅读方法等维度** |

**财务全景的硬要求**：
- 数据至少覆盖 **2 年以上的每个季报期**（≥10 期，建议拉满接口能给的 16+ 期做完整周期）；
- 三层口径缺一不可：**单季**（本期累计 − 上期累计）、**滚动四季**（消季节性）、
  **同季同比**（季节性强的公司环比会骗人）；
- 每张图的 `note` 必须写出「图形读法」——Markdown 版唯一能呈现图表的方式就是这段文字；
- 反推科目（应收、存货等）必须在行名与 `lead` 里注明「反推」。

写完 JSON 后：**先跑 `validate.py`，再跑两个渲染脚本，最后跑 `lint_encoding.py`**，
三步全绿才交付。跑完用浏览器或 `present_files` 打开。

---

## 降级策略

| 情形 | 处理 |
|---|---|
| WeStock Connector 未连接 | 先提示用户在「连接器管理」中连接**腾讯自选股**；征得同意后可用 WebSearch/WebFetch 拿公开财报数据补齐，**但报告里必须标注每个数字的来源与时效**；同时补齐 `data_gaps` |
| 部分接口无数据（如北交所 / 次新股缺机构预期、缺历史估值序列） | 该指标判定置「无数据」，在报告中注明原因，**不要用其他市场的口径或同行数据硬套** |
| **接口缺 `GoodWill` / `LongtermLoan` 等 key** | 先判「该科目为 0/无」还是「接口未返回」：能由 F10 核实的按 0 处理并在 `data_gaps` 注明；不能核实的标「无数据」，不要直接写「接口拿不到商誉」。商誉、合同负债、其他应收在打分卡里各 ×2，共 6 权重；应付账款没有独立计分项。**不要记 0 分**：不可评项从分母剔除后按可评项归一化，并写明「本项无法判定，结论不含该项」 |
| 用户只要快速结论 | 跳过 HTML，直接在对话里给六段式的纯文字版 |
| Python 不可用 | 按 `references/解读范式.md` 手写 HTML，视觉规范照抄 `scripts/render_report.py` 里的 CSS 常量 |
| Node 不可用（`westock_client.js` 跑不了） | 只用能挂上 `data_*` 工具的客户端跑；**不要自己拼 OAuth** |
| 凭据/鉴权相关 | 见 `references/接入WeStock.md` 第七节排查表；**任何情况下都不把 token 写进报告、日志或 git** |

---

## 输出与交付

**保存路径只由 skill 根目录的 `env` 决定**，不要写死在命令行或数据 JSON 里：

```bash
# /home/kevin/.workbuddy/skills/stock-research-report/env（UTF-8）
REPORT_OUTPUT_DIR=~/企业研究报告
REPORT_BASENAME_TEMPLATE={name}-企业信息解读-{date}
```

- `REPORT_OUTPUT_DIR`：三件套保存目录。支持**中文、空格**、`~`、`$HOME`、绝对路径；
  相对路径以 **skill 目录**为基准。改完即生效，不用改脚本；留空则回退到 `~/企业研究报告`。
- `REPORT_BASENAME_TEMPLATE`：三个文件共用的主文件名；占位符 `{name}` / `{code}` / `{date}`。
- **三个文件同名不同后缀**：`{basename}.json`、`{basename}.html`、`{basename}.md`；
  例如 `贵州茅台-企业信息解读-20261031.json` / `.html` / `.md`，三个都要交付。
- `.json` 是**唯一的数据交付文件**：根节点 = skill 计算/研判结果；`raw_data` = 远程原始返回；
  `_data_package` = 打包说明。不再另出「数据源 JSON」。
- **重复研究同一家公司时，输出目录里的旧 JSON 就是缓存**：先跑
  `report_cache.py lookup --code {code}`，命中就加 `save_report.py --reuse` 只更新三件套；
  只有新公司才完整取数。缓存按 `meta.code` / `meta.name` 识别，和文件名里的日期无关。
  只有旧 HTML/MD 时 `has_data: false`，需先完整取数一次补齐 JSON（见「两条路线」）。
- 想先看会存到哪：`python3 scripts/report_paths.py --data data.json`。
- 交付时附一句话核心结论（stance + 最重要的一个理由），不要复述全文。
- **免责声明必须保留**：报告基于公开数据整理，仅供参考，不构成投资建议。

---

## 常见错误（不要犯）

1. 拿到名称直接当代码用 → 必须 `data_search` 先转。
2. 只报百分比不给绝对额 → 毛利 39% 但不知道是 8 亿营收的 39% 还是 80 亿的。
3. 把滚动 PE 当动态 PE → 三种 PE 必须分开标。
4. 忘了扣非 → 归母净利 +518% 而扣非 −51% 的公司（厚普股份式）会被严重误判。
5. 只看最新一期 → 五年趋势才是判断「连贯性」的最低要求。
6. 结论骑墙 → 「有待观察」「需进一步跟踪」不能作为最终 stance。
7. 数据源没给就靠记忆补 → 这份报告的全部价值在于「每个数字都有出处」。
8. 拿不到数据的项记 0 分 → 缺数据 ≠ 中性，会把数据不全的公司判成经营变差。
9. 排雷列表只写命中项却按列表长度做分母 → 分母固定 25；零命中也要写 `redflags_checked: 25`。
10. 渲染完不看图 → 图上值全是字符串时图会整块消失，`validate.py` + 看一眼截图才算完；`price.chart_data[].value` 也必须是纯数字。
11. 估值只写一个分位 → PE/PB/PS 必须三个都给图、并排读；只报 PE 会被一次性收益骗。
12. 护城河写成散文 → 没有五指标表、没有两张趋势图、没有 ROIC 减 WACC，等于没论证。
13. 改了文档不改代码（或反过来）→ 跑 `check_docs.py`。文档里的数字是**硬编码**的：
    「16 项」「25 条」「满分 66」「§9.4」「1.6 秒 / 80 次 / 60 秒」每改一处都要回头对账，别信记忆。
14. 零命中只写「0 / 25」不写理由 → `redflags_note` 必填。清单没命中 ≠ 没有问题
    （301087 的经营现金流 −55.2% 就一条都没中），不写理由读者分不清「查过了」和「没查」。
15. 为了让 `valuation.current` 通过校验，往 series 里硬塞一个非当月点 → 先看日期：
    末点比报告日早是**允许**的（只提醒），只有同日两点不一致才是错。塞点会污染分位口径。
16. 原始返回散成一堆文件、或另起 `-数据源-` 文件名 → 必须先进 `collect_raw.py` 的采集包，
    最后由 `save_report.py` 并进**同名 JSON** 的 `raw_data`。
17. 忽略 `env` 直接 `-o ./报告.html` → 正式交付一律走 `save_report.py`；`-o` 只用于排障。
18. 只交 HTML/MD 不交 JSON，或三个文件主名不一样 → 用 `save_report.py` 一次写出，
    三件套必须**同目录、同主名、只差后缀**。
19. 已研究过的公司又跑完整 16 类接口 → 先 `report_cache.py lookup`；`cached: true` 就加
    `save_report.py --reuse`，只更新三件套，别重拉 40~85 次月末采样。
20. 采样脚本还在跑就用 `collect_raw add/run` 写同一个采集包 → 走锁排队，别并发；
    终端说「已记录」时要看「包内共 N 条」，那是回读后的真实条数。
21. 估值样本里有 300 倍 PE 却只报一个分位 → 必须同时给 `percentile_trimmed`，
    并在 `note` 点名极端点；只给全样本分位会让「偏贵」被算成「偏便宜」（正海 47.9% vs 62.2%）。
22. 已研究过却新建到别的目录、或另起一个主名 → 缓存按 `meta.code` 能识别日期不同的旧文件，
    但交付目录要保持 `env` 的那一个，避免同一公司散成多份。

---

## 变更记录

见 `CHANGELOG.md`。**v2.11.0 起：① 采集包写入统一走 `raw_bundle.locked()/update()`
（锁内重读-追加-回写-回读），采样期间并发 add 不再丢条目；② 轻量标记（`**粗体**` / 反引号）
并入 `esc()` 一次处理，正文/证据/清单不再漏；③ 估值分位双口径（`percentile` + 剔除极端点后的
`percentile_trimmed`，校验器与渲染器共用 `report_stats.py`）；④ `watchlist/triggers`
元素必须是字符串、市值单位不许写两遍，校验器直接报错。**
**v2.9.0 起（v2.10.0 继续沿用）：先查 `env` 输出目录的旧报告——已研究过的公司用
`save_report.py --reuse` 只更新三件套（复用旧 `raw_data`），没研究过的公司才完整取数；
`report_cache.py` 按 `meta.code` / `meta.name` 识别缓存。**
**v2.8.0 起：输出目录改由 skill 根目录 `env` 的 `REPORT_OUTPUT_DIR`
配置（支持中文/空格/相对路径）；新增 `collect_raw.py` 采集远程原始返回，`save_report.py`
把它并入交付 JSON 的 `raw_data`，并与 HTML/Markdown 一起按同名主文件名写出。**
**v2.7.2 起：取数三态（`ok:false` / `ok:true` 空返回 / 非 JSON）、
`redflags_note` 正式登记、`valuation.series` 末点改为按日期分级校验、`lint_encoding` 白名单外置
并分 `error` / `warn` 两级、主营构成跨源模板（`RPT_F10_FN_MAINOP`）。**
**v2.5.0 起：明确定义「报告骨架（八节）」并把六段式映射过去**——
三节含护城河四件套（五指标表 + 两图 + ROIC/WACC + 来源表），七节是 PE/PB/PS 三条历史走势曲线。
v2.4.1 起：估值图从直方图改为时间序列曲线（当前值标在末端）+ 分位百分比（`valuation` 块）。v2.2.0 起：接口文档按 2026-10-30 实测重写（`fields="all"` 的资产负债表字段随公司科目变化：301101 49 / 600315 51 / 600519 53，
含 `GoodWill`、`LongtermLoan`、`NonCurrentLiabilityIn1Year`、`_Q` 单季字段、`data_quote` 的 `date` 参数、限频阈值）；
`num=16`、`price_at`、`data_gaps`、缺项归一化、结论矩阵、`validate.py`；
修掉渲染器的轴单位叠字、排雷分母、图表静默跳过、MD 七步表空白、加权总分重复五处缺陷。
