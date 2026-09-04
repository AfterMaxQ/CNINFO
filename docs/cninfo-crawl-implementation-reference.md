# CNINFO 产业链网站爬取详细实现参考

## 1. 文档目的

本文是给开发人员的实现参考，说明如何从
[CNINFO 产业分析系统](https://pis.cninfo.com.cn/ics/index.html#/chainCenter?all_menu)
获取：

1. 全部产业链主题；
2. 每个主题的产业链节点树；
3. 每个节点自身的行业编码和企业列表；
4. 页面节点到九字段业务行的映射。

本文只描述已经在 Chrome 登录会话中观察到的接口和响应，不保存浏览器凭据。下面的真实响应片段来自本地响应体样本，采集时间为 2026-09-03；CNINFO 接口字段和数据数量可能随网站更新变化，正式运行前要重新做一次接口健康检查。

已有完整接口摘要见 [`api_report.md`](../api_report.md)，真实响应体见 [`data/raw/`](../data/raw/)。

## 2. 网站架构

### 2.1 页面技术形态

- 前端：Vue 风格的单页应用（SPA）。地址栏使用 hash 路由，例如：

  ```text
  https://pis.cninfo.com.cn/ics/index.html#/industryChain/A02n019/lsx019/A02n019/太阳能EVA胶膜
  ```

- 数据加载：页面通过 Fetch/XHR 异步请求 JSON，HTML 不是产业链数据的主来源。
- 接口基地址：

  ```text
  https://pis.cninfo.com.cn/ics/aasKnowledgeBase
  ```

- 认证：需要使用已经登录的浏览器会话。当前探索中观察到请求头模板包含 `Accept`、`Content-Type`、`token`、`sign` 等字段，但它们只应留在浏览器页面内存中，不能写入 raw、日志、代码仓库或 Excel。

### 2.2 推荐数据流

```text
根目录
  ↓ chainlist/list
主题与 chain_id
  ↓ dynamicChainMapNew
节点森林、children、上/中/下游分区
  ↓ industry-info(chainid)
节点元数据和 industry_code
  ↓ 每个节点点击一次 / 直接回放该节点请求
节点详情、年报披露、上市企业、非上市企业
  ↓ 分页和字段校验
节点级规范化企业集合
  ↓ 路径投影
九字段业务行
```

### 2.3 “点一次”的实际含义

采集范围以主题页面 `dynamicChainMapNew` 返回的节点集合为边界：

- 每个返回的节点最多点击/请求一次，获取该节点自己的企业数据；
- 节点的 `children` 只用于还原路径，不把页面中额外展示的行业上下游推荐无限递归成新节点；
- 父节点和子节点都是独立节点：父节点有自己的 `industry_code` 时查询父节点企业，子节点再查询子节点企业；
- 一个节点的企业请求完成所有分页后再生成该节点的一行，不能每家公司拆一行。

## 3. 页面分区到分类字段的规则

页面实际有四种业务分区：`其他`、`上游`、`中游`、`下游`。业务输出规则如下：

| 页面分区 | 分类1 | 分类2 起始内容 |
| --- | --- | --- |
| 其他 | `其他` | 该分区下的节点，例如 `焊带` |
| 上游 | `上游` | 上游分组或节点路径 |
| 中游 | `中游` | 中游分组或节点路径 |
| 下游 | `下游` | 下游分组或节点路径 |

当前真实响应中，页面底部的“其他”节点表现为 `tier0`，节点字段为 `chain_up_down: "未分配节点"`。因此建议保存两套值：

- 业务值：专门的“其他”分区映射为 `其他`；
- 原始值：sidecar 中保留 `source_group: "tier0"` 和 `chain_up_down: "未分配节点"`。

只有在节点确实来自页面的“其他”分区时才这样映射。如果将来接口返回了未知标签，不能把所有未知值默认为“其他”，应记录结构差异并暂停该节点。

### 3.1 真实路径示例

当前 `新能源` 动态地图中有以下真实关系：

```text
其他
└── 焊带

上游
└── 太阳能电池零部件
    ├── 太阳能EVA胶膜
    ├── 光伏玻璃
    └── 太阳能电池片

中游
└── 太阳能生产设备
    └── 电池片生产设备
```

对应九字段的分类部分：

```text
其他 | 焊带 |       |
上游 | 太阳能电池零部件 |       |
上游 | 太阳能电池零部件 | 光伏玻璃 |
中游 | 太阳能生产设备 | 电池片生产设备 |
```

分类字段必须连续：

- `分类1` 是分区标签；
- 节点路径从 `分类2` 开始；
- 超过四级时，`分类4` 按原顺序用 ` > ` 合并；
- 不补行业知识，不改节点原名。

## 4. 已验证接口

### 4.1 获取全部主题目录：`chainlist/list`

```text
POST https://pis.cninfo.com.cn/ics/aasKnowledgeBase/chaincenter/chainlist/list
```

请求体当前观察为 form：

```text
chainId=ROOT
```

也可以在浏览器 Network 中看到等价的结构化参数：

```json
{
  "chainId": "ROOT"
}
```

真实响应节选：

```json
{
  "code": 200,
  "msg": "请求成功",
  "data": [
    {
      "chain_menu": "能源",
      "chains": [
        {
          "path": "https://dataclouds.cninfo.com.cn/icsp/system/chain-pic/新能源.png",
          "chainPictureId": 61,
          "chain_id": "lsx019",
          "chain_menu": "能源",
          "chain_name": "新能源",
          "ratio": 0.2
        },
        {
          "chain_id": "yl001",
          "chain_menu": "能源",
          "chain_name": "石油天然气"
        }
      ]
    }
  ],
  "ok": true
}
```

当前样本返回 17 个目录分类、134 条产业链。实现时不要按主题名称猜 ID，必须保存接口返回的 `chain_id`。

### 4.2 获取主题节点树：`dynamicChainMapNew`

```text
POST https://pis.cninfo.com.cn/ics/aasKnowledgeBase/chaincenter/chainlist/dynamicChainMapNew
```

请求体：

```text
chainId=lsx019
```

真实响应节选：

```json
{
  "code": 200,
  "data": {
    "tier0": [
      {
        "node_id": "AUC0000051",
        "node_name": "焊带",
        "node_floor": "0",
        "cnode_link": "",
        "chain_up_down": "未分配节点",
        "chain_type": null,
        "children": [],
        "tier_num": 0
      }
    ],
    "tier1": [
      {
        "node_id": "A02n027",
        "node_name": "太阳能电池零部件",
        "node_floor": "1",
        "chain_up_down": "上游",
        "children": [
          {
            "node_id": "A02n019",
            "node_name": "太阳能EVA胶膜",
            "node_floor": "2",
            "node_pid": "A02n027",
            "chain_up_down": "上游",
            "chain_type": "主",
            "children": []
          },
          {
            "node_id": "A02n020",
            "node_name": "光伏玻璃",
            "node_floor": "2",
            "node_pid": "A02n027",
            "chain_up_down": "上游",
            "chain_type": "主",
            "children": []
          }
        ]
      }
    ]
  },
  "ok": true
}
```

关键点：

- `tier0`、`tier1`、`tier2`、`tier3` 是来源分组，不等同于业务分类1；
- 真正的树关系在 `children`；
- `node_pid` 可作为辅助父节点证据，但以父节点的 `children` 关系为主；
- `node_name`、`node_id`、顺序和空节点都要保留。

### 4.3 获取主题节点元数据：`industry-info`

#### 主题级请求

```text
POST https://pis.cninfo.com.cn/ics/aasKnowledgeBase/industry/industry-info
```

请求体：

```text
chainid=lsx019
```

真实响应节选：

```json
{
  "code": 200,
  "data": {
    "total": 124,
    "list": [
      {
        "chain_id": "lsx019",
        "chain_name": "新能源",
        "chain_tier": "1",
        "node_floor": "2",
        "cnode_id": "A02n019",
        "cnode_name": "太阳能EVA胶膜",
        "industry_code": "A02010201",
        "industry_name": "太阳能EVA胶膜",
        "parent_code": "",
        "parent_name": "",
        "chain_updown": "上游",
        "chain_type": "主"
      },
      {
        "cnode_id": "A02n020",
        "cnode_name": "光伏玻璃",
        "industry_code": "A02010202",
        "chain_updown": "上游"
      }
    ]
  },
  "ok": true
}
```

#### 单节点请求

```text
POST https://pis.cninfo.com.cn/ics/aasKnowledgeBase/industry/industry-info
```

请求体：

```text
cnodeid=A02n019
```

真实返回的关键字段：

```json
{
  "code": 200,
  "data": {
    "total": 1,
    "list": [
      {
        "cnode_id": "A02n019",
        "cnode_name": "太阳能EVA胶膜",
        "industry_code": "A02010201",
        "industry_name": "太阳能EVA胶膜",
        "chain_updown": "上游",
        "node_floor": "2"
      }
    ]
  },
  "ok": true
}
```

采集规则：

- 优先使用主题级 `industry-info` 建立节点元数据索引；
- 单节点请求用于页面点击验证、元数据缺失补查或异常节点复核；
- `industry_code` 为空时保留节点，但不向企业接口发送空行业编码。

### 4.4 年报产品披露企业：`companyIncome`

```text
POST https://pis.cninfo.com.cn/ics/aasKnowledgeBase/industryDetail/companyIncome
```

请求体为 JSON：

```json
{
  "industryCode": "A02010201",
  "pageNum": 1,
  "pageSize": 15,
  "industry_flag": true
}
```

真实响应节选：

```json
{
  "code": 200,
  "data": {
    "list": [
      {
        "company_name_one": "杭州福斯特应用材料股份有限公司",
        "company_name_two": "杭州福斯特应用材料股份有限公司",
        "secname_one": "福斯特",
        "seccode_one": "603806",
        "product_name_one": "光伏胶膜",
        "industry_code": "A02010201",
        "industry_name": "太阳能EVA胶膜",
        "product_income_one": "139.63",
        "is_listed": true
      },
      {
        "company_name_one": "深圳市燃气集团股份有限公司",
        "secname_one": "深圳燃气",
        "seccode_one": "601139",
        "product_name_one": "光伏胶膜",
        "industry_code": "A02010201",
        "is_listed": true
      }
    ]
  },
  "ok": true
}
```

当前 EVA 样本的年报产品披露返回 9 条。该接口适合作为“企业在年报中披露该行业产品”的证据，不等同于上市检索总数。

### 4.5 上市公司检索：`searchOtherListed`

```text
POST https://pis.cninfo.com.cn/ics/aasKnowledgeBase/chaincenter/searchOtherListed
```

请求体为 JSON：

```json
{
  "industry": "A02010201",
  "type": "company",
  "page_num": 1,
  "page_size": 15,
  "industry_flag": true
}
```

真实响应节选：

```json
{
  "code": 200,
  "data": {
    "total": 7,
    "companys": [
      {
        "companyShortName": "久日新材",
        "stockCode": "688199",
        "fullname": "天津久日新材料股份有限公司",
        "industryCode": ["A02010201"],
        "industry": ["太阳能EVA胶膜"],
        "isListed": true
      },
      {
        "companyShortName": "天洋新材",
        "stockCode": "603330",
        "fullname": "天洋新材（上海）科技股份有限公司",
        "industryCode": ["A02010201"],
        "industry": ["太阳能EVA胶膜"],
        "isListed": true
      }
    ]
  },
  "ok": true
}
```

### 4.6 非上市/全球企业检索：`searchglobalNew`

```text
POST https://pis.cninfo.com.cn/ics/aasKnowledgeBase/chaincenter/searchglobalNew
```

当前观察请求为 form：

```text
industry=A02010201&type=company&pageNumber=1&pageSize=15&flag=noListed&industryFlag=true
```

等价参数表示：

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

真实响应节选：

```json
{
  "code": 200,
  "data": {
    "total": 71,
    "companys": [
      {
        "fullname": "无锡市万力粘合材料股份有限公司",
        "company_id": 141143,
        "industryCode": ["A02010201"],
        "industry": ["太阳能EVA胶膜", "热熔胶"],
        "isListed": false,
        "province": "江苏",
        "city": "无锡市"
      },
      {
        "fullname": "上海宇昂水性新材料科技股份有限公司",
        "company_id": 96961,
        "industryCode": ["A02010201"],
        "industry": ["太阳能EVA胶膜"],
        "isListed": false
      }
    ]
  },
  "ok": true
}
```

第一页 15 条时，EVA 样本的 `total=71`，需要抓取 5 页：15、15、15、15、11。

## 5. 代码级采集示例

### 5.1 浏览器内请求适配器

认证头必须由当前已登录页面的请求上下文提供。下面示例只展示请求形态，`headers_in_memory` 代表页面内存中的当前请求头模板，不能从浏览器导出到文件：

```javascript
const API = "/ics/aasKnowledgeBase";

async function postJson(path, body, headers_in_memory) {
  const response = await fetch(API + path, {
    method: "POST",
    headers: {
      ...headers_in_memory,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });
  const payload = await response.json();
  if (!response.ok || payload.code !== 200) {
    throw new Error(`${path}: HTTP ${response.status}, code ${payload.code}`);
  }
  return payload;
}

async function postForm(path, params, headers_in_memory) {
  const response = await fetch(API + path, {
    method: "POST",
    headers: {
      ...headers_in_memory,
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    },
    body: new URLSearchParams(params)
  });
  const payload = await response.json();
  if (!response.ok || payload.code !== 200) {
    throw new Error(`${path}: HTTP ${response.status}, code ${payload.code}`);
  }
  return payload;
}
```

实际运行时，若页面应用使用自己的请求封装，应优先复用该封装；若通过页面内 XHR 回放，应为每个请求设置超时，并在认证失效时暂停任务。不要把 `headers_in_memory`、请求拦截器内容或响应中的隐含认证字段写入 capture。

### 5.2 主题和节点遍历

```python
from collections.abc import Iterator


def iter_nodes(nodes: list[dict], path: tuple[str, ...] = ()) -> Iterator[tuple[dict, tuple[str, ...]]]:
    """按 dynamicChainMapNew 的来源顺序输出每个节点和完整路径。"""
    for node in nodes:
        current_path = path + (node["node_name"],)
        yield node, current_path
        yield from iter_nodes(node.get("children", []), current_path)


def page_classification(node: dict, path: tuple[str, ...]) -> list[str]:
    """分类1使用页面分区，路径从分类2开始。"""
    raw_zone = node.get("chain_up_down", "")
    source_group = node.get("source_group", "")

    if source_group == "tier0" and raw_zone == "未分配节点":
        direction = "其他"
    elif raw_zone in {"上游", "中游", "下游"}:
        direction = raw_zone
    else:
        raise ValueError(f"unknown chain zone: {source_group=} {raw_zone=}")

    return [
        direction,
        path[0] if len(path) >= 1 else "",
        path[1] if len(path) >= 2 else "",
        " > ".join(path[2:]) if len(path) >= 3 else "",
    ]
```

注意：生产代码不能只依赖 `source_group == "tier0"`，应同时保留页面分区的原始字段；上面的判断是当前真实样本的映射演示。

### 5.3 以 `total` 驱动分页

下面是非上市企业接口的分页逻辑。上市接口只需要把页码字段换成 `page_num`，年报接口使用 `pageNum`；不要写死“抓 5 页”：

```python
from math import ceil
from typing import Callable


def collect_pages(
    post_form: Callable[[dict], dict],
    industry_code: str,
    page_size: int = 15,
) -> list[dict]:
    if not industry_code:
        return []
    if page_size <= 0:
        raise ValueError("page_size must be positive")

    def request(page: int) -> dict:
        return post_form({
            "industry": industry_code,
            "type": "company",
            "pageNumber": page,
            "pageSize": page_size,
            "flag": "noListed",
            "industryFlag": "true",
        })

    first = request(1)
    data = first.get("data", {})
    total = int(data.get("total", 0) or 0)
    pages = ceil(total / page_size) if total else 0
    # 即使 total=0，也保留首个响应作为节点审计证据。
    results = [first]

    for page in range(2, pages + 1):
        results.append(request(page))

    captured = sum(len(item.get("data", {}).get("companys", [])) for item in results)
    if captured != total:
        raise RuntimeError(
            f"pagination mismatch: code={industry_code}, total={total}, captured={captured}"
        )
    return results
```

实际实现还要记录：接口、请求页码、声明 `total`、实际行数、重试次数、响应时间和错误信息。

### 5.4 企业规范化与去重

三类接口的统计口径不同，但业务行的公司字段需要一个去重后的企业名称集合。建议保留 sidecar 证据，再投影公司名称：

```python
def add_company(store: dict[str, dict], row: dict, source_type: str, listed: bool) -> None:
    name = str(row.get("fullname") or row.get("company_name_one") or "").strip()
    code = str(row.get("stockCode") or row.get("seccode_one") or row.get("company_id") or "").strip()
    if not name:
        return

    # 有代码时以代码去重；没有代码时保留原始名称并用去空白名称去重。
    key = f"code:{code}" if code else f"name:{''.join(name.split())}"
    item = store.setdefault(key, {
        "name": name,
        "code": code,
        "listed": listed,
        "source_types": [],
    })
    item["listed"] = item["listed"] or listed
    if source_type not in item["source_types"]:
        item["source_types"].append(source_type)


def company_cell(companies: list[dict]) -> str:
    return "、".join(item["name"] for item in companies)
```

不要把股票代码拼入九字段的“公司”列；代码、上市状态、来源接口和产品字段放在 sidecar 中，业务表只保存企业实体名称。

## 6. 一个真实节点的完整演示：太阳能EVA胶膜

节点页面地址：

```text
https://pis.cninfo.com.cn/ics/index.html#/industryChain/A02n019/lsx019/A02n019/太阳能EVA胶膜
```

### 6.1 请求顺序

```text
1. chainlist/list              chainId=ROOT
2. dynamicChainMapNew         chainId=lsx019
3. industry-info              chainid=lsx019
4. industry-info              cnodeid=A02n019
5. companyIncome              industryCode=A02010201
6. searchOtherListed          industry=A02010201
7. searchglobalNew             industry=A02010201, pageNumber=1..5
```

### 6.2 实际数量

| 来源接口 | 返回数量 | 解释 |
| --- | ---: | --- |
| `companyIncome` | 9 | 年报产品披露企业 |
| `searchOtherListed` | 7 | 上市公司行业检索 |
| `searchglobalNew` | 71 | 非上市企业检索，5 页 |

本地样本经代码/名称去重后，`data/processed/company_A02n019.json` 的摘要为：

```json
{
  "node_id": "A02n019",
  "node": "太阳能EVA胶膜",
  "industry_code": "A02010201",
  "counts": {
    "unique": 86,
    "listed": 15,
    "non_listed": 71
  },
  "source_types": [
    "annual_report_product",
    "listed_search",
    "non_listed_search"
  ]
}
```

这里的 86 是去重后的联合集合，不是 9+7+71 的直接相加结果；年报披露和上市检索之间存在企业重叠。

### 6.3 业务行演示

该节点的来源路径为：

```text
上游 > 太阳能电池零部件 > 太阳能EVA胶膜
```

对应业务行：

```text
主题	信源主体	分类1	分类2	分类3	分类4	公司	信源URL	备注
新能源	CNINFO产业分析系统	上游	太阳能电池零部件	太阳能EVA胶膜		杭州福斯特应用材料股份有限公司、深圳市燃气集团股份有限公司、…	https://pis.cninfo.com.cn/ics/index.html#/industryChain/A02n019/lsx019/A02n019/太阳能EVA胶膜	来自CNINFO产业链中心结构化数据
```

上面公司列中的省略号只是文档展示用，实际导出必须写入完整的去重企业名称集合；不要把 `…` 作为企业名称写入数据。

## 7. 页面/API 对照演示

当前通过 Chrome 页面可见 DOM 的“总计”与接口响应的 `data.total` 做了结构化对照，未使用截图或 OCR：

| 节点 | industry_code | 页面上市/非上市总计 | API `total` | 结果 |
| --- | --- | --- | --- | --- |
| 太阳能EVA胶膜 | A02010201 | 7 / 71 | 7 / 71 | 一致 |
| 光伏玻璃 | A02010202 | 9 / 197 | 9 / 197 | 一致 |
| 电池片生产设备 | A02010301 | 20 / 165 | 20 / 165 | 一致 |
| 太阳能电池零部件 | 无编码 | 0 / 0 | 不发送空编码查询 | 符合规则 |

对照文件：[`data/processed/newenergy_ui_comparison.json`](../data/processed/newenergy_ui_comparison.json)。

这个对照只能证明当前接口统计口径和页面列表数量一致，不能证明行业编码关联企业是完整的上下游供销关系。

## 8. 推荐的最小采集脚本职责

现有探索脚本已经分别承担以下职责：

| 文件 | 职责 |
| --- | --- |
| [`scripts/discover_api.py`](../scripts/discover_api.py) | 输出接口清单、响应结构和探索经验 |
| [`scripts/fetch_chain.py`](../scripts/fetch_chain.py) | 将目录、动态地图和 `industry-info` 规范化为保留来源顺序的树 |
| [`scripts/fetch_company.py`](../scripts/fetch_company.py) | 合并企业接口响应、去重并输出九字段 XLSX |
| [`scripts/validate_newenergy.py`](../scripts/validate_newenergy.py) | 校验节点文件、元数据和分页声明 |

正式全站运行时，外层只需要增加一个主题/节点遍历入口，核心逻辑仍应保持以上职责分离：

```text
浏览器接口桥接
  → raw/<chain_id>/<node_id>/*.json
  → fetch_chain 生成 node/path
  → fetch_company 生成 node-company sidecar
  → 九字段行生成器
  → Excel 物化器
```

不要把页面的行业资讯、产业政策、产业营收、热点趋势等模块误当成节点企业接口；它们可以作为后续数据联动来源，但不属于本次“节点一次点击、获取该节点企业”的核心链路。

## 9. 运行时保护

1. API 返回非 `200` 或 `ok=false` 时，保留原始响应并标记失败，不生成空企业结果。
2. 请求必须有超时；单个大结果节点超时不能阻塞整个主题。
3. 使用 `total` 计算页数，检查实际行数；不能只保存第一页。
4. 空 `industry_code` 节点保留节点业务行，公司留空，不请求企业接口。
5. 原始响应只保存 JSON；不保存浏览器 headers、Cookie、Local Storage、token、sign 或密码。
6. 公司名称按接口原值保存；不能通过外部知识把简称补成工商全称。
7. 页面 DOM 对照只记录“总计”数字和页面节点名，不用 OCR 作为主采集方式。
8. 主题、节点和企业数量会变化；每次正式运行都必须保存运行时间、接口响应、页码和验证结果。
