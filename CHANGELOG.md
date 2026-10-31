# 变更记录

> **写作规范（自 2026-10-30 16:54 起）**
>
> 本目录下**任何文件**（`SKILL.md`、`references/`、`scripts/`、`evals/`、示例 JSON、模板与脚本）
> 的改动，都必须留下**具体到时分**的修改时间，不再只写到日：
>
> - 版本标题写成 `## v2.8.1 — 2026-11-02 09:41（一句话说清改了什么）`；
> - `SKILL.md` 的 `updated:` 同步写成 `2026-11-02 09:41`；
> - 时间取改动完成时的本机时间（北京时间 UTC+8，24 小时制，`年-月-日 时:分`），
>   同一分钟内的多次改动照实写同一时分，不许含糊成「上午 / 下午」；
> - 条目正文要说清**改了哪个文件、改了什么**，只写「优化」「调整」不算数。
>
> 下方 v2.7.2 – v2.3.0 的时分按 git 提交时间补登；更早的条目（v2.2.1 及以前）
> 没有可靠的时分记录，保留到日。


## v2.11.2 — 2026-10-31 16:57（把两处接口口径做成固定回归：文档不是基准，返回才是）

v2.11.1 只保证了「这次写对」，没保证「下次写错能被抓到」。这一版把口径验集固化：

- 新增 `evals/fixtures/api-semantics.json`：5 个真实市值样本（`sz300224` 当前 / 2026-09-30，
  `sz301101` 当前 / 2021-12-31 / 2026-09-30）+ `sz301101` 2026 中报的 `MAINOP_TYPE` 三组条目。
  **全部来自 2026-10-30 的采集包**，不是手写的期望值。
- `evals/run.py` 新增 `test_api_semantics()`：
  ① 对每个样本断言 `cap ÷ (单价 × 总股本) ≈ 1`（口径一旦被解释成「亿元」，比值会变成 1e-8）；
  ② 按 `ITEM_NAME` 反推枚举（单一「制造业」名 ≈100% ⇒ 行业、多个品种名 ⇒ 产品、国内/国外 ⇒ 地区），
     与「1 行业 / 2 产品 / 3 地区」对照；
  ③ 要求 `SKILL.md` 与接口文档写同一个结论、不得出现 `1 产品` / `2 行业` / `当前值是「亿元」`，
     且必须写 `/1e8`。
- `SKILL.md` 的「改 skill 自身」检查清单加一条：改单位 / 枚举类描述必须先存实测再改文档。
- 接口文档把「旧文档写成 1=产品、2=行业」这种**带错误映射的引用**改成文字描述
  （文档里不留错误编号，免得被检索到又被抄回去；完整对照留在本文件）。
- 变异测试：把枚举对调、把市值改成亿元量级，两条断言都按预期报错。

## v2.11.1 — 2026-10-31 16:52（修正两处「文档与接口不符」：市值单位、MAINOP_TYPE 1/2；补一道语义闸门）

这两处是真错，而且都属于「结构全对、数字全错」：`check_docs.py` 当时 0 错误，报告却算错。

**① `total_market_cap` 单位**
- 旧文档写「当前值是亿元、历史 `date` 查询是元」，实测**两处都是元**：
  `sz300224` 当前 `11,820,000,000`（12.70 × 930,700,417 = 118.20 亿）；
  `sz301101` 当前 `6,654,000,000`、`2021-12-31` 历史 `7,305,000,000`（54.38 × 134,341,396）。
  两处 `cap ÷ (price × total_shares)` 都 = 1.0000。
- 统一规则：**一律 `/1e8` 换亿元**，取用前用 `price × total_shares` 交叉验一次；
  历史点的股本要用当时的（`sz301101` 2022 年 10 转 5 前 1.34 亿股、之后 2.02 亿股）。
- 同步改掉 `SKILL.md` 取数纪律里的同一句旧口径（原 169 行），否则两处互相打架。

**② `MAINOP_TYPE` 枚举**
- 旧文档写「1 产品 / 2 行业」，**正好相反**：`sz301101` 2026 中报 `TYPE=1` 只有
  「专用设备制造业 100%」（行业），`TYPE=2` 才是镜片 84.9% / 原料 10.5% / 成镜 1.4% / 镜架 1.1%，
  `TYPE=3` 是国内 93.4% / 国外 6.6%。
- 改为「**1 行业 / 2 产品 / 3 地区**，并按 `ITEM_NAME` 内容判，别按编号硬取」；
  同时修掉 `SKILL.md` 取数表与接口文档同一节里「产品拆分用 type 1」的旧说法（三处一起改）。
- 附带发现：`TYPE=2` 会混「其他(补充)」「客户合同产生的收入」这类汇总行，占比小可单列，别并进主产品。

**③ 新增语义闸门（`scripts/check_docs.py` 的 `check_api_semantics`）**
结构检查抓不到「单位/枚举含义写反」，所以单设一道：禁止 `1 产品`、`2 行业`、
`当前值是「亿元」` 三种旧配对；接口文档提到 `MAINOP_TYPE` 附近必须出现 `ITEM_NAME`；
`SKILL.md` 提到 `total_market_cap` 必须写「/1e8」。三条都在本次的真实错误上报过错。

**④ 措辞校准**：旧文说「PE/PB/PS 全被放大 1e8 倍」不准确——PE/PB 分位直接用
`pe_ratio`/`pb_ratio`，不经市值；受影响的是总市值、PS 及一切用市值反算的指标。

## v2.11.0 — 2026-10-31 16:10（采集包并发安全 + 文本层统一 + 分位双口径；落地复盘 12 条 + 审核漏项 5 条）

一次把 `正海磁材-skill复盘与改进建议-20261031.md` 与
`DeepSeekHarness/正海磁材-skill审核-20261031.md` 里的问题收敛掉；原本计划的
v2.10.1 / v2.10.2 / v2.11.0 三个批次合并为一次发布（代码与文档必须同时改，否则对账不过）。

**采集包（P0：终端说「已记录」、文件里没有）**
- `scripts/raw_bundle.py`：新增 `locked()`（`fcntl.flock`，Windows 走 `msvcrt`）与
  `update()`（锁内「重读 → 追加 → 写回 → 回读校验」）；`append()` 的 `seq` 改为 `max+1`；
  `make_raw_data()` 发现重号时重编；`atomic_write_text()` 补 `fsync`。
- `scripts/collect_raw.py`：`add/run` 改走 `_append() → raw_bundle.update()`，
  打印「已记录 #N（包内共 M 条）」，M 是回读后的真实条数；`no_data` 标记也在锁内写入。
