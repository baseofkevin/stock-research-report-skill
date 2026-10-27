---
name: stock-research-report
description: 输入股票代码或名称，从腾讯自选股（WeStock）调取行情、季K线、三大报表、机构预期等数据，按用户私人笔记的解读范式完成企业分析，并输出美化布局的 HTML 企业信息解读报告。触发词：企业信息解读、个股分析、解读一下、股票分析、帮我看看 XXXX、财报解读、研报式个股分析。
---

# 企业信息解读报告（个股分析 Skill）

把「股票代码」变成一篇**像人写的、有明确结论的**企业信息解读报告，输出为美化的 HTML。

> 分析范式来自用户私人笔记（`/home/kevin/MyData/我github上的私人笔记/` 的 B 系列），
> 指标体系来自《企业财务分析指标体系手册》。
> **三条铁律贯穿全程：现金流 > 利润；趋势 > 时点；结构 > 总量。**

---

## 何时使用

用户给出股票代码、名称或「帮我看看 XXX」时触发。典型输入：

- `解读一下 sz300470`
- `帮我看看 600519` / `分析下贵州茅台`
- `给我出一份 中远海控 的企业信息解读报告`
- `这只票怎么样？002519`---

## 前置条件

**主要数据源：腾讯自选股（WeStock）Connector。**
工具前缀 `data_*` / `tool_*`。若该 Connector 未连接，先按第五节「降级策略」处理。

代码规范：沪 `sh600519`、深 `sz000001`、港 `hk00700`、美 `usAAPL`。
用户只给名称或 6 位数字时，**必须先 `data_search` 拿到带前缀的代码**。

---

## 执行流程（五步，不要跳步）

### 第 1 步 · 取数

按 `references/westock-接口.md` 的清单调用。**最小集合（14 项）**：

```
data_search      → 名称转代码
data_quote       → 现价、涨跌幅、市值、PE/PB、股息率
data_kline       → period=season, limit=40, fq=qfq   （季K线，判断股价位置）
data_kline       → period=year,   limit=10, fq=qfq   （年K线，补长周期）
data_profile     → 主营业务、行业、股本
data_finance     → num=8                              （三大报表，至少 8 期）
data_consensus   → 机构一致预期（动态 PE 的来源）
data_rating      → 机构评级
data_dividend    → years=5                            （分红连续性）
data_shareholder → 股东结构
data_risk        → 质押、解禁、诉讼、ST
data_notice      → limit=20                           （公告：重组/减持/业绩预告）
data_news        → limit=20
data_sector      → mode=search 后 constituent         （同业对比）
```

**取数纪律**
- 同一市场、支持 `codes` 的工具只调一次，逗号分隔。
- `ok:false` 时**原样转述 message，禁止编造**。
- 接口拿不到的字段，先同源替代（consensus → 动态PE，rating → 反推预测净利），
  再用 `data_report` / `data_news` 的文字口径；**仍没有就写「暂无披露」，判定置为「无数据」**。
  **绝对不能用训练记忆或常识补具体数字。**

### 第 2 步 · 计算

对照 `references/指标体系.md` 把原始数变成判断：

- 必算：毛利率及同比、净现比、扣非净现比、应收增速差、现金短债比、速动比率、
  ROE/ROA/ROIC、资产负债率（剔合同负债）、有息负债、利息覆盖倍数（毛利额÷利息费用）、
  商誉占净资产比、理财占总资产比、营运资本占用（应收+存货−应付）。
- 同比口径要标清楚：**年报对年报，半年报对半年报**；
  单季 = 本期累计 − 上期累计；TTM = 本期累计 + 上年全年 − 上年同期累计。
- **每个比率都要同时给分子分母的绝对额**，只给百分比等于没说。

### 第 3 步 · 研判

按 `references/指标体系.md` 的**七步流程**走，并执行一票否决：

1. 验真伪 → 2. 看趋势 → 3. 查质量 → 4. 排雷 → 5. 定性质 → 6. 交叉验证 → 7. 问价格

第 1 步（现金流）或第 4 步（安全）任一「高危」→ 直接否定；
第 6 步故事讲不通（科目变动与收入毛利象限矛盾）→ 直接否定，不必再算估值。

### 第 4 步 · 撰写

严格按 `references/解读范式.md` 的**六段式结构 + 句式模板**写。
核心要求：

- **有明确结论，不骑墙**（看好 / 谨慎观望 / 不看好 / 等安全边际）。
- 每个判断后面必须跟数字；矛盾点（净利增但现金流降、毛利升但应收暴增）要指出来。
- 区分事实与推测：财报数字是事实；机构预测写「隐含的假设是…」；自己的判断写「这么看来…」。
- 推演句式：「这么看来…」「这也说明…」「后续关键看 xxx，若 A 将 X，若 B 将 Y」。
- **禁止**套话（未来可期 / 助力腾飞）与编造；**禁止**把主观感慨混进财务分析正文。

### 第 5 步 · 出报告

把第 2–4 步的结果填进 JSON，跑渲染脚本：

```bash
python3 <skill目录>/scripts/render_report.py data.json -o 报告.html
```

**JSON 字段清单**（全部可选，缺失的区块自动隐藏；完整示例见 `scripts/sample.json`）：

| 键 | 内容 | 对应报告区块 |
|---|---|---|
| `meta` | name / code / tagline / price / change_pct / market_cap / industry / report_date | 顶部横幅 |
| `verdict` | stance / level(good·mid·bad·watch) / headline / summary / tags[] | 结论卡 |
| `core_metrics` | [{label, value, note, flag(ok·warn·bad)}] | 指标卡墙 |
| `price` | records[]（历史区间）/ chart_data[{label,value}] / comment | 股价位置 + SVG 走势图 |
| `business` | intro / segments[{name,rev_pct,margin,comment}] / moat / policy / upstream / downstream | 生意本身 |
| `trends` | years[] / series[{name,values[]}] / comment | 多年财务趋势表 |
| `latest` | period / items[{label,value,yoy,note}] / signals[{name,state(pass·fail·na),result,reason}] | 最新财报 + 三项信号判定 |
| `balance` | items[{label,value,note}] / risks[{name,value,level,threshold}] / comment | 资产负债 + 四项安全指标 |
| `redflags` | [{level, text, evidence, hit}] | 排雷扫描（只列命中的） |
| `scorecard` | steps[{no,name,state,conclusion}] / items[{dim,value,weight}] / total | 七步研判 + 评分条 |
| `conclusion` | paragraphs[] / watchlist[] / triggers[] | 综合研判 + 跟踪清单 |
| `sources` | [{name, detail}] | 数据来源 |

写完 JSON 后：**先自查一遍数字是否都能在取数结果里找到出处**，再跑脚本。
跑完用浏览器或 `present_files` 打开交付。

---

## 降级策略

| 情形 | 处理 |
|---|---|
| WeStock Connector 未连接 | 先提示用户在「连接器管理」中连接**腾讯自选股**；征得同意后可用 WebSearch/WebFetch 拿公开财报数据补齐，**但报告里必须标注每个数字的来源与时效** |
| 部分接口无数据（如港股缺现金流明细） | 该指标判定置「无数据」，在报告中注明原因，**不要用其他市场的口径硬套** |
| 用户只要快速结论 | 跳过 HTML，直接在对话里给六段式的纯文字版 |
| Python 不可用 | 按 `references/解读范式.md` 手写 HTML，视觉规范照抄 `scripts/render_report.py` 里的 CSS 常量 |

---

## 输出与交付

- 文件名建议：`{股票名称}-企业信息解读-{YYYYMMDD}.html`
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
