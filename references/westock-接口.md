# 腾讯自选股（WeStock）数据接口

> 工具名、参数、字段名全部来自 **2026-10-28 实测**（`sz301101` 明月镜片 + `sz002382` 蓝帆医疗）。
> 返回统一为 `{ "ok": true|false, "data": ..., "message": "..." }`。
> **`ok: false` 时原样转述 message，禁止编造数据。**

---

## 一、前置：代码规范

| 市场 | 格式 | 示例 |
|---|---|---|
| 沪市 | `sh` + 6 位 | `sh600519` |
| 深市 | `sz` + 6 位 | `sz000001` |
| 北交所 | `bj` + 6 位 | `bj830799` |

**只做 A 股。** 港股（`hk`）、美股（`us`）不在范围内——两边的科目体系不同
（港股没有「扣非」、美股没有「合同负债」的同类科目），拿 A 股口径去套会得出错误结论。

**用户只给名称或 6 位数字时，先调 `data_search` 拿到带前缀的代码，再取其他数据。**

---

## 二、必取数据（按顺序，一次解读的最小集合）

| 步骤 | 工具 | 关键参数 | 用途 |
|:--:|---|:--:|---|
| 1 | `data_search` | `query` | 名称 → 代码 |
| 2 | `data_disclosure` | `code` | **报告期确认**：最新定期报告的 `reportEndDate` + `disclosureDate` |
| 3 | `data_quote` | `code` | 现价、涨跌幅、市值、`pe_ratio`(TTM) / `pe_lyr`(静态) / `pe_fwd`(动态)、`pb_ratio`、`dividend_ratio_ttm` |
| 4 | `data_kline` | `code`, `period=season`, `limit=40`, `fq=qfq` | **季 K 线**：判断股价历史位置（一节） |
| 5 | `data_kline` | `code`, `period=year`, `limit=10`, `fq=qfq` | 年 K：补长周期高低点 |
| 6 | `data_profile` | `code` | 主营、行业、股本、上市日期（**不含估值**，别指望它给 PE/PB） |
| 7 | `data_finance` | `code`, `fields="all"`, `num=16`（护城河另补 `num=28`） | **三大报表全字段**，见第三节 |
| 8 | `data_consensus` | `code` | `targetPrice` + 未来三年 `netProfit`/`eps`/`pe`（动态 PE 的来源） |
| 9 | `data_rating` | `code` | 机构评级；返回 `forecastInstitutions` / `ratingBuyCnt` / `ratingCnt`，**可能只有条数、没有评级与目标价**（见 §6.4） |
| 10 | `data_dividend` | `code` | 分红送转序列 |
| 11 | `data_shareholder` | `code` | 股东结构、大股东性质 |
| 12 | `data_risk` | `code` | 质押、解禁、诉讼、ST（仅 A 股） |
| 13 | `data_notice` | `code`, `limit=20` | 公告（重组/减持/业绩预告） |
| 14 | `data_news` | `code`, `limit=20` | 个股新闻 |
| 15 | `data_sector` | `mode=search` + `query` → `mode=constituent` + `code` | 同业对比（**两步走，见 6.5**） |
| 16 | `data_score` | `code` | 诊股评分，仅作交叉参考，**不替代自己的判断** |

可选：`data_fund_flow`、`data_technical`、`data_industry_chain`、`data_report`、
`data_dehydrated`、`data_north_holding`、`data_finsearch`（文字检索，补附注类信息）。

**没有 `data_valuation` 这个工具。** PE/PB 历史分位只能自己搭，见第七节。

**这张表之外还有三件事必须做**：① 第七节的月末采样（同上第 3 行 `data_quote` 加 `date`）；
② 第三节护城河要的资本支出，见第八节（东财 F10，WeStock 没有这个科目）；
③ 分部表缺主营构成时的跨源补数，见 8b（同样是东财 F10）。

### 2.1 原始返回一律进同一个采集包（v2.8.0 起）

