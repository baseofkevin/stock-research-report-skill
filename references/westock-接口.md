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
| 4 | `data_kline` | `code`, `period=season`, `limit=40`, `fq=qfq` | **季 K 线**：判断股价历史位置（第 1 段） |
| 5 | `data_kline` | `code`, `period=year`, `limit=10`, `fq=qfq` | 年 K：补长周期高低点 |
| 6 | `data_profile` | `code` | 主营、行业、股本、上市日期（**不含估值**，别指望它给 PE/PB） |
| 7 | `data_finance` | `code`, `fields="all"`, `num=16` | **三大报表全字段**，见第三节 |
| 8 | `data_consensus` | `code` | `targetPrice` + 未来三年 `netProfit`/`eps`/`pe`（动态 PE 的来源） |
| 9 | `data_rating` | `code` | 机构评级 |
| 10 | `data_dividend` | `code` | 分红送转序列 |
| 11 | `data_shareholder` | `code` | 股东结构、大股东性质 |
| 12 | `data_risk` | `code` | 质押、解禁、诉讼、ST（仅 A 股） |
| 13 | `data_notice` | `code`, `limit=20` | 公告（重组/减持/业绩预告） |
| 14 | `data_news` | `code`, `limit=20` | 个股新闻 |
| 15 | `data_sector` | `mode=search` → `constituent` | 同业对比 |
| 16 | `data_score` | `code` | 诊股评分，仅作交叉参考，**不替代自己的判断** |

可选：`data_fund_flow`、`data_technical`、`data_industry_chain`、`data_report`、
`data_dehydrated`、`data_north_holding`、`data_finsearch`（文字检索，补附注类信息）。

**没有 `data_valuation` 这个工具。** PE/PB 历史分位只能自己搭，见第七节。

**这张表之外还有两件事必须做**：① 第七节的月末采样（同上第 3 行 `data_quote` 加 `date`）；
② 第三节护城河要的资本支出，见第八节（东财 F10，WeStock 没有这个科目）。

---

## 三、`data_finance`：一定要传 `fields="all"`

实测对比（`sz301101`，同一期）：

| 参数 | 资产负债表字段数 | 能不能算 §7 资产质量 |
|---|:--:|---|
| `fields="core"`（默认） | **25** | 不能：没有应付、存货、应收、其他应收、合同负债的绝对额 |
| `fields="all"` | **49** | 能：全部拿到 |

`fields="all"` 的资产负债表字段（49 个，2026-10-28 实测）：

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

**`fields="all"` 也拿不到的（别浪费时间重试）**：

- **商誉**（`Goodwill` 不存在）——排雷第 5 条只能走 `data_finsearch "公司名 商誉"` 或年报附注，
  拿不到就把该项标「不可评」，不要猜。
- **短期借款、长期借款**（`ShortTermLoan` / `LongtermLoan` 不存在）——只能看
  `InterestBearDebt`（合计）和 `LeaseLiabilities`（租赁负债）。现金短债比的分母要用
  `InterestBearDebt` 并在报告里注明口径。
- **产成品 / 发出商品**等存货明细。

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

1. **先确认参数用对了**：`data_finance` 必须 `fields="all"`；**默认的 `core` 会让你误以为
   应付账款、存货、合同负债「接口拿不到」**——实测都能拿到。
2. 再尝试同源替代（`data_consensus` 拿动态 PE、`data_finsearch` 拿附注类信息）。
3. 仍然没有 → 报告写「暂无披露」，该指标判定置「无数据」，写进 JSON 的 `data_gaps`；
   打分卡该项 `value: null`（**从分母剔除，不记 0 分**）。
4. **绝对不能用训练记忆或常识补齐具体数字。**

---

## 六、实测补充（2026-10-28）

### 6.1 一次典型返回的规模

`data_finance(code, fields="all", num=16)` 返回 16 期 × 三大报表：
利润表 58 字段、资产负债表 49 字段、现金流量表 22 字段。够算全部 14 章指标，
不需要再拼其他接口。

### 6.2 `data_quote` 的 `date` 参数能拿历史估值

`data_quote(code, date="2024-12-31")` 返回该日的 `pe_ratio` / `pb_ratio` / `pe_lyr` / `pe_fwd`
/ `total_market_cap` 等，与当日行情一致。**这是搭 PE/PB 历史分位的唯一路径**，见第七节。

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
- 动态 PE 也可用 `pe_fwd` 反推隐含预期净利 = 总市值 ÷ `pe_fwd`，并注明「隐含的假设是…」。

---

## 七、历史估值分位：怎么搭、限频怎么躲

**没有现成的历史估值接口**，只能循环 `data_quote(date=…)` 采样。实测数据：

- 服务端有**限频**：连续快速调用约 80 次后开始返回
  `查询财报异常：error_type=2 suggest=2 msg=服务限频`（连 `data_finance` 也会被拒）。
- 触发后需要**退避 60 秒以上**，否则后续调用全失败——失败是静默的（返回文本不是 JSON），
  写脚本时**必须断言返回是 JSON**，否则会把失败当成「那天没数据」。
- 实测每次调用约 0.3~1 秒；建议 **间隔 ≥1.5 秒**。

**推荐的采样方案（按公司上市年数选）**：

| 上市年数 | 采样频率 | 调用次数 | 说明 |
|---|:--:|:--:|---|
| ≥ 10 年 | 月末 | ~120 | 分位精度够用 |
| 5 ~ 10 年 | 月末 | ~60~120 | 同上 |
| 2 ~ 5 年 | **月末** | ~24~60 | 建议同时给出「样本区间 + 点数」 |
| < 2 年 | 月末 | < 24 | 样本太少，**只写区间不给分位** |

**不要**逐交易日采样（1200+ 次调用必然被限频，且对分位精度没有实质提升）。

**分位算法**：`分位 = 低于当前值的样本数 ÷ 有效样本数`；只统计 `pe_ratio > 0` 的样本
（亏损期 PE 为负或空，混进去会把分位算低）。报告里必须写出样本区间与点数，
例如「PE 分位 19.3%，样本 2021-12-16 起 1176 个交易日」。

**实测校验（301101，2026-10-28）**：月末采样 59 个点算得 PE 分位 16.9%、PB 分位 25.4%；
用东财 1176 个交易日的日频序列算是 19.3% / 29.3%。**相差 2~4 个百分点，月末采样够用**，
不必为了精度去冒限频的险。

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

---

## 九、一句话速查

```
data_search     → 代码
data_disclosure → 报告期 + 披露日
data_quote      → 行情 + 三种 PE + PB（date= 可查历史，用于自建分位）
data_kline      → 季K/年K（period=season/year, fq=qfq）
data_profile    → 主营/行业/股本/上市日（没有估值）
data_finance    → fields="all", num=16（三大报表 16 期全字段）
data_consensus  → targetPrice + 三年预测（动态 PE）
data_rating     → 评级    data_dividend → 分红
data_shareholder→ 股东    data_risk → 质押/解禁/诉讼
data_notice     → 公告    data_news → 新闻
data_sector     → 同业    data_score → 诊股（仅参考）
data_finsearch  → 文字检索，补商誉/附注类缺口
```