- `scripts/sample_valuation.py`：每个采样点走 `raw_bundle.update()`，不再拿启动时的旧副本
  整包写回；收尾统计重新读盘；`--dry-run` 增加耗时预估（3.0s/点 + 每 80 次 60s 退避）
  并压缩明细输出（`-v` 看逐月）。
- `evals/run.py`：新增 `test_concurrency()`——两个子进程同时写 40 条，断言 80 条零丢失、
  `seq` 连续。

**渲染与校验（静默错误）**
- `scripts/render_report.py`：轻量标记（`**粗体**` / 反引号）并入 `esc()`，不再只在
  `_rich()` 覆盖的字段生效（此前 `insights.points`、`watchlist`、`redflags.evidence`
  会把 `**` 原样印出来）；`_rich` 退化为 `esc()` 的别名。
- 新增 `scripts/report_stats.py`：校验器与渲染器共用一套分位算法（`percentile` /
  `trimmed_percentile` / `is_outlier_sample` / `trim_bounds`）。
- `scripts/render_report.py` / `render_md.py`：`percentile_trimmed` 与全样本分位相差
  ≥10pct 时并排显示「历史 X% 分位（缩尾后 Y%）」；缩尾区间外的点画空心圈。
- `scripts/validate.py`：`watchlist/triggers/paragraphs` 元素必须是字符串（dict 直接 err）；
  `market_cap` 与 `cap_note` 重复写「亿元」报 err；护城河五指标缺任一从 warn 升为 err
  （文档一直写「必须五个」）；`percentile_trimmed` 与 series 对账，极端样本缺缩尾口径时告警；
  `total_note` 未提「成长」时告警；`data_rating` 覆盖 <3 家而报告仍用 PEG 定档时告警。
- `scripts/lint_encoding.py`：`BUILTIN_ALLOW` 补 `strong` / `code` / `dict`（标签与类型名）。

**文档（口径收拢）**
- `references/指标体系.md`：§2.1 条件① 改成两个不等式（V 型不算改善）；§3.5 新增
  **分位口径表**（样本、负值、极值、披露义务、禁止项，附正海 47.9% / 62.2% 实例）；
  §6.4 三流组合补「先看资本支出、剔除理财净买入」；§7.1 定义「理财类资产」并明确
  货币资金不混算；§12 #9 指向该定义；§13 声明 16 项**不含成长**、PEG 覆盖 <3 家不定档、
  `watchlist` 载体是字符串。
- `references/westock-接口.md`：`data_rating` 返回结构与 `ratingCnt`（评级记录条数）写清，
  附 `sz300224` 实测三值；§6.4 加 PEG 覆盖率硬规则；§6.2 加 `market_name` 禁用说明与
  板块前缀表（`sz300224` 会被返回「深圳主板」）。
- `references/解读范式.md`：打分卡表下固定写「本卡只评质地不评成长」；跟踪清单注明
  每项是字符串与推荐写法。
- `SKILL.md`：`market_cap` 带单位 / `cap_note` 只写股本；`valuation` 说明
  `percentile_trimmed`；`scorecard.total_note` 固定句；`conclusion` 三个数组都是字符串；
  第 1 步加「采样期间别写同一个包」；取数纪律加 PEG 覆盖率规则；常见错误补两条。
- `evals/cases.json`：新增 4 个用例（富文本、watchlist 传 dict、极端样本缺缩尾口径、
  缩尾口径并排显示），断言新增 `html_contains` / `html_not_contains` / `md_not_contains`。

> 这一版是「先提交再改」的产物：v2.10.0 之前 `collect_raw.py` / `raw_bundle.py` /
> `report_cache.py` / `report_paths.py` / `save_report.py` / `sample_valuation.py`
> 六个脚本一直没进 git，本次先打快照提交，再动代码。

## v2.10.0 — 2026-10-31 15:30（修静默错列/丢说明；采集包不再静默新建；月末采样脚本化）

把复盘里「不报错但产出错」的几类问题一起收口，并补上可复跑的采样脚本。

**渲染不再静默丢内容**
- `scripts/render_md.py` / `scripts/render_report.py`：`business.moat.metrics.judge`
  写成字符串时按**一整条**渲染，不再逐字拆成 `- 五` / `- 年`；
  `redflags_note` 在有命中项时也渲染在命中表之后（以前只在零命中时输出）。
- `scripts/validate.py`：v2 的 `judge` 必须是对象，字符串直接报错（渲染器只做兼容）；
  `financials.yoy/cumulative` 的 `series[].values` 必须与 `headers` 等长，错列报错；
  `price.records` 必须用 `name/range/note`（`label/value` 报错）；删掉
  「年度 7 年 labels ≠ 17 期 periods」的跨图误报，只保留 series 与本图 labels 比。

**采集包安全**
- `scripts/collect_raw.py`：`run/add` 找不到采集包**默认拒绝**，必须显式 `--create`
  或先 `init`；`status/merge` 对缺失/坏 JSON 友好报错；失败摘要打印 `error` 首行
  和原文首段；纯文本 `未找到/暂无/无数据` 标记 `no_data: true`，按合法空返回 exit 0，
  不再和限频/参数错混在一起。
- `scripts/westock_client.js`：新增 `--timeout`（1000~120000ms）和
  `WESTOCK_TIMEOUT`，超时报错带秒数；默认仍是 60s。

**月末采样**
- 新增 `scripts/sample_valuation.py`：读 raw 包已有 `data_quote(date=...)` 按月补缺，
  空返回回退前一交易日，超时/限频分开退避（5/15/45s、60s），成功一条立即落盘；
  `--dry-run` 可先看要采哪些月份；采集包不存在直接报错。
- 文档把 `/tmp` 采集包示例统一改成 `${PWD}/.raw/`，`.gitignore` 加 `.raw/`。

**文档对账**
- `SKILL.md` / `references/指标体系.md` / `references/westock-接口.md`：
  护城河补 `num=28`、取数预算表、四态返回（业务空返回不重试）、`data_dividend {}` 规则、
  日期口径表、`ShortTermLoan` 常见但非必然、申万二级缺失降级、示例数字标为历史快照、
  经营性 PB 的 `TradingAssets` 上限口径、当年 FCF 待年报、排雷 #9 的 30% 阈值、
  C1/C2 不临时加第 17 项；`ratingCnt` 等接口字段加入 `allow_words.txt`。

**回归**
- `evals/run.py` 新增「静默降级防护」：`judge` 字符串、表头错列、`price.records`、
  命中后的 `redflags_note`、采集包缺失守卫、`sample_valuation --dry-run`。