上表每一次调用、每个月的 `data_quote(date=...)` 采样、每条东财 F10 / 网页补数，
都要把**完整返回原文**写进同一个 `raw-v1` 采集包；最后由 `save_report.py` 并入交付
JSON 的 `raw_data`。不要再拆成 `{code}-raw-{YYYYMMDD}.json` 多个文件，也不要另起
「数据源 JSON」的文件名。

```bash
RAW="$PWD/.raw/sz301101-raw.json"
mkdir -p "$(dirname "$RAW")"
python3 scripts/collect_raw.py init "$RAW" --code sz301101

# 走脚本：run 自动调 westock_client.js 并记录完整返回（推荐）
python3 scripts/collect_raw.py run "$RAW" --tool data_quote --params '{"code":"sz301101"}'
python3 scripts/collect_raw.py run "$RAW" --tool data_finance \
  --params '{"code":"sz301101","fields":"all","num":16}'

# 走 data_* connector 工具：把工具返回原样落文件，再 add
python3 scripts/collect_raw.py add "$RAW" --tool data_sector \
  --params '{"code":"sz301101","mode":"constituent"}' --response-file /tmp/sector.json

# 东财 F10（资本支出 / 主营构成）
python3 scripts/collect_raw.py add "$RAW" --source eastmoney \
  --tool RPT_F10_FN_MAINOP --url "$F10_URL" --response-file /tmp/mainop.json

python3 scripts/collect_raw.py status "$RAW"
```

- `ok:false` 的返回同样原样记（`response.ok=false` + `message`），**不要因为它失败就丢掉**。
- `run` / `add` 找不到采集包时**默认报错**，不会静默新建；确实要新建空包加 `--create`
  （更推荐先 `init`）。`status` 对不存在的包会直接提示「请先 init」。
- 限频 / 参数错导致返回纯文本时，用 `--text`（或 `--response-file` 存原文）记成
  `raw_text`；这正是排查「到底是被限频还是那天没数据」的证据。
- 采集包只是临时中转，**交付时只交一个 JSON**（根节点=计算结果，`raw_data`=原始返回）。
- 最小结构示例见 `scripts/sample-raw.json`。
- **已经研究过的公司不要重跑本节全表**：先 `scripts/report_cache.py lookup --code …`；
  命中就只补需要刷新的那一两项，再 `save_report.py --reuse`（见 SKILL「两条路线」）。


---

## 三、`data_finance`：一定要传 `fields="all"`

实测对比（`sz301101`，同一期）：

| 参数 | 资产负债表字段数 | 能不能算 §7 资产质量 |
|---|:--:|---|
| `fields="core"`（默认） | **24**（`sz301101` 实测） | 不能：没有应付、存货、应收、合同负债、股本的绝对额 |
| `fields="all"` | **49 / 51 / 53**（`sz301101` / `sh600315` / `sh600519`） | 能：按公司科目有无返回，不是固定 49 |

`fields="all"` 的资产负债表字段（以 `sz301101` 的 49 个为例，2026-10-30 实测；其他公司会多出 `GoodWill` / `LongtermLoan` 等）：

```
CashEquivalents  TradingAssets  BillAccReceivable  AdvancePayment  Inventories
OtherCurrentAssets  OtherNonCurrentAssets  TotalFixedAsset  TConstruInProcess
IntangibleAssets  LongtermEquityInvest  TotalAssets  TotalCurrentAssets
TotalNonCurrentAssets  NotAccountsPayable  ContractLiability  SalariesPayable
OtherPayableED  OtherCurrentLiability  NonCurrentLiabilityIn1Year
LeaseLiabilities  TotalCurrentLiability  TotalNonCurrentLiability  TotalLiability
PaidInCapital  CapitalReserveFund  SurplusReserveFund  RetainedProfit  SEWithoutMI
TotalShareholderEquity  NAPS  InterestBearDebt  WorkingCapital  EnterpriseType
ARTRate  InventoryTRate  TotalAssetTRate  CurrentRatio  QuickRatio
DebtAssetsRatio  DebtEquityRatio  EBIT  NPDeductNonRecurringPL  SecuCode
EndDate  InfoPublDate  date  _date
```

