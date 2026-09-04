# CNINFO 产业链中心接口报告

API base: `https://pis.cninfo.com.cn/ics/aasKnowledgeBase`

本报告根据已登录 Chrome 会话中实际返回的 JSON 字段整理。报告和样本只保存响应体，不保存 Cookie、Authorization、签名或其他会话凭据。

## 观测结论

- 页面是单页应用（Vue SPA），产业链和企业数据通过 AJAX Fetch/XHR 加载。
- `chaincenter/chainlist/list` 返回产业链目录；`dynamicChainMapNew` 返回节点及 `children` 关系；`industry-info` 返回节点元数据。
- 企业数据有三种可区分证据：年报产品披露、上市公司检索、非上市公司检索。
- 企业接口存在分页；示例节点的非上市企业总数为 71，第一页返回 15 条。

## 接口列表

### 1. `chain_list`

接口 URL: `https://pis.cninfo.com.cn/ics/aasKnowledgeBase/chaincenter/chainlist/list`

请求方法: `POST`

作用: 返回产业链分类和产业链列表

请求参数示例:

```json
{
  "chainId": "ROOT"
}
```

返回结构示例:

```json
{
  "code": 200,
  "data": [
    {
      "chain_menu": "能源",
      "chains": [
        {
          "chain_id": "lsx019",
          "chain_name": "新能源"
        }
      ]
    }
  ]
}
```

### 2. `dynamic_chain_map`

接口 URL: `https://pis.cninfo.com.cn/ics/aasKnowledgeBase/chaincenter/chainlist/dynamicChainMapNew`

请求方法: `POST`

作用: 返回产业链节点森林；节点通过 children 连接

请求参数示例:

```json
{
  "chainId": "lsx019"
}
```

返回结构示例:

```json
{
  "code": 200,
  "data": {
    "tier1": [
      {
        "node_id": "A02n027",
        "node_name": "太阳能电池零部件",
        "children": []
      }
    ]
  }
}
```

### 3. `industry_info`

接口 URL: `https://pis.cninfo.com.cn/ics/aasKnowledgeBase/industry/industry-info`

请求方法: `POST`

作用: 返回产业链节点元数据、层级、上下游和行业编码

请求参数示例:

```json
{
  "chainid": "lsx019"
}
```

返回结构示例:

```json
{
  "code": 200,
  "data": {
    "total": 124,
    "list": [
      {
        "cnode_id": "A02n019",
        "cnode_name": "太阳能EVA胶膜",
        "chain_updown": "上游"
      }
    ]
  }
}
```

### 4. `node_info`

接口 URL: `https://pis.cninfo.com.cn/ics/aasKnowledgeBase/industry/industry-info`

请求方法: `POST`

作用: 返回单个节点的行业编码、说明和来源字段

请求参数示例:

```json
{
  "cnodeid": "A02n019"
}
```

返回结构示例:

```json
{
  "code": 200,
  "data": {
    "total": 1,
    "list": [
      {
        "cnode_id": "A02n019",
        "industry_code": "A02010201"
      }
    ]
  }
}
```

### 5. `chain_stream`

接口 URL: `https://pis.cninfo.com.cn/ics/aasKnowledgeBase/chaincenter/chainlist/chainStream`

请求方法: `POST`

作用: 返回节点在产业链中的上游、当前和下游标签

请求参数示例:

```json
{
  "industryId": "A02010201"
}
```

返回结构示例:

```json
{
  "code": 200,
  "data": {
    "up": [],
    "middle": [],
    "down": []
  }
}
```

### 6. `company_income`

接口 URL: `https://pis.cninfo.com.cn/ics/aasKnowledgeBase/industryDetail/companyIncome`

请求方法: `POST`

作用: 返回年报中披露该行业产品的上市公司及产品字段

请求参数示例:

```json
{
  "industryCode": "A02010201",
  "pageNum": 1,
  "pageSize": 15,
  "industry_flag": true
}
```

返回结构示例:

```json
{
  "code": 200,
  "data": {
    "list": [
      {
        "company_name_one": "杭州福斯特应用材料股份有限公司",
        "seccode_one": "603806"
      }
    ]
  }
}
```

### 7. `listed_companies`