## v2.9.0 — 2026-10-31 14:38（已研究过的公司只更新三件套；新公司才完整取数）

解决「同一家公司反复研究时把 16 类接口和 40~85 次月末采样全部重跑」的浪费，
同时避免把「旧报告」误当「没研究过」。

**缓存识别**
- 新增 `scripts/report_cache.py`：扫描 `env` 的 `REPORT_OUTPUT_DIR` 顶层 `*.json`，
  按 `meta.code`（优先，6 位数字也认）或 `meta.name` 匹配旧报告；返回最新一份的
  JSON/HTML/MD 路径、报告日、行情时点、`raw_data` 条数、三件套是否齐全。
  `lookup --json` 输出 `cached / count / latest / reports / hint`，
  没找到时加 `--fail-if-missing` 可 exit 3，方便脚本按退出码分支。
- 同公司多份历史文件按 `report_date` / 修改时间取最新；文件名带旧日期不影响识别。
- 兼容 v2.8.0 之前只有 `.html/.md`、没有 JSON 的历史报告：按文件名
  `名称-企业信息解读-YYYYMMDD` 和 Markdown 首行标题 `# 名称（sz123456）企业信息解读`
  识别公司，返回 `legacy_only: true`；这种报告不能直接复用（缺 `raw_data`），
  先完整取数一次补齐 JSON，之后才走增量。

**增量更新**
- `save_report.py` 新增 `--reuse` / `--code` / `--name`：
  - `--reuse --code sz301101`（不给新 JSON）→ 直接读旧 JSON，按 env 重写同名三件套，
    不联网、不重拉数据；
  - `new.json --reuse` → 新 JSON 缺 `raw_data` 时自动从旧报告补；
  - `new.json --reuse --raw new-raw.json` → 旧 `raw_data` 保留，新采集包追加进 `calls`；
  - 找不到旧报告时 exit 4，并提示「第一次研究走完整取数」。
- 位置参数 `json_path` 改为可选；校验、`_data_package`、三件套同名规则不变。

**文档**
- `SKILL.md` 第 0 步改为「先确认三件事（缓存 / 报告期 / 行情时点）」，
  新增「两条路线：已研究过 vs 第一次研究」对照表；第 5 步补 `--reuse` 命令；
  输出与交付补缓存说明；常见错误补 19–20 条（重复全量取数、同公司散成多份）。
- `check_docs.py` 输出契约增加 `report_cache.py`、`--reuse` 对账；
  `evals/run.py` 增加「保存后能查到缓存 / 复用模式不新增文件 / 新公司不误判」回归。


## v2.8.0 — 2026-10-31 14:23（原始数据与计算结果合并为同名 JSON；输出目录改由 env 配置）

这一版改的是**交付形态**，不动 16 项 / 25 条 / 满分 66 这些结构常量。

**一个 JSON 同时装原始数据与计算结果**
- 新增 `scripts/raw_bundle.py`：定义 `raw-v1` 采集包（`schema/code/created_at/calls[]`），
  每条调用记录保留 `source / tool / params / at / ok / response|raw_text`，失败返回也原样留；
  提供合并、统计、结构校验函数。
- 新增 `scripts/collect_raw.py`：`init / add / run / status / merge` 五个子命令。
  `run` 直接调 `westock_client.js call` 并把完整返回写进采集包；走 `data_*` connector
  工具时用 `add --response-file` 留痕；东财 F10 / 网页补数用 `--source eastmoney --url`。
- 新增 `scripts/save_report.py`：合并 `--raw` 采集包 → 调 `validate.py`（含 `raw_data` 闸门）
  → 一次写出 `{basename}.json` / `.html` / `.md` 三件套。JSON 根节点是计算结果，
  `raw_data` 是远程原始返回，`_data_package` 是打包说明（保存时间 / 主名 / 目录）。
- `scripts/sample-raw.json`：`raw-v1` 最小示例，带 WeStock 与东财 F10 各一条。

**输出路径改由 env 配置**
- 新增 skill 根目录 `env`（UTF-8）：`REPORT_OUTPUT_DIR` 决定三件套保存目录，
  `REPORT_BASENAME_TEMPLATE` 决定三个文件共用的主文件名（`{name}` / `{code}` / `{date}`）。
  路径支持中文、空格、`~`、`$HOME`；相对路径以 skill 目录为基准。
- 新增 `scripts/report_paths.py`：env 解析（BOM、引号、行尾注释、`export` 前缀）、
  中文/空格路径解析、非法文件名字符清洗、三件套同名路径生成；也可用
  `python3 scripts/report_paths.py --data data.json` 先查看会存到哪。

**脚本回归**
- `render_report.py` / `render_md.py`：省略 `-o` 时不再写到当前目录 `report.html/md`，
  而是按 env 目录 + `meta.name/code/report_date` 生成同名文件；新增 `--env-file` /
  `--out-dir` 仅供排障覆盖。`-o` 仍可用，但正式交付走 `save_report.py`。
- `validate.py`：抽出 `check_data()` 供内存校验；新增 `--require-raw`，
  `save_report.py` 默认打开，缺 `raw_data` / `calls` 为空 / 调用记录结构不全都报错。
  历史样例不带 raw_data 时默认不强制，避免旧用例全红。

**文档**
- `SKILL.md`：第 1 步新增「原始返回怎么留」采集命令；第 5 步改为
  `validate.py` → `save_report.py --raw` → `lint_encoding.py`；JSON 字段表登记
  `raw_data` / `_data_package`；「输出与交付」重写为 env 配置说明 + 同名三件套约定；
  常见错误补 16–18 条（散落 raw、绕过 env、三件套不同名）。
- `references/westock-接口.md` 新增 §2.1 采集包要求；`references/接入WeStock.md` §四
  补 `collect_raw.py` 用法；`CHANGELOG.md` 本条。


## v2.7.2 — 2026-10-30 13:22（按 301087 实测反馈收口：取数三态、排雷出口、估值末端点）

这一版几乎全是「踩过一次的坑」固化，改法以文档为主、代码只补闸门，**不动 16 项 / 25 条 / 满分 66
这些结构常量**。

**取数层（静默降级）**
- `westock_client.js call`：工具返回**非 JSON** 时改为 stderr 报错 + **exit 3**（原文仍打到
  stdout）。旧版把原文打出去还 exit 0，`call … > x.json` 会留下一个不是 JSON 的文件，
  失败被推迟到消费方。抽出纯函数 `parseToolText()` 并新增 `selftest` 子命令（离线、不发请求）。