对照报告指标：

| 报告指标 | 字段 |
|---|---|
| 货币资金 | `CashEquivalents` |
| 交易性金融资产（理财） | `TradingAssets` ← **经营性 PB 必需** |
| 应收票据及应收账款 | `BillAccReceivable` |
| 应收款项融资 | `ReceivablesFin` |
| 存货 | `Inventories` |
| 应付账款 | `NotAccountsPayable`（名字反直觉，就是应付账款） |
| 其他应收款 | `OtherReceivableED` |
| 其他应付款 | `OtherPayableED` |
| 合同负债 | `ContractLiability` |
| 在建工程 | `TConstruInProcess` |
| 资本公积 | `CapitalReserveFund` |
| 未分配利润 | `RetainedProfit` |
| 归母净资产 | `SEWithoutMI` |
| 有息负债（合计） | `InterestBearDebt` |
| 一年内到期非流动负债 | `NonCurrentLiabilityIn1Year` |

**`fields="all"` 也不是固定字段表（按公司科目有无返回）**：

- **商誉**：字段是 **`GoodWill`**（大写 W），`sh600315` 2026-09-30 为 14.55 亿；`sz301101` / `sh600519` 未返回该 key（按 0/无处理）。
  不要再写「`Goodwill` 不存在」——大小写写错会误判成没有商誉。
- **长期借款**：字段是 **`LongtermLoan`**，`sh600315` 为 3.20 亿；未返回时按 0/无处理。
- **一年内到期非流动负债**：`NonCurrentLiabilityIn1Year` 有值（`sh600315` 1.26 亿、`sz301101` 212 万）。
- **短期借款**：`ShortTermLoan` **常见但非必然**——`sz000629` 的 `fields="all"` 返回了
  1.20 亿，`sh600519`/`sh600315` 未返回；此时用 `InterestBearDebt`（合计）减
  `LongtermLoan − NonCurrentLiabilityIn1Year − LeaseLiabilities` 估算，
  或直接用合计做保守替代，并在报告里注明。
- **产成品 / 发出商品**等存货明细：没有，需 F10/附注。

**关键**：缺 key 通常是该科目为 0/无，不等于接口没有这个字段。先用三只股票并集快照或 F10 核对，
再决定是「0」还是「不可评」；不要把「这只股票没返回」写成「接口拿不到」。

### 利润表 / 现金流量表

利润表 58 个字段，**含 `_Q` 单季口径**（`OperatingRevenue_Q`、`OperatingCost_Q`、
`NPParentCompanyOwners_Q`、`NPDeductNonRecurringPL_Q`、`RAndD_Q`、`TotalAdminExpense_Q` …）。
现金流量表 22 个字段，同样是「累计 + `_Q` + `TTM`」三套（`NetOperateCashFlow` /
`_Q` / `NetOperateCashFlowTTM`）。

> **但单季仍以倒挤为准**：`_Q` 实测与倒挤一致（301101 2026Q3 营收 `_Q`=2.7342 亿，
> 倒挤=2.73 亿），两者可以互验；**不一致时用倒挤，并在报告里注明接口 `_Q` 与累计口径有出入**。
> 不要因为接口给了 `_Q` 就跳过「本期累计 − 上期累计」这一步——它同时是数据一致性的检查。

---

## 四、TTM 与单季口径的处理规则

- **同比**：本期累计 ÷ 上年同期累计 − 1。**年报对年报，半年报对半年报，不要混。**
- **单季倒挤**：`第 N 季度 = 本期累计 − 上期累计`（并与 `_Q` 字段互验）。
- **TTM**：`本期累计 + 上年全年 − 上年同期累计`；接口也有现成的 `*TTM` 字段可对照。
- **趋势图**：优先用年报序列（噪音小），至少取 **5 年**（评判 ROE 连贯性的最低要求）。
- **最新一期**优先用 **中报或三季报**，并注明报告期。

