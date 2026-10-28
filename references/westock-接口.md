# 腾讯自选股（WeStock）数据接口提纲

> 用于企业信息解读报告的取数。工具名以 WeStock MCP 为准，
> 返回统一为 `{ "ok": true|false, "data": ..., "message": "..." }`。
> **`ok: false` 时原样转述 message，禁止编造数据。**

---

## 一、前置：代码规范

| 市场 | 格式 | 示例 |
|---|---|---|
| 沪市 | `sh` + 6 位 | `sh600519` |
| 深市 | `sz` + 6 位 | `sz000001` |
| 港股 | `hk` + 5 位 | `hk00700` |
| 美股 | `us` + 代码 | `usAAPL` |

**用户只给名称或 6 位数字时，先调 `data_search` 拿到带前缀的代码，再取其他数据。**

---

## 二、必取数据（按顺序，一次解读的最小集合）

| 步骤 | 工具 | 关键参数 | 用途 |
|:--:|---|:--:|---|
| 1 | `data_search` | `query` | 名称 → 代码 |
| 2 | `data_quote` | `code` | 现价、涨跌幅、市值、静态/滚动 PE、PB、股息率、换手率 |
| 3 | `data_kline` | `code`, `period=season`, `limit=40`, `fq=qfq` | **季 K 线**：判断股价历史位置（第 1 段） |
| 4 | `data_kline` | `code`, `period=year`, `limit=10`, `fq=qfq` | 年 K：补充长周期高低点 |
| 5 | `data_profile` | `code` | 主营业务、所属行业、股本、上市日期 |
| 6 | `data_finance` | `code`, `num=16` | **三大报表，至少 16 期**（单季倒挤 + 同季同比 + TTM 同时要数据；8 期连两年季报都不够） |
| 7 | `data_valuation` | `code`, `days=1800` | PE/PB 历史序列（历史分位用）。接口没有这一项时，用季 K 收盘 × 当期 EPS 自建，并注明是自建口径 |
| 8 | `data_consensus` | `code` | 机构一致预期（对应动态 PE） |
| 9 | `data_rating` | `code` | 机构评级：可以从评级隐含的目标价反推盈利预测 |
| 10 | `data_dividend` | `code`, `years=5` | 分红连续性，判断股息率含金量 |
| 11 | `data_shareholder` | `code` | 股东结构、大股东性质（央企/民营） |
| 12 | `data_risk` | `code` | 质押、解禁、诉讼、ST 风险 |
| 13 | `data_notice` | `code`, `limit=20` | 近期公告（资产重组、减持、业绩预告） |
| 14 | `data_news` | `code`, `limit=20` | 近期新闻与行业事件 |
| 15 | `data_sector` | `mode=search` → `constituent` | 所属行业及可比同业（用于横向对比） |
| 16 | `data_score` | `code` | 诊股评分，作为交叉参考，**不替代自己的判断** |

可选补充：`data_fund_flow`（资金流向）、`data_technical`（均线 MACD）、
`data_industry_chain`（产业链位置）、`data_report` / `data_dehydrated`（研报观点）、
`data_north_holding`（北向持仓）。

---

## 三、财报字段 → 报告指标的对应

`data_finance` 取回利润表（`income`）、资产负债表（`balance`）、现金流量表（`cashflow`）后，
按下表取值计算：

### 利润表

| 报告指标 | 取自 |
|---|---|
| 营业收入 | `OperatingRevenue` / 营业总收入 |
| 营业成本 | `OperatingCost` |
| 毛利率 | `(营业收入 − 营业成本) ÷ 营业收入` |
| 归母净利润 | `NPParentCompanyOwners` |
| 扣非净利润 | 归母净利润 − 非经常性损益（若接口未返回，查 `data_notice` 或研报） |
| 净利率 | `净利润 ÷ 营业收入` |
| 三项费用率 | 销售 / 管理 / 研发费用 ÷ 营业收入 |

### 资产负债表

| 报告指标 | 取自 |
|---|---|
| 货币资金 | `CashEquivalents` |
| 交易性金融资产 | 需与货币资金合并看「类现金」 |
| 应收票据及应收账款 | `BillAccReceivable` |
| 存货 | `Inventories` |
| 合同负债 / 预收款项 | `ContractLiability` / `AdvanceReceipts` |
| 流动资产合计 | `TotalCurrentAssets` |
| 流动负债合计 | `TotalCurrentLiability` |
| 短期借款 | `ShortTermLoan` |
| 一年内到期非流动负债 | `NonCurrentLiabilityIn1Year` |
| 商誉 | 无形资产下的 `Goodwill` |
| 在建工程 | 固定资产下的在建工程 |
| 未分配利润 / 资本公积 | 所有者权益明细 |

### 现金流量表

| 报告指标 | 取自 |
|---|---|
| 经营活动现金流净额 | `NetOperateCashFlow` / `OCF` |
| 投资 / 筹资活动现金流净额 | 同名科目 |
| 自由现金流 | `经营活动现金流净额 − 购建固定资产等支付的现金` |

---

## 四、TTM 与单季口径的处理规则

- **同比**：本期累计 ÷ 上年同期累计 − 1。**年报对应年报，半年报对应半年报，不要混。**
- **单季倒挤**：`第 N 季度 = 本期累计 − 上期累计`。
  例：Q3 单季营收 = 三季报累计营收 − 半年报累计营收。
- **TTM**：`本期累计 + 上年全年 − 上年同期累计`。
- **趋势图**：优先用年报序列（噪音小），至少取 **5 年**（评判 ROE 连贯性的最低要求）。
- **最新一期**优先用 **中报或三季报**，并注明报告期。

---

