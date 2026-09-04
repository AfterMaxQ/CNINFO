# CNINFO 产业链中心探索

本目录验证 CNINFO 产业分析系统能否提供产业链结构和节点企业的结构化数据，并将结果投影为业务所需的九字段 XLSX。

## 当前结论

CNINFO 可以作为产业链 Tree 的高置信度骨架来源：产业链目录、节点 `children` 关系、节点层级和行业编码均由 JSON 接口返回；企业可通过节点行业编码从上市公司年报披露、上市公司检索和非上市公司检索接口取得。

当前 Chrome 实测样本为“新能源”产业链：目录接口返回 17 个分类、134 条产业链；“新能源”节点图返回 124 个节点。节点“太阳能EVA胶膜”对应行业编码 `A02010201`，实测返回 9 条年报产品披露、7 条上市公司检索结果和 71 条非上市企业检索结果。

## 数据获取方式

页面是 Vue 单页应用（SPA），数据通过 AJAX Fetch/XHR 加载。接口基地址为：

`https://pis.cninfo.com.cn/ics/aasKnowledgeBase`

主要接口：

- `POST /chaincenter/chainlist/list`：通过 `chainId=ROOT` 获取产业链分类和产业链名称、`chain_id`。
- `POST /chaincenter/chainlist/dynamicChainMapNew`：通过 `chainId` 获取产业链节点森林；节点关系在 `children` 中。
- `POST /industry/industry-info`：通过 `chainid` 获取整条产业链节点元数据，或通过 `cnodeid` 获取单节点元数据。
- `POST /industryDetail/companyIncome`：通过 `industryCode` 获取年报产品披露的上市公司。
- `POST /chaincenter/searchOtherListed`：通过 `industry` 行业编码获取上市公司。
- `POST /chaincenter/searchglobalNew`：通过 `industry` 行业编码和 `flag=noListed` 获取非上市企业；接口分页。

接口字段、参数和 JSON 示例见 [api_report.md](api_report.md)。响应体样本在 `data/raw/`，不包含浏览器凭据。

## 运行

脚本处理从已登录 Chrome 会话捕获的 JSON 响应体。由于登录态属于浏览器会话，样本采集使用 Chrome；脚本本身不读取 Cookie、Local Storage 或密码，也不把认证信息写入项目。

```text
python scripts/discover_api.py
python scripts/fetch_chain.py --chain-id lsx019
python scripts/fetch_company.py --node-id A02n019 --industry-code A02010201
```

输出：

- `api_report.md`：接口清单和返回结构。
- `data/processed/chain_lsx019.json`：保留来源分组、节点顺序、节点层级和 `children` 的规范化链路。
- `data/processed/company_A02n019.json`：去重后的节点企业和企业证据类型。
- `export/result.xlsx`：九个业务列，信源 URL 已生成超链接。

## 九字段映射

| 业务字段 | CNINFO 映射 |
| --- | --- |
| 主题 | 产业链名称 |
| 信源主体 | `CNINFO产业分析系统` |
| 分类1-4 | `分类1` 填来源的上游/中游/下游标签；节点路径从 `分类2` 开始，第四级及更深层级按 ` > ` 合并 |
| 公司 | 直接由当前节点企业接口返回的企业实体名称，去重后以顿号连接 |
| 信源URL | 产生当前样本证据的 CNINFO 节点 URL |
| 备注 | 仅来源组首行填写“来自CNINFO产业链中心结构化数据” |

导出表只包含九个业务列；父节点和无企业节点保留为独立行，不把企业拆成“一家一行”。

## 数据质量评价

优点：

- 节点关系是 JSON 中的 `children`，不需要视觉识别或 LLM 建树。
- 节点有稳定的 `cnode_id`、行业编码、上下游方向和层级字段。
- 企业结果有上市、非上市、年报产品披露三类接口，可区分企业证据强弱。
- 产业链目录能直接返回主题和 `chain_id`，适合先选主题再展开节点。

限制：

- 节点图是森林，样本中存在 `tier0` 的“未分配节点”；不能擅自把它们挂到其他节点。
- 企业检索是分页接口，当前脚本处理已捕获的响应页；正式采集必须按 `total` 循环分页并记录页码。
- 行业编码关联企业不等于完整的上下游供销关系；年报产品披露的证据强度高于宽口径行业标签。
- 接口结果可能随 CNINFO 数据更新而变化，下一步需要在 5 个不同主题上做可重复性验证。

## 与现有方案比较

方案 A（搜索网页/PDF/研报 + LLM 建树）覆盖面和解释能力更强，适合 CNINFO 没有覆盖的主题、非标准节点、海外企业、细粒度供销关系和需要外部来源引用的场景，但成本高，且树结构和企业挂载需要人工审核。

方案 B（CNINFO 结构化采集）适合有现成产业链目录、需要稳定节点骨架和候选企业集合的主题。推荐先用 CNINFO 生成骨架和候选公司，再用 Agent 补充未分配节点、关系证据和 CNINFO 未覆盖的企业，最后进入 HITL 审核。

当前证据支持“CNINFO 可作为结构化骨架来源”，尚不足以证明它覆盖任意主题，也不足以替代所有外部证据。