---

## 五、数据缺口的处理

### 5.0 先分清「三种返回形态」，处理规则完全不同

`{ ok, data, message }` 只是**成功**时的外壳；实际至少会遇到三种形态，混为一谈就会
把「参数写错」当成「没数据」、把「空数组」当成「接口坏了」：

| 形态 | 长什么样 | 判据 | 处理 |
|---|---|---|---|
| ① 业务失败 | `{"ok":false,"message":"…"}` | `ok === false` | **原样转述 message**，禁止编造；该指标「无数据」 |
| ② 成功但无数据 | `{"ok":true,"data":{"sz301087":{"top10Shareholders":[]}}}` | `ok === true` 且列表/对象为空 | **不重试**（重试只会烧限频额度）：该指标「无数据」，写 `data_gaps`，打分卡 `value: null` |
| ③a 不是 JSON（真失败） | `请提供搜索关键词`、`查询财报异常：… 服务限频`、鉴权失败 | `JSON.parse` 失败，且原文是参数/限频/鉴权错误 | **调用失败**：必须非零退出或退避重试，保留原文；不能当「那天没数据」 |
| ③b 不是 JSON（业务无数据） | `未找到一致预期数据`、`暂无…`、`无数据` | `JSON.parse` 失败，但语义是「没有这个数据」 | **合法空返回**：不重试，写 `data_gaps`，打分卡 `value: null`；与 ③a 分开 |

形态 ③ 的实测例子（2026-10-30）：`data_sector` 的 `mode=search` **漏传 `query`** 时，
返回的就是一句 `请提供搜索关键词`；`mode=constituent` 传错参数时返回 `成分股查询需要 code 或 codes`。
两者都是**参数问题**，正确写法见 6.5。`data_consensus` 对 `sz000629` 返回
`未找到一致预期数据`，属于 ③b，不要重试。

> 脚本铁律（对应形态 ③）：解析后必须断言 `ok === true`，否则 `exit` 非 0。
> `westock_client.js` 的 `call` 在工具返回纯文本时以 **exit 3** 退出，并把原文同时写 stderr
> 和 stdout——不要用 `2>/dev/null` 把唯一的现场信息丢掉。

### 5.1 拿不到数据时的四步

1. **先确认参数用对了**：`data_finance` 必须 `fields="all"`；**默认的 `core` 会让你误以为
   应付账款、存货、合同负债「接口拿不到」**——实测都能拿到。
2. 再尝试同源替代（`data_consensus` 拿动态 PE、`data_finsearch` 拿附注类信息）。
3. 仍然没有 → 报告写「暂无披露」，该指标判定置「无数据」，写进 JSON 的 `data_gaps`；
   打分卡该项 `value: null`（**从分母剔除，不记 0 分**）。
4. **绝对不能用训练记忆或常识补齐具体数字。**

**已确认的「合法空返回」（形态 ②，不要重试）**：

| 工具 | 现象 | 实测 | 处理 |
|---|---|---|---|
| `data_shareholder` | 三个列表全空 | `sz301087`（可孚医疗）返回 `shareholderNum: []` / `top10Shareholders: []` / `top10FloatShareholders: []`，`ok: true` | `business.ownership` 留空，`data_gaps` 记一条「股东结构未返回（接口合法空返回）」，不重试 |
| `data_dividend` | `{"ok":true,"data":{}}` | `sz000629` 近 5 年返回空对象 | 再看 `data_quote.dividend_ratio_ttm`：为 0 → 按「零分红」处理；非 0 或取不到 → 按「无分红数据」写 `data_gaps`，不要武断判零分红 |

---

## 六、实测补充（2026-10-30）

### 6.1 一次典型返回的规模