- `westock-接口.md` 新增 **5.0「三种返回形态」**：`ok:false` / `ok:true` 但空列表 /
  不是 JSON，三者的处理规则完全不同；并登记已确认的合法空返回（`data_shareholder` 对
  301087 三个列表全空）。
- 新增 **6.5 `data_sector` 两步走**：`mode=search` 必须带 `query`（漏了返回纯文本
  「请提供搜索关键词」），`mode=constituent` 的参数名是 **`code`**（值是 `sectorCode`）——
  这两点都实测过，附完整请求与返回样例。

**排雷（盲区与出口）**
- `指标体系.md` §12 #1 改为**组合判据**：保留「净利大增 + 扣非微利 + 现金流恶化」，
  并入「利润增长 + OCF 同比降 > 30% + 净现比 < 1 且应收/存货周转未恶化」。
  301087（OCF −55.2%、净现比 0.9，而扣非健康、应收周转 43→37 天）由此从「一条都不中」
  变成 #1② 命中。**条数仍是 25**，`redflags.id` / 分母 / 渲染器常量全部不动。
- `redflags_note` 正式登记进 SKILL 的 JSON 字段表：零命中时必填（≥10 字），
  `validate.py` 对 v2 零命中且空 note 直接报错。渲染器早就读这个字段
  （`render_report.py` / `render_md.py`），但文档里没写——等于只有写源码的人知道。

**估值（末端点口径）**
- `validate.py`：`current` 与 `series` 末点的 5% 断言改为**按日期分级**——
  末点日期早于报告日（月末采样正常现象）只提醒；同日/更晚仍报错。
  以前一律报错，实际会逼着人往序列里塞一个非月末点，污染分位口径。
- `SKILL.md` / `解读范式.md` / `westock-接口.md` 补「series 末点怎么取」：
  采样覆盖当月就**替换**该月最后一点，只到上月末才**追加**，并在 `note` 写明采样频率。

**编码自检（误报治理）**
- `lint_encoding.py` 改**两级判定**：`[error]` 全小写怪串（必须改）、
  `[warn]` CamelCase / 首字母大写单词（大概率是品牌名，人工确认即可，不再堵交付）。
- 业务词白名单外置到 **`scripts/allow_words.txt`**（一行一词），换公司只加数据不改代码；
  行内豁免 `<!-- lint-allow: SmartVitals -->`、文件级 `<!-- lint-allow-file: … -->`。
- 修掉两处历史漏报：`CHANGELOG.md` 里的 `undici` / `llhttp` 一直被当乱码（skill 自己的文档
  从没进过 lint），以及豁免标记本身会被判可疑串。

**文档对账（check_docs.py）**
- 新增：限频三数（`WESTOCK_INTERVAL` 默认 1600 ↔ 文档的 80 次 / 60 秒 / 1.6 秒）、
  两个跨源字段的 URL 模板（`CONSTRUCT_LONG_ASSET` + `RPT_F10_FN_MAINOP`）、
  「渲染器读了但 SKILL 没登记」的 JSON 键（`redflags_note` 就是这么被找出来的）。
- `westock-接口.md` 新增 **8b 主营构成**：`RPT_F10_FN_MAINOP` 的字段名
  （`MAIN_BUSINESS_RPOFIT` 是**拼写错误但必须照抄**）、`MAINOP_TYPE` 1/2/3 的含义、
  金额单位与比率的写法陷阱。
- `evals/run.py`：把 skill 自身文档的 lint 与 `westock_client.js selftest` 也纳入回归。

## v2.7.1 — 2026-10-30 13:22（客户端去掉 undici 依赖，修复沙箱内必崩）

- `scripts/westock_client.js`：新增 `postOnce()`，改用 `node:https` / `node:http` 直连，
  **不再使用全局 `fetch`**。原实现在容器/沙箱里会抛
  `RangeError: WebAssembly.instantiate(): Out of memory`（undici 的 llhttp WASM 分配失败），
  导致 `check` 都跑不过、整个 skill 不可用。`rpc()` 相应改为读 `postOnce()` 返回的 `res.text`。
- 30 秒静默超时改为 60s 显式超时（`req.setTimeout`），限频与网络异常都能明确报出来。
- 实测：301087 全流程 16 次接口 + 49 点月末采样，未触发退避。

## v2.7.0 — 2026-10-30 12:20（按全面审计修复：结构闸门、字段事实、结论一致性与双渲染器）

这一版把审计中发现的交付级问题收口，重点不是加功能，而是让「错误的报告出不来」。

**结构闸门（validate.py）**：
- v2 八节改为必需：缺 `price` / `core_metrics` / `business` / `financials` / `redflags_checked` /
  `scorecard` / `valuation` / `conclusion` 任一块直接报错，不再静默跳过。
- `verdict.stance` 必填；`core_summary` 必填且 ≥8 字；`core_metrics` 少于 10 项报错；
  `scorecard` 少于 16 项报错；`redflags_checked` 必须为 25。
- `price.chart_data[].value` 必须是数字；`valuation.current` 必须对齐 series 末点；
  `scorecard.total` 的分母和括号内得分率都要与实算一致。
- 护城河/估值检查移出 `if financials`，没有财务块也不再跳过。

**数据事实**：
- 商誉字段改为 `GoodWill`（不是 `Goodwill`），长期借款 `LongtermLoan` 存在；
  `NonCurrentLiabilityIn1Year`、`TradingAssets`、`ContractLiability`、`PaidInCapital` 在 `fields="all"` 里。
- 字段数改为「随公司科目变化」：301101 49 / 600315 51 / 600519 53；`core` 实测 24（不是 25）。
- 补单位陷阱：`data_quote` 历史 `total_market_cap` 是元、当前是亿元；`data_consensus` 金额是万元；
  `data_profile.regCapital` 是万元。

**结论一致性**：
- sample/评测用例的 ROIC 拆成「账面 10.8% / 经营 43.1%」；打分卡该项改为 2 分，总分 47/66=71.2%，
  与「看好但等安全边际」矩阵一致。
- PE/PB 分位统一为 13.8% / 24.1%；删掉不在 series 内的 2021 年 106 倍叙事；
  零命中排雷按严格定义重写为 0 / 25，并补 `redflags_checked`。

**渲染器**：
- 八节编号统一由 `SECTION_TITLES + numbered()` 生成，缺节不再跳号/重号；v1 兼容路径也走同一套。
- 零命中排雷固定输出「命中 0 / 25 条」，不再整节消失。
- HTML 补 `financials.charts_title`、护城河 ② 标题；MD 同步；`price.chart_data` 字符串不再崩溃。
- 修正右轴柱状图基线、`height` 字符串、`core_summary` 渲染。