接口 URL: `https://pis.cninfo.com.cn/ics/aasKnowledgeBase/chaincenter/searchOtherListed`

请求方法: `POST`

作用: 返回与节点行业编码关联的上市公司

请求参数示例:

```json
{
  "industry": "A02010201",
  "type": "company",
  "page_num": 1,
  "page_size": 15,
  "industry_flag": true
}
```

返回结构示例:

```json
{
  "code": 200,
  "data": {
    "total": 7,
    "companys": [
      {
        "fullname": "天津久日新材料股份有限公司",
        "stockCode": "688199"
      }
    ]
  }
}
```

### 8. `non_listed_companies`

接口 URL: `https://pis.cninfo.com.cn/ics/aasKnowledgeBase/chaincenter/searchglobalNew`

请求方法: `POST`

作用: 返回与节点行业编码关联的非上市企业；结果分页

请求参数示例:

```json
{
  "industry": "A02010201",
  "type": "company",
  "pageNumber": 1,
  "pageSize": 15,
  "flag": "noListed",
  "industryFlag": true
}
```

返回结构示例:

```json
{
  "code": 200,
  "data": {
    "total": 71,
    "companys": [
      {
        "fullname": "无锡市万力粘合材料股份有限公司"
      }
    ]
  }
}
```

## 本地响应体证据

当前样本目录包含以下响应体文件：

- `capture_manifest.json`
- `chain_lsx019_dynamicChainMapNew.json`
- `chain_lsx019_industry_info.json`
- `chainlist_ROOT.json`
- `node_A02n019_companyIncome.json`
- `node_A02n019_industry_info.json`
- `node_A02n019_searchOtherListed.json`
- `node_A02n019_searchglobalNew.json`
- `node_A02n019_searchglobalNew_page2.json`
- `node_A02n019_searchglobalNew_page3.json`
- `node_A02n019_searchglobalNew_page4.json`
- `node_A02n019_searchglobalNew_page5.json`

## 逐节点采集经验

1. 先调用目录接口拿到 `chain_id`，再调用 `dynamicChainMapNew` 还原 `children`；不要从页面卡片文字反推节点关系。
2. 节点详情同时提供 `cnode_id` 和 `industry_code`。企业查询应使用行业编码；没有行业编码的父节点或组合节点应记录为“无可查询编码”，不能把子节点企业继承上来。
3. `searchOtherListed` 和 `searchglobalNew` 都是分页接口。以返回的 `total` 为准，按 15 条一页核对实际页数和实际行数；不能只抓第一页。
4. `companyIncome` 是年报产品披露证据，`searchOtherListed`/`searchglobalNew` 是行业编码关联企业证据。三者口径不同，合并时按企业编码或名称去重，但要保留 `source_types`。
5. Chrome 登录态适合用来触发接口；路由连续切换时，CDP 的响应体可能在事后不可读取。此时使用页面已经渲染的表格 DOM 作为结构化兜底，并保存 `capture_mode`，同时以页面“总计”与抓到的分页行数做对照。
6. 产业链导出按来源标签投影：`chain_updown`（上游/中游/下游）进入分类1，节点路径从分类2开始；`tier0` 的未分配节点保留原标签。
7. 节点 ID 集合、节点名称/行业编码、分页总数和页面可见总数应至少各做一次交叉核验；单一接口返回成功不等于结果完整。

## 对照验证口径

- 结构对照：`dynamicChainMapNew` 递归节点集合与 `industry-info` 节点集合应一致。
- 节点对照：每个采集文件的 `node_id`、节点名称、行业编码和上下游标签与链路元数据逐项比较。
- 分页对照：每个节点分别比较声明的 `total`、页数和各页实际行数。
- 页面对照：抽样节点读取 Chrome 可见表格的“总计”数字，与接口/采集汇总并列；若不一致，保留差异，不强行合并为一个数字。

当前新能源页面对照样本：

- 样本数：4；API total 与页面可见总数一致：4。
- 对照解释：样本支持接口 total 与页面企业列表总计一致，但不能据此推断所有节点都已验证或企业集合完整。
- 页面企业列表、年报产品披露和行业编码检索的统计口径不同，不能把三者直接相加作为企业总数。

报告生成时间：2026-09-03T09:46:46.743148+00:00