`data_finance(code, fields="all", num=16)` 返回 16 期 × 三大报表（4 个年报）；
护城河要 ≥5 年时再补一次 `num=28`（7 个年报）：
利润表 58 字段、现金流量表 22 字段；资产负债表 **49 / 51 / 53 字段（301101 / 600315 / 600519）**。
够算全部 14 章指标，不需要再拼其他接口。

### 6.2 `data_quote` 的 `date` 参数能拿历史估值

`data_quote(code, date="2024-12-31")` 返回该日的 `pe_ratio` / `pb_ratio` / `pe_lyr` / `pe_fwd`
/ `total_market_cap` 等，与当日行情一致。**这是搭 PE/PB 历史分位的唯一路径**，见第七节。

**单位陷阱**：不带 `date` 的当前报价里 `total_market_cap` 单位是**亿元**（如 67.51）；
带 `date` 的历史返回单位是**元**（如 8,641,000,000）。用历史市值算 PS 必须先 `/1e8`。
报告 `meta.market_cap` 也沿用「带单位」这一写法（如「118.20 亿」），`cap_note` 只写股本口径。

**板块陷阱：`market_name` 不能用**。实测 `sz300224.market_name` 返回「深圳主板」，
但 300 段是创业板——任何用这个字段生成的文案都会写错板块。板块一律按代码前缀判：

| 前缀 | 板块 |
|---|---|
| `sh688` | 科创板 |
| `sh60` | 沪市主板 |
| `sz300` / `sz301` | 创业板 |
| `sz00` | 深市主板 |
| `bj8` / `bj4` | 北交所 |

### 6.2b `data_consensus` 的单位

`netProfit` / `revenue` 单位是**万元**（如 2026E 22,649.81 / 95,558.38），`eps` 是**元**，
`targetPrice` 是**元**。换算成亿元要 `/1e4`，否则动态 PE 会差 1 万倍。
`data_profile.regCapital` 也是**万元**，不是股数；股数取 `data_quote.total_shares`。

### 6.3 三个容易误判的点

1. **应收增速差的机械口径会误报**。营收塌方型企业，应收绝对额没涨、营收大跌三成，
   算出来的「应收增速 − 营收增速」反而大幅为正（> +15pct）。
   必须回看应收**绝对额**：没涨就不是放宽账期，是需求萎缩，不构成垫资风险。
2. **静态 PE 为负不代表便宜**（`pe_lyr` 负数），只能看 PB 和 TTM。
3. **同一时点不同接口的 PE 会差 3%~5%**（`data_quote.pe_ratio` vs 行情站口径）。
   报告里只用一套口径，并在脚注写明用的是哪个字段。

### 6.4 小盘冷门票的取数预期

- `data_consensus` 可能返回 `institutionCnt: 0`（有预测但没统计到机构数）——不是报错。
- `data_rating` 可能只有 1 家机构。报告里如实写「机构覆盖极低，缺少外部验证」。
- **`ratingCnt` 是「评级记录条数」，不是覆盖机构数**；它和 `forecastInstitutions`、
  `data_consensus.institutionCnt` 会互相矛盾。实测 `sz300224`（正海磁材，2026-10-30）：
  `{"forecastInstitutions": 1, "ratingBuyCnt": 1, "ratingCnt": 1}`，**没有评级、目标价和机构名**，
  而同一天 `data_consensus` 给了 3 个年度预测、`institutionCnt: 0`。三处口径打架时，
  按「最乐观的覆盖数」记录，并在 `data_gaps` 写明分歧。
- **硬规则：覆盖机构 < 3 家时，PEG 只能作参考，不得单独作为估值档位（§13 第 3 轴）的主依据**，
  改用经营口径 PB 分位定档，并在 `conclusion` 写「预测来自 N 家机构，PEG 仅作参考」。
  `SKILL.md` 的「rating → 反推预测净利」在这种情况下反推不出来，不要硬凑。
- 动态 PE 也可用 `pe_fwd` 反推隐含预期净利 = 总市值 ÷ `pe_fwd`，并注明「隐含的假设是…」。