**文档/对账/测试**：
- `check_docs.py` 标题对账改为直接读 `SECTION_TITLES`，覆盖一~八；字段检查不再用「不存在」豁免
  反向错误；`--refresh` 改为三只股票并集、先抓后写、原子替换。
- `lint_encoding.py` 剥标签插入空格，修 `pctROIC` 误报；表格行不再整行跳过。
- `evals/run.py` 增加 lint 和节编号连续性断言；新增 moat 对象、零命中、缺节、price 字符串等用例。

## v2.6.3 — 2026-10-30 11:07（把二节的「初步研判」职责写进 SKILL + 标题对账自动化）

上一版把二节改名成「主要指标初步研判」，配套要求却只写进了 `解读范式.md`——
SKILL 里没有，等于「改了 A 处忘了 B 处」的老毛病又犯一次。这个版本补齐，并让机器盯着。

**SKILL 补三处**：
- 骨架表二节的内容列：`摘要卡片（≥10 项）` → `摘要卡片（≥10 项）+ 一句初步判断`。
- 骨架表后新增「**八节的职责不重叠**」：二摆数+初判 / 六摊推导 / 七判贵不贵 / 八定性和跟踪，
  并写明「二节把结论说死，六、八节就没得写」。
- 第 4 步「撰写」新增硬要求：**二节收尾必须有一句初步判断**，这一节不下结论。

**`check_docs.py` 加第 9 类检查「节标题对账」**：SKILL 骨架表、`解读范式` §二 小节标题、
渲染器默认标题字符串，三处必须指同一节（允许一方是另一方的前缀，如「财务全景」⊂
「财务全景与跨年趋势」）。v2.6.2 那次改名手动同步了 5 个文件，以后漏一处就报错。

- `--selftest` 的变异注入改用占位符（`@VER@`、`@SEC2@`）取当前真值，
  版本号或标题再改也不会让自测失效；注入 8 处、抓到 10 处（标题不一致会同时报文档与渲染器两处）。

## v2.6.2 — 2026-10-30 11:03（第二节改名）

第二节标题：**核心指标与估值 → 主要指标初步研判**。

改的不只是字面——这一节的职责本来也不是"估值"，是"先把几个数摆出来、给一句初判"，
估值的位置在第七节。顺带把要求补严：

- `render_report.py` / `render_md.py` 的默认标题同步（编号仍是「二」，随骨架自动排）。
- SKILL 骨架表、JSON 字段表、`解读范式` §一的映射表与 §二 小节标题，四处一起改。
- `解读范式` 二节新增要求：收尾必须给**一句初步判断**（如「初步看，增收不增利，现金流比利润好看」），
  并明确这一节**不下结论**——定性归第六节七步研判与第八节综合研判。

## v2.6.1 — 2026-10-30 10:59（解读范式改成八节模板）

`references/解读范式.md` 原来只有 §一 标了「六段式 → 八节」的映射，正文却仍是
「第 1~6 段」的旧模板，而且两个关键块位置错了。改成一节一模板：

- §二 标题从「每段的写法模板」改为**「八节的写法模板（按成稿顺序）」**，
  六个「第 N 段」全部换成八个小节标题，与 SKILL 骨架逐一对应。
- **护城河四步**原来夹在「生意」和「财务」之间，现在收进三节（作为四级子标题）；
  **企业估值四步**原来也在同一位置，现在归位到七节。
- **补上原先没有模板的两节**：五节（排雷，编号+证据+后果三件套、分母固定 25、
  零命中也要交代）和六节（七步一步一行带数字、打分卡 `null` 剔除分母、得分率必须能推出 stance）。
- 四节补「三层口径（累计/单季/TTM）必须齐」和图的常规三张；二节明确「只报数和 PE 梯度，
  分位留给七节」，避免两节互相重复。
- 修掉一处文本损坏：语气一节里 `补充：`帝3年内）。` 是残句，重写为括号+破折号的用法说明。
- 连带改掉跨文档的旧编号：SKILL「手册第 4 段」→「四节」、接口文档「第 1 段」→「一节」，
  SKILL 撰写步骤改为指向第二节的八节模板。
- `lint_encoding.py` 放行行首 markdown 标题井号（四个井号曾被当成「重复字符」误报）。

## v2.6.0 — 2026-10-30 10:51（新增 check_docs.py：文档 ↔ 代码对账）

v2.5.1 那次审计抓出的 6 处不一致，全是「改了 A 处忘了 B 处」。这个版本把这类检查自动化。

`scripts/check_docs.py` 做 8 类对账，**离线可跑**（工具/字段名用 `scripts/snapshots/westock.json`
快照，`--refresh` 才联网重建）：

| 检查 | 抓的是什么 |
|---|---|
| 版本一致 | SKILL frontmatter `version` ↔ CHANGELOG 最新条目；`schema_version` ↔ 渲染器认的版本 |
| 章节引用 | 所有 `§N` 必须在 `指标体系.md` 有对应 `## N.` |
| 文件路径 | 文档里写的 `references/*.md`、`scripts/*.py` 必须真实存在 |
| 工具名 | 文档提到的 `data_*`/`tool_*` 必须在工具快照里（`data_valuation` 这种「故意说不存在」的除外） |
| 字段名 | 反引号里的驼峰字段必须在字段快照里；上下文说「不存在」的不算错 |
| 数量常量 | 排雷 25 条、护城河 5 指标、打分卡 16 项/权重和 33、取数 16 次调用，与代码常量对账 |
| JSON 键可达 | 骨架表和字段表承诺的键，渲染器里必须真有 `data.get("…")` |
| 报告骨架 | 8 节、编号连续、每节声明的键都读得到 |

**内置变异测试证明它不是空转**：`python3 scripts/check_docs.py --selftest`
会在临时副本里注入错误再跑一遍；：往副本里注入 7 类错误（改版本号、引用 §14、写错工具名、
拼错字段、权重 ×2→×4、排雷 25→26、骨架键 `valuation`→`valuationZ`），**7/7 全部报错**。
其中第一轮漏掉了 `valuationZ`——正则只认小写，大写拼错会逃过检查，已修。

- `evals/run.py` 末尾挂上这项检查，与 5 个用例一起跑，失败则整体 FAIL。
- SKILL 第 5 步新增「改 skill 本身时跑 check_docs」的流程，常见错误补一条。

**踩坑记录**：skill 目录是软链接，`cp -r` 复制的是链接本身，变异测试第一轮直接改到了真文件
（已被 git 还原）。以后做这类测试用 `cp -rL` 解引用。