## 五、数据缺口的处理

接口拿不到某个字段时：

1. 先尝试同源替代（如 `data_consensus` 拿动态 PE，`data_rating` 反推预测净利）。
2. 再尝试 `data_report` / `data_news` 的文字口径。
3. **仍然没有就在报告里写「暂无披露」，该指标判定置为「无数据」，并写进 JSON 的 `data_gaps`。**
   打分卡里这些项**从分母剔除**（不记 0 分），报告要写清「本次可评 N / 16 项」。
4. **绝对不能用训练记忆或常识补齐具体数字**——这是这份报告的生命线。

分产品/分地区收入明细属于财报附注，WeStock 的三大报表通常不含。
可用 `data_profile` 的主营构成或 `data_report` 的研报摘要补充，
**引用时必须标注来源（如「据 XX 券商研报」）**。

---

## 六、实测补充（2026-10 首次实战：钒钛股份 sz000629）

### 6.1 `fields=core` 实际返回的字段

**利润表**：`OperatingRevenue` `OperatingCost` `OperatingProfit` `TotalProfit`
`NPParentCompanyOwners` `NPDeductNonRecurringPL` `GrossIncomeRatio` `NetProfitRatio`
`ROE` `ROECut` `ROA` `ROIC` `EBIT` `BasicEPS` `RAndD`
`NPParentCompanyYOY` `NPParentCompanyYOY_Q` `NPParentCompanyCutYOY_Q`
`TORGrowRate` `TORGrowRate_Q` `OperatingRevenueGrowRate_Q` `NPPCCGrowRate3Y` `ORComGrowRate3Y`
以及四个 TTM 口径：`NPParentCompanyOwnersTTM` `OperatingRevenueTTM` `GrossProfitTTM` `OperatingProfitTTM`
`ROETTM` `ROATTM` `EPSTTM`

**资产负债表**：`CashEquivalents` `TotalAssets` `TotalCurrentAssets` `TotalNonCurrentAssets`
`TotalCurrentLiability` `TotalNonCurrentLiability` `TotalLiability` `TotalShareholderEquity`
`SEWithoutMI`（归母净资产）`NAPS`（每股净资产）`ShortTermLoan` `LongtermLoan` `InterestBearDebt`
`WorkingCapital` 以及四个现成比率：`CurrentRatio` `QuickRatio` `DebtAssetsRatio` `DebtEquityRatio`
和三个周转率：`ARTRate` `InventoryTRate` `TotalAssetTRate`

**现金流量表**：`NetOperateCashFlow` `NetInvestCashFlow` `NetFinanceCashFlow`（三者的 TTM 版都有）
`GoodsSaleServiceRenderCash`（销售商品收到现金）`FCFF` `FCFE` `NetCashFlowTTM` `OperCashFlowPS`

### 6.2 core 拿不到的科目（实测确认，别再试了）

合同负债 / 预收款项、商誉、在建工程、应付账款、应收票据及应收账款**绝对额**、
存货**绝对额**、一年内到期非流动负债、未分配利润、资本公积。

- 报告里一律写「暂无披露」，依赖合同负债的判定（信号 ②）置「无数据」。
- 现金短债比分母只能取 `ShortTermLoan`，要在报告里注明口径不完整。
- 补救分产品构成：用 `data_finsearch` 搜「{公司名} 主营构成 分产品 毛利率」，
  实测能返回分产品、分地区的收入占比和近四年业绩趋势。
- 补救行业价格 / 政策：同样用 `data_finsearch`，能拿到商品价格月评和产业政策原文。

### 6.3 三个由现有字段反推的技巧

1. **应收、存货的绝对额**：应收 ≈ 营业收入 ÷ `ARTRate`；存货 ≈ 营业成本 ÷ `InventoryTRate`。
   够用来判断绝对额和占总资产比例，但**不要**拿反推值算精确到万元的同比。
2. **家底是赚来的还是融资来的**：股本占比 = 总股本 ÷ `SEWithoutMI`。总股本从 `data_quote`
   的 `total_shares` 或 `data_profile` 的 `regCapital` 取。
   钒钛股份 92.91 ÷ 125.48 = 74%，说明家底主要靠融资，配合「连续零分红」一起读。
3. **单季毛利率**（信号 ① 判定要用）：`GrossIncomeRatio` 是**累计口径**，不能直接当单季。
   必须先按第五节「单季倒挤」算单季营收和单季成本，再算单季毛利率。

### 6.4 三个容易误判的点

1. **应收增速差的机械口径会误报**。营收塌方型企业，应收绝对额没涨、营收大跌三成，
   算出来的「应收增速 − 营收增速」反而大幅为正（> +15pct）。
   必须回看应收**绝对额**：没涨就不是放宽账期，是需求萎缩，不构成垫资风险。
2. **静态 PE 为负不代表便宜**。亏损年度的 `pe_lyr` 是负数（钒钛股份 −263.85），
   此时只能看 PB 和 TTM，并且要在报告里写清「静态 PE 已失真」。
3. **利润大增要拆减值和研发**。大额资产减值计提的次年，反弹里有「不再计提」的成分；
   研发费用降幅大于营收降幅，说明利润里有相当一块是省出来的，不可持续。

### 6.5 小盘冷门票的取数预期

- `data_consensus` 很可能直接返回「未找到一致预期数据」——不是报错，别重试。
- `data_rating` 可能只有 1 家机构。报告里如实写「机构覆盖极低，缺少外部验证」。
- 动态 PE 仍可从 `data_quote` 的 `pe_fwd` 反推隐含预期净利 = 总市值 ÷ `pe_fwd`，
  并在报告里注明「隐含的假设是…」。