### 6.5 `data_sector`：必须两步走，参数写错只会拿到一句中文

`mode=search` **必须带 `query`**，`mode=constituent` **必须带 `code`**（值是第一步拿到的
`sectorCode`）。漏参数时返回的是**纯文本**（见 5.0 形态 ③），不是 `ok:false`——
脚本 `JSON.parse` 会直接抛 `Unexpected token '请'`。

**第一步 · 行业名 → `sectorCode`**：

```bash
node scripts/westock_client.js call data_sector \
     '{"code":"sz301087","mode":"search","query":"医疗器械"}'
```

实测返回（2026-10-30，可孚医疗）：

```json
{"ok": true, "data": [
  {"code": "pt02003668", "name": "医疗器械概念", "type": "聚源产业概念清单",
   "sectorCode": "indus_pt02003668", "listCode": "concept_list_industry"},
  {"code": "pt01801153", "name": "医疗器械", "type": "申万二级行业清单",
   "sectorCode": "sw2_pt01801153", "listCode": "industry_list_sw2"}
]}
```

**第二步 · `sectorCode` → 成分股**（注意参数名是 `code`，不是 `sectorCode`）：

```bash
node scripts/westock_client.js call data_sector \
     '{"mode":"constituent","code":"sw2_pt01801153"}'
```

实测返回 `data.comp_sw2_pt01801153`，含 `sectorName`（申万二级行业成分股-医疗器械）、
`sectorType`、`date` 和 `stocks[{code,name}]`；直接拿 `stocks[].code` 批量调
`data_quote` / `data_finance` 做同业对比。

**两个清单怎么选**：同业对比表优先**申万二级**（`listCode=industry_list_sw2`），口径最接近
「同类公司」；概念清单（`concept_list_industry`）会把上下游一起圈进来，只适合写正文背景，
不要拿它算同业中位数。

**取不到申万二级时的降级规则**：有些行业（如钢铁）`mode=search` 只返回申万一级，
没有 `industry_list_sw2`。此时用「申万一级成分股 + 主营构成重合度」人工挑 3~5 家，
在报告里明确写「自选同业，不是板块中位数」，不要假装是申万二级口径。

---

## 七、历史估值分位：怎么搭、限频怎么躲

**没有现成的历史估值接口**，只能循环 `data_quote(date=…)` 采样。实测数据：

- 服务端有**限频**：连续快速调用约 80 次后开始返回
  `查询财报异常：error_type=2 suggest=2 msg=服务限频`（连 `data_finance` 也会被拒）。
- 触发后需要**退避 60 秒以上**，否则后续调用全失败——失败是静默的（返回文本不是 JSON），
  写脚本时**必须断言返回是 JSON**，否则会把失败当成「那天没数据」。
- 实测每次调用约 0.3~1 秒；建议 **间隔 ≥1.6 秒**。

**推荐的采样方案（按公司上市年数选）**：

| 上市年数 | 采样频率 | 调用次数 | 说明 |
|---|:--:|:--:|---|
| ≥ 10 年 | 月末 | ~120 | 分位精度够用 |
| 5 ~ 10 年 | 月末 | ~60~120 | 同上 |
| 2 ~ 5 年 | **月末** | ~24~60 | 建议同时给出「样本区间 + 点数」 |
| < 2 年 | 月末 | < 24 | 样本太少，**只写区间不给分位** |

**不要**逐交易日采样（1200+ 次调用必然被限频，且对分位精度没有实质提升）。

**取数预算**：基础 16 + 东财 F10 2 + 护城河补数 1 + 同业 2~4 + 采样 N。
服务端约 80 次触发限频，计划值控制在 **16 + 2 + 1 + 4 + N ≤ 75 → N ≤ 52**；
要采 60 个月就砍同业或分批跑。`data_quote` 支持 `codes` 批量，同业行情可一次拿；
`data_finance` 是否支持 `codes` 未确认，别默认批量。