## v2.5.1 — 2026-10-30 10:44（对齐审计：指标公式 ↔ 数据源 ↔ 校验脚本）

把 SKILL 全文按「要求 / 完整性 / 指标与数据源对齐」三轴审了一遍，修掉 6 处不一致：

- **打分卡缺项规则自相矛盾**：`指标体系 §0` 写「拿不到数据的指标记 0 分」，
  而 `§13 缺项处理` 写「不记 0 分、从分母剔除」。改前者对齐后者——
  0 分是「中性」，缺数据是「不知道」，混起来会把数据不全的公司判成变差。
- **取数清单数量对不上**：标题写「最小集合（16 项）」，实际列了 18 行。
  拆成「16 次接口调用 + 1 轮历史采样」，并把东财资本支出单列成「两个补充动作」表。
- **期数阈值文档与校验器不一致**：文档说「10 期起、16 期用满」，校验器在 <16 就告警，
  连 SKILL 自己承诺「可直接渲染」的 `sample.json`（11 期）都被警告。校验器改为
  <10 报错、<12 提醒「建议拉满 16 期」。
- **三个指标补上数据源口径**：① 现金短债比——WeStock 没有短期借款明细，
  用 `InterestBearDebt` 保守替代并注明；② 商誉——没有 `Goodwill` 字段，
  必须走 `data_finsearch` / 年报附注 / 东财 F10 补，补不到就判不可评，**不许拿无形资产凑数**；
  ③ 扣非——接口直接给 `NPDeductNonRecurringPL`，不用自己推。
- **ROE 口径**：接口回传的 `ROE`/`ROIC`/`ROA` 只能做交叉验证，自己算要用 `SEWithoutMI`
  且注明期末/平均口径，两个数差超 1pct 要交代。
- **结论矩阵接上第七节**：估值档位原本只看 PEG + 经营 PB 分位，补上「PE/PB/PS 三分位方向
  不一致时先查分母污染，再按保守档定」。
- 接口文档 §2 表后补一句指引：估值采样与资本支出不在这张表里，见第七/八节。
- `sample.json` 的 `_note` 注明其 11 期是历史抓取所致，实际使用请拉满 16 期。

## v2.5.0 — 2026-10-30 10:35（框架固化：报告骨架八节 + 示例同步）

把今天新增的两块内容**写进框架本身**，而不是只留在代码里。

- SKILL.md 新增 **「报告骨架（八节，顺序不要变）」** 表格：节次 / 标题 / 内容 /
  必备图表 / 对应 JSON 键。之前八节只散落在字段表里，容易被漏掉。
- `references/解读范式.md §一` 改成 **六段式（思考路径）→ 八节（成稿）** 的映射表，
  并点明「估值在八节里出现两次：二节给数、七节给位置」。
- 取数清单补两件事：① 估值必须**月末采样**（40~85 点、间隔 ≥1.6s、约 80 次触发限频、
  退避 60s），PS 需要 `OperatingRevenueTTM` 并按 `InfoPublDate` 做前视过滤；
  ② **资本支出只能从东财 F10 补**（WeStock 无此科目，FCFE/FCFF 不可用）。
- 撰写要求补两条硬约束：护城河四件套（五指标表 + 两图 + ROIC/WACC + 来源表）、
  估值三曲线（每张图下写读法，三个分位并排给结论）。
- 常见错误补两条：只报一个分位、护城河写成散文。
- JSON 字段表修正过期标注：「七、综合研判」→「八」（无 `valuation` 时回落为七）、
  估值行「历史分布图」→「三条历史走势曲线」、标题缺省编号由渲染器自动决定。
- **`scripts/sample.json` 补全**：`business.moat` 改为对象、新增 `valuation`，
  全部用明月镜片（301101）真实数据（2021–2025 财报 + 东财资本支出 + 57 个月末估值采样），
  渲染出来就是八节完整报告——之前这份「可再渲染的完整示例」还停在旧结构。

## v2.4.1 — 2026-10-30 10:29（估值图改为时间序列曲线）

直方图看不出时间顺序，改成折线：**横轴时间、纵轴倍数，当前值标在曲线末端**。

- `valuation.metrics[].series` 改为 `[{d,v},…]`（带日期）；纯数值数组仍兼容，
  但横轴会退化成序号，validate 会提示。
- 新图 `svg_series()`：历史曲线 + 面积填充 + 中位虚线 + 末端当前值圆点与粗体标注，
  横轴按年份打刻度（等间隔取点会让月份漂移）。PE 与 PB/PS 样本数不同，
  **起点可能不同，图上已注明，别拿峰谷硬对齐**。
- 标题行补「区间 / 样本数 / 起始月份」，MD 表同步加起始月份列。
- 估值一节的行文改为讲形状：2021 年同步见顶 → 四年下台阶 → 2025 反弹 → 2026 回落，
  并解释 PE 末端断崖是三季报的利润垫高（30x → 17.5x），不是股价上涨。
- 回归用例同步：两个指标改用带日期的点，一个保留纯数值以覆盖向后兼容。

## v2.4.0 — 2026-10-30 10:20（新增第七节「企业估值」：PE/PB/PS 历史分位图）

报告结构从七节变八节：`六、七步研判` → **`七、企业估值`** → `八、综合研判`。

- 新增 `valuation` 数据块：`metrics[{key: pe|pb|ps, name, unit, current,
  series[], tone?, badge?, note}]`。**分位、中位、区间由渲染器从 `series` 现算**，
  数据里不用手填（填了也会被 validate 用重算值对账，差 3pct 就报错）。
- HTML：每个指标一张历史分布直方图——柱子是历史样本，竖线是当前值，虚线是中位，
  图内直接标「当前 X.Xx · 历史 N% 分位」。标题行给分位徽章（绿=低位/黄=中性/红=高位）。
- `tone` / `badge` 可覆盖默认判定：PE 被一次性收益垫低时写
  `tone:"mid"`、`badge:"名义 0% 分位（口径失真）"`，避免把人骗进"最便宜"。
- 结论要求：三个分位并排读，并检查分母是否干净（一次性收益、商誉减值、亏损），
  最后给出「便宜的原因」——市场没发现，还是利润已经塌了。
- MD 版同构：一张「当前/历史分位/中位/区间/样本」表 + 每个指标的读法要点。
- 章节编号自适应：没有 `valuation` 的报告，综合研判仍是「七」，不会跳号。
- `scripts/westock_client.js` 改为可 `require` 的模块（`module.exports`），
  采样脚本直接复用它的取数与鉴权，**凭据仍然不落盘**。