**不要手写采样循环**，直接跑 `scripts/sample_valuation.py`：

```bash
python3 scripts/sample_valuation.py --code sz000629 --raw "$RAW" --years 5
python3 scripts/sample_valuation.py --code sz000629 --raw "$RAW" \
  --start 2021-11-01 --end 2026-10-31 --dry-run   # 只看待补月份
```

它从 raw 包读已有月份，只补缺失；空返回回退前一交易日，超时/限频分开退避，
成功一条立即保存。采集包不存在时直接报错，不会静默新建。

**分位算法**：`分位 = 低于当前值的样本数 ÷ 有效样本数`；只统计 `pe_ratio > 0` 的样本
（亏损期 PE 为负或空，混进去会把分位算低）。报告里必须写出样本区间与点数，
例如「PE 分位 13.8%，样本 2022-01 起 58 个月末点」。

**实测校验（301101，2026-10-30）**：月末采样 58 个点算得 PE 分位 13.8%、PB 分位 24.1%；
用东财 1176 个交易日的日频序列算是 19.3% / 29.3%。**月末采样会平滑掉极端点，差 2~5 个百分点**，
报告里要注明「月末采样」，不把它当日频精确值；不必为了精度去冒限频的险。

**曲线上「当前值」放哪里（`valuation.series` 末点口径）**：`series` 是月末采样序列，
**末点用报告日/最新交易日的读数**（同一只股票、同一个 `pe_ratio` 字段）。两种合法写法：

- **替换**（推荐）：如果采样已覆盖报告日所在月，把该月最后一点换成报告日的值，
  仍是「一个月度点」，不改变采样频率；
- **追加**：采样只到上个月末时，允许再追加一个报告日的点；此时序列里会多出一个
  **非月末点**，`valuation.note` 必须写明「月末采样 + 报告日补一点」。

`validate.py` 对此的规则是：`current` 与 `series` 末点相差 > 5% 时——
**末点日期等于/晚于报告日 → 报错**（同一时点两个数，必有口径错）；
**末点日期早于报告日 → 只提醒**（月末采样本来就允许末端有缺口，但 `note` 要交代）。

**上市不足 5 年的公司**，分位低可能只是「从上市初期的泡沫里跌下来」，不能当便宜的证明。

---

## 八、FCF 的「资本支出」必须外补（WeStock 的唯一致命缺口）

护城河五指标里 **FCF = 经营现金流 − 资本支出**，而 WeStock 的现金流量表只有 22 个字段，
**没有「购建固定资产、无形资产和其他长期资产支付的现金」**。三个替代品全部不能用：

| 候选 | 实测（上海家化 600315） | 结论 |
|---|---|---|
| `FCFE` / `FCFF` 字段 | 2024 年 OCF +2.73 亿、资本支出 0.96 亿 → 真 FCF 1.77 亿，而接口 `FCFE` = **−14.19 亿**、`FCFF` = −12.04 亿 | 口径不明（含债务/权益变动），**差 16 亿，不能用** |
| `NetInvestCashFlow`（投资活动净额） | 2025 年 8.01 − 5.38 = 2.63 亿，真 FCF 7.25 亿 | 把买理财当成投资，**严重低估** |
| 用资产负债表倒推 | Δ(固定资产+在建+无形) + 折旧摊销 | WeStock **没有折旧摊销字段**，倒不出来 |

**唯一可行做法**：WeStock 取其余全部数据，资本支出单独从东财 F10 补一个字段：

```
https://datacenter.eastmoney.com/securities/api/data/v1/get
  ?reportName=RPT_F10_FINANCE_GCASHFLOW
  &columns=SECUCODE,REPORT_DATE,CONSTRUCT_LONG_ASSET
  &filter=(SECUCODE%3D%22600315.SH%22)&pageSize=60
  &sortColumns=REPORT_DATE&sortTypes=-1&source=HSF10&client=PC
```