- 采样方法：`data_quote(date=…)` 月末采样（上海家化 83 个时点，2019-12～2026-10），
  PS = 当日总市值 ÷ 最近一期已披露 TTM 营收（按 `InfoPublDate` 做前视过滤）。
- `evals/` 增至 5 个用例（新增 `valuation-v2.json`）。
- 样板：上海家化 600315 重渲染，validate 0 错 0 警；结论是「PB 8%、PS 1% 在历史地板，
  剔除 4.01 亿一次性收益后 PE 43.8x 反而在 61% 分位」——名义最便宜，实际不便宜。

## v2.3.0 — 2026-10-30 10:03（护城河模块：五指标 + 趋势图 + ROIC/WACC）

按「先用财务数据验证有没有护城河，再回答护城河从哪来」的思路重做 `business.moat`。

- `business.moat` 从**一段文字**升级为**对象**：`text` / `strength` / `years` /
  `metrics.rows`（fcf、fcf_margin、net_margin、roe、roa 五个 key）/ `charts` /
  `roic{value,wacc,spread,note}` / `sources[{type,strength,evidence}]` / `verdict`。
  **旧的纯字符串仍然兼容**，但 validate 会告警缺表缺图。
- HTML 渲染：五指标矩阵表（指标 × 年份）+ 两张趋势图（FCF 柱 + FCF/营收 线；
  净利率/ROE/ROA 三线）+ ROIC/WACC 三张卡片（差值正绿负红）+ 来源表（强/中/弱/无）
  + 结论引用块。MD 版同构（表格 + 图的文字读法）。
- 支持轻量标记：`**加粗**` 与 `` `代码` `` 在护城河里会渲染成 `<strong>`/`<code>`，
  不再是裸露的星号；结论段与立场标签一并修好。
- `references/指标体系.md §9` 扩写：五个指标的公式与口径陷阱、阈值分档、
  一致性规则（5 年里 ≥4 年达标）、ROIC 剔除超额现金的理由、护城河五类来源的判断线索。
- `references/解读范式.md`：护城河一节的四步写法 + 句式模板 + 收尾反问
  「对手拿 10 个亿进场能不能抢走这门生意」。
- `references/westock-接口.md §八`：**FCF 的资本支出必须外补**。WeStock 现金流量表没有
  这个科目，`FCFE`/`FCFF` 口径不明（上海家化 2024 年 OCF 2.73、真 FCF 1.77，
  接口给 −14.19），`NetInvestCashFlow` 把买理财当投资（2025 年低估 4.6 亿），
  资产负债表倒推又缺折旧摊销字段。改用东财 F10 `CONSTRUCT_LONG_ASSET` 补一个字段，
  并在报告里注明跨源。
- `scripts/lint_encoding.py`：全大写 + 下划线的接口名（`RPT_F10_FINANCE_G`）不再误报为乱码。
- 样板：上海家化（600315）2019—2025 七年数据重算并重渲染，validate 0 错 0 警。

## v2.2.1 — 2026-10-28（接入过程可复用）

把「怎么在终端里连上 WeStock」从一次性操作沉淀成文档 + 脚本。**不含任何本机凭据**，
换电脑照做 + 重新授权一次即可。

- 新增 `references/接入WeStock.md`：插件缓存位置、凭据信封结构（AES-256-GCM +
  HKDF-SHA256，`info="workbuddy-oauth-credentials-v1"`，AAD=`userId|serverKey|fieldName`）、
  MCP 协议细节（必须带 `Accept: text/event-stream`、`notifications/initialized` 返回空体、
  结果是 SSE 的 `data:` 行、`content[].text` 里还是 JSON 要二次解析）、限频与排查表、
  安全红线（token 不落盘、不拷贝 `.master.key`+凭据文件到别的机器）。
- 新增 `scripts/westock_client.js`：Node ≥18 零依赖客户端，
  `check` 看端点/有效期/连通性，`tools` 列真实工具，`call <tool> '<json>'` 取数。
  返回非 JSON 时**直接报错退出**，避免把「服务限频」误当成「那天没有数据」。
- `SKILL.md` 前置条件接上这两个文件；降级策略补 Node 不可用、凭据鉴权两行。

## v2.2.0 — 2026-10-28（接口实测后重写）

拿到 WeStock MCP 的真实端点（`https://stockbuddy.qq.com/cgi/cgi-bin/openai/mcp/mcp`，
streamable-http + OAuth）后，把两份接口文档从「照着旧笔记猜」改成「照着实测结果写」。
**上一版有两处是错的，会直接误导取数：**

1. **`data_valuation` 这个工具不存在。** 历史 PE/PB 只能靠 `data_quote(date=…)` 循环采样自建。
2. **`data_finance` 默认的 `fields="core"` 只有 25 个字段**，确实缺应付账款、存货、应收、
   其他应收、合同负债的绝对额——但**传 `fields="all"` 就有 49 个字段，全都能拿到**。
   旧文档写「实测确认，别再试了」，导致报告里把本来拿得到的数据写成「暂无披露」，
   进而把打分卡相应项判成「不可评」，人为压低得分。这是最严重的一处。

其余实测结论：

- `fields="all"` 的字段名反直觉，已列表对照：`NotAccountsPayable`=应付账款、
  `OtherReceivableED`=其他应收款、`TradingAssets`=交易性金融资产（经营性 PB 必需）、
  `TConstruInProcess`=在建工程、`RetainedProfit`=未分配利润、`CapitalReserveFund`=资本公积。
- 真正拿不到的只有：**商誉**、短期/长期借款明细（只有 `InterestBearDebt` 合计）、
  存货的产成品/发出商品拆分。这三项标「不可评」，不猜。
- 利润表/现金流量表带 `_Q` 单季字段，实测与倒挤一致（301101 2026Q3：`_Q`=2.7342 亿 vs
  倒挤 2.73 亿）。**仍以倒挤为准**，`_Q` 用来做一致性校验。
- `data_disclosure` 返回 `reportEndDate` + `disclosureDate`，正好做第 0 步的「报告期确认」，
  已加入最小取数集合。
- **服务端限频**：连续快速调用约 80 次后返回 `查询财报异常：error_type=2 suggest=2 msg=服务限频`，
  之后 `data_finance` 也会被拒；需退避 ≥60 秒。失败时返回的是纯文本不是 JSON，
  采样脚本必须断言返回格式，否则会把限频误当成「那天没有数据」。
- 历史分位采样方案：**月末采样 24~120 个点**，间隔 ≥1.5 秒；不要逐交易日（1200+ 次必然限频）。
  分位算法只统计 `pe_ratio > 0` 的样本，并写明样本区间与点数。

## v2.1.0 — 2026-10-28

这一版全部来自一次实跑（301101 明月镜片）暴露的问题，按「会算错 → 会缺件 → 会静默失真」排优先级。

### 数据口径（会算错结论的部分）

- `data_finance` 期数 **8 → 16**。8 期连「单季倒挤 + 同季同比 + TTM」三件事都不够，
  更达不到第四节自己写的「≥10 期」门槛。
- 新增 `data_valuation`（PE/PB 历史序列）。此前 §3.5 要求 5–10 年分位，但工具集里只有当下值，
  指标无法执行；接口没有时用季 K 收盘 × 当期 EPS 自建，并注明自建口径。
- §3.5 补「样本区间规则」：上市不足 5 年用「上市以来」并写明起点与交易日数，不足 1 年不给分位。
- **缺项不再记 0 分**。0 分是「中性判断」，缺数据是「不知道」；改为从分母剔除、按可评项归一化，
  并要求报告写清「本次可评 N / 16 项」。此项会系统性压低数据不全公司的得分。

### 结论推导（会自相矛盾的部分）

- §13 结论映射从「6 条 if-else」换成**三维矩阵**（否决项 × 得分率 × 估值档位）。
  原表没有覆盖「总分显著为正 + 第 7 步偏贵 + 第 5 步平平」这一格，
  而实战里这一格最常见——不补就只能拍脑袋，与「不许拍脑袋」冲突。
- 补「边界情形选更保守的一档，并说明理由」。

### 交付流程（会缺件/失真的部分）

- 新增 `scripts/validate.py`：校验 schema 版本、periods 与每行等长、图表值必须为数字、
  评分卡 16 项权重合计 = 33 且 `total` 与实算一致、`redflags.id` 在 1~25 且不重复、
  `watchlist` 不许出现空话、`sources`/`data_gaps` 必须存在。
  它兜住的正是渲染器的静默降级（图整块消失、七步表整列空白、分数造假）。
- 新增 `evals/`：3 个黄金用例（v2 完整、v1 兼容、四类故意错误）+ `run.py`。
  改脚本先跑回归，全绿再提交。
- `lint_encoding.py` 重写：支持 `.md/.html/.json`、接受文件或目录、HTML 先剥标签、
  JSON 只抽中文字符串。此前只 `rglob("*.md")`，传文件进去会静默输出「检查了 0 个文件」，
  等于没有这个工具。
- 新增 `data_gaps` 区块：拿不到的指标显式列出（含它对哪个判断的影响），
  不再让区块自动消失。
- 新增 `meta.price_at`：盘中取价必须写清时刻，PE/PB/分位/PEG/买卖区间全由它推出，
  收盘后按收盘价复核。

### 渲染器缺陷（五处）

1. **轴单位与顶部刻度叠字**：单位画在 `y=pad_t-4`、顶部刻度在 `y=pad_t+4`，
   字号 10/10.5，8px 基线间距必然重叠（显示成「亿1元4.5」）。改为 `pad_t=26` + 单位 `pad_t-12`。
2. **排雷标题分母用错**：原先按「传进来的条数」做分母，只列命中项时显示「命中 4 / 4 项」，
   等于自欺。改为固定 25，并列出命中编号（`#9、#14、#20、#23`）。
3. **图表静默跳过**：`series.values` 混进 `"60.08%"` 这类字符串时 `svg_multi` 返回空，
   代码 `continue` 掉，图整块消失且无任何提示。改为 stderr 告警 + `validate.py` 硬校验。
4. **MD 版七步表整列空白**：`render_md.py` 只读 `state_text` 且无兜底。
   改为按 `state` 兜底映射（pass→通过 / warn→存疑 / fail→否决）。
5. **加权总分重复显示**：「实算值（报告标注值 …）」双份。改为仅在两者不一致时告警。

另外修掉两处：`verdict.tags` 只接受对象、传字符串会直接 `AttributeError` 崩溃（渲染器的
「缺字段不崩溃」承诺没做到）；v1 旧结构下「五、资产负债」与「五、排雷扫描」编号重复。

### v2.1.1 补丁（同日第二轮自检）

- **`value: null`（不可评）全链路支持**：v2.1.0 把「缺项不记 0 分」写进了文档，但代码
  两处 `float(i.get("value"))` 遇 null 直接崩溃，validate 也报错——规则等于不能执行。
  现在：HTML 画灰条「不可评 ×权重」、MD 写「不可评」、validate 从分母剔除并打印
  「可评 13 / 16 项，归一化得分率 67.3%」。新增回归用例 `partial-nulls`（4/4 通过）。
- `data_gaps` 传字符串会被渲染成一串单字列表 → validate 增加类型校验（必须是字符串数组）。
- `periods` 10~15 期原先静默通过 → 现在告警（SKILL 要求 16 期）。
- 打分卡不是 16 项时提示「保留 16 行、缺的写 null」，避免有人直接删行把分母改小。
- 清掉上一版留下的两处空壳：`if price_at: pass`、`len(items) != len([])`。
- **明确只做 A 股**（沪/深/北），删掉港股、美股的支持声明与代码规范。
  指标体系本来就是 A 股口径（扣非、合同负债、商誉），半支持不如明确不支持；
  `validate.py` 增加 `meta.code` 前缀校验（`sh|sz|bj` + 6 位），碰到 `hk`/`us` 直接报错。
- `解读范式.md` 补「次新股分位不能当便宜的证据」，与 §3.5 对齐。

### 文件

- `SKILL.md`：新增第 0 步（报告期/行情时点确认）；JSON 字段表补 `schema_version` /
  `charts_title` / `state_text` / `data_gaps` / `meta.price_at`；`charts[].labels` 由「必须给」
  改为「可省，默认 periods」；交付流程改为「validate → 渲染 → lint」三步全绿。
- `references/指标体系.md`：§13 矩阵化、§3.5 分位口径、§12 只列命中 + 编号规则。
- `references/westock-接口.md`：接口表 15 → 16 项（补 `data_valuation`），期数 8 → 16，
  缺口处理补归一化。
- `scripts/sample.json`：**换成 v2 结构**（真实数据）。上一版仍是 v1（trends/latest/balance），
  照抄样例会整块丢掉「财务全景」章节——这是最后一次结构改动留下的漂移。

## v2.0.0 — 2026-10（上一次提交）

- 财务展示重构：trends / latest / balance 合并为 `financials` 一块，新增单季主表与跨年趋势图。
- 未同步更新 SKILL.md 的字段表与 sample.json，导致 v2.1.0 修的三处漂移。