`CONSTRUCT_LONG_ASSET` = 购建固定资产、无形资产和其他长期资产支付的现金（元）。
年报到年报、季报对季报，`REPORT_DATE` 取 `12-31` 即得年度资本支出。

**报告里必须注明**：FCF 的资本支出来自东财 F10，其余数据来自腾讯自选股——
两个源的口径差异（例如资本开支是否含税、是否含在建工程）要一句话交代。

> 这一条是护城河模块唯一的跨源依赖。除它之外，五指标里的净利率、ROE、ROA，
> 以及 ROIC 需要的 EBIT / 有息负债 / 货币资金 / 交易性金融资产，**WeStock 的
> `fields="all"` 全部覆盖**，不需要第二个源。

### 8b 主营构成：分部表的跨源补数

WeStock 的 `data_finance` 只到利润表科目（营业总收入这一层），**没有「按产品/按地区」的分部
收入与毛利率**。第三节要算「各业务毛利额占比」，缺这个就只有一句定性。东财 F10 同一个
接口族里有一张主营构成表，实测可用（2026-10-30，301087）：

```
https://datacenter.eastmoney.com/securities/api/data/v1/get
  ?reportName=RPT_F10_FN_MAINOP
  &columns=SECUCODE,REPORT_DATE,REPORT_NAME,MAINOP_TYPE,ITEM_NAME,
           MAIN_BUSINESS_INCOME,MBI_RATIO,MAIN_BUSINESS_COST,MAIN_BUSINESS_RPOFIT,
           MBR_RATIO,GROSS_RPOFIT_RATIO
  &filter=(SECUCODE%3D%22301087.SZ%22)&pageSize=60
  &sortColumns=REPORT_DATE&sortTypes=-1&source=HSF10&client=PC
```

- `MAINOP_TYPE`：**1 = 按产品**、**2 = 按行业**、**3 = 按地区**。同一个 `REPORT_DATE` 下
  三种都返回，别混着加总（会重复计数）。
- 金额单位是**元**（`MAIN_BUSINESS_INCOME: 1861906774.13` = 18.62 亿）；
  `MBI_RATIO` / `MBR_RATIO` / `GROSS_RPOFIT_RATIO` 是**小数**（0.8987 = 89.87%），不是百分数。
- **字段名有拼写错误，必须照抄**：`MAIN_BUSINESS_RPOFIT`（不是 `PROFIT`）、
  `GROSS_RPOFIT_RATIO`（不是 `GROSS_PROFIT_RATIO`）。传 `MAIN_BUSINESS_PROFIT` 会被拒：
  `返回字段不存在`（`code: 9501`）。
- `MAINOP_TYPE` 为 2 的那组常出现「其他(补充)」，做产品拆分时用 type 1，地区拆分用 type 3。
- 报告里要注明「分部数据来自东财 F10 主营构成，与 WeStock 报表口径可能不一致
  （是否含税、是否含其他业务收入）」，并把 `REPORT_NAME`（如「2026中报」）一起写上。

> 只有这两个字段需要跨源：资本支出（8）与主营构成（8b）。其余一律优先 WeStock，
> 避免同一张表里混三个口径。

---

## 九、一句话速查

```
data_search     → 代码
data_disclosure → 报告期 + 披露日
data_quote      → 行情 + 三种 PE + PB（date= 可查历史，用于自建分位）
data_kline      → 季K/年K（period=season/year, fq=qfq）
data_profile    → 主营/行业/股本/上市日（没有估值）
data_finance    → fields="all", num=16（基础 16 期；护城河另补 num=28）
data_consensus  → targetPrice + 三年预测（动态 PE）
data_rating     → 评级    data_dividend → 分红
data_shareholder→ 股东    data_risk → 质押/解禁/诉讼
data_notice     → 公告    data_news → 新闻
data_sector     → 同业（search 带 query → constituent 带 code）
data_score      → 诊股（仅参考）
data_finsearch  → 文字检索，补商誉/附注类缺口
```
