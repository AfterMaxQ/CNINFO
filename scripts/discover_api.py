"""Generate the API inventory for the CNINFO chain-center experiment.

The inventory is based on response bodies observed in a signed-in Chrome
session.  It intentionally does not contain cookies, authorization headers,
or other session material.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


API_BASE = "https://pis.cninfo.com.cn/ics/aasKnowledgeBase"

APIS = [
    {
        "name": "chain_list",
        "method": "POST",
        "path": "/chaincenter/chainlist/list",
        "params": {"chainId": "ROOT"},
        "purpose": "返回产业链分类和产业链列表",
        "response": {
            "code": 200,
            "data": [{"chain_menu": "能源", "chains": [{"chain_id": "lsx019", "chain_name": "新能源"}]}],
        },
    },
    {
        "name": "dynamic_chain_map",
        "method": "POST",
        "path": "/chaincenter/chainlist/dynamicChainMapNew",
        "params": {"chainId": "lsx019"},
        "purpose": "返回产业链节点森林；节点通过 children 连接",
        "response": {
            "code": 200,
            "data": {"tier1": [{"node_id": "A02n027", "node_name": "太阳能电池零部件", "children": []}]},
        },
    },
    {
        "name": "industry_info",
        "method": "POST",
        "path": "/industry/industry-info",
        "params": {"chainid": "lsx019"},
        "purpose": "返回产业链节点元数据、层级、上下游和行业编码",
        "response": {
            "code": 200,
            "data": {"total": 124, "list": [{"cnode_id": "A02n019", "cnode_name": "太阳能EVA胶膜", "chain_updown": "上游"}]},
        },
    },
    {
        "name": "node_info",
        "method": "POST",
        "path": "/industry/industry-info",
        "params": {"cnodeid": "A02n019"},
        "purpose": "返回单个节点的行业编码、说明和来源字段",
        "response": {
            "code": 200,
            "data": {"total": 1, "list": [{"cnode_id": "A02n019", "industry_code": "A02010201"}]},
        },
    },
    {
        "name": "chain_stream",
        "method": "POST",
        "path": "/chaincenter/chainlist/chainStream",
        "params": {"industryId": "A02010201"},
        "purpose": "返回节点在产业链中的上游、当前和下游标签",
        "response": {"code": 200, "data": {"up": [], "middle": [], "down": []}},
    },
    {
        "name": "company_income",
        "method": "POST",
        "path": "/industryDetail/companyIncome",
        "params": {
            "industryCode": "A02010201",
            "pageNum": 1,
            "pageSize": 15,
            "industry_flag": True,
        },
        "purpose": "返回年报中披露该行业产品的上市公司及产品字段",
        "response": {
            "code": 200,
            "data": {"list": [{"company_name_one": "杭州福斯特应用材料股份有限公司", "seccode_one": "603806"}]},
        },
    },
    {
        "name": "listed_companies",
        "method": "POST",
        "path": "/chaincenter/searchOtherListed",
        "params": {
            "industry": "A02010201",
            "type": "company",
            "page_num": 1,
            "page_size": 15,
            "industry_flag": True,
        },
        "purpose": "返回与节点行业编码关联的上市公司",
        "response": {"code": 200, "data": {"total": 7, "companys": [{"fullname": "天津久日新材料股份有限公司", "stockCode": "688199"}]}},
    },
    {
        "name": "non_listed_companies",
        "method": "POST",
        "path": "/chaincenter/searchglobalNew",
        "params": {
            "industry": "A02010201",
            "type": "company",
            "pageNumber": 1,
            "pageSize": 15,
            "flag": "noListed",
            "industryFlag": True,
        },
        "purpose": "返回与节点行业编码关联的非上市企业；结果分页",
        "response": {"code": 200, "data": {"total": 71, "companys": [{"fullname": "无锡市万力粘合材料股份有限公司"}]}},
    },
]


def build_report(raw_dir: Path) -> str:
    lines = [
        "# CNINFO 产业链中心接口报告",
        "",
        f"API base: `{API_BASE}`",
        "",
        "本报告根据已登录 Chrome 会话中实际返回的 JSON 字段整理。报告和样本只保存响应体，不保存 Cookie、Authorization、签名或其他会话凭据。",
        "",
        "## 观测结论",
        "",
        "- 页面是单页应用（Vue SPA），产业链和企业数据通过 AJAX Fetch/XHR 加载。",
        "- `chaincenter/chainlist/list` 返回产业链目录；`dynamicChainMapNew` 返回节点及 `children` 关系；`industry-info` 返回节点元数据。",
        "- 企业数据有三种可区分证据：年报产品披露、上市公司检索、非上市公司检索。",
        "- 企业接口存在分页；示例节点的非上市企业总数为 71，第一页返回 15 条。",
        "",
        "## 接口列表",
        "",
    ]
    for index, api in enumerate(APIS, start=1):
        url = API_BASE + api["path"]
        lines.extend(
            [
                f"### {index}. `{api['name']}`",
                "",
                f"接口 URL: `{url}`",
                "",
                f"请求方法: `{api['method']}`",
                "",
                f"作用: {api['purpose']}",
                "",
                "请求参数示例:",
                "",
                "```json",
                json.dumps(api["params"], ensure_ascii=False, indent=2),
                "```",
                "",
                "返回结构示例:",
                "",
                "```json",
                json.dumps(api["response"], ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )

    raw_files = sorted(p.name for p in raw_dir.glob("*.json")) if raw_dir.exists() else []
    lines.extend(
        [
            "## 本地响应体证据",
            "",
            "当前样本目录包含以下响应体文件：",
            "",
        ]
    )
    lines.extend(f"- `{name}`" for name in raw_files)
    lines.extend(
        [
            "",
            "## 逐节点采集经验",
            "",
            "1. 先调用目录接口拿到 `chain_id`，再调用 `dynamicChainMapNew` 还原 `children`；不要从页面卡片文字反推节点关系。",
            "2. 节点详情同时提供 `cnode_id` 和 `industry_code`。企业查询应使用行业编码；没有行业编码的父节点或组合节点应记录为“无可查询编码”，不能把子节点企业继承上来。",
            "3. `searchOtherListed` 和 `searchglobalNew` 都是分页接口。以返回的 `total` 为准，按 15 条一页核对实际页数和实际行数；不能只抓第一页。",
            "4. `companyIncome` 是年报产品披露证据，`searchOtherListed`/`searchglobalNew` 是行业编码关联企业证据。三者口径不同，合并时按企业编码或名称去重，但要保留 `source_types`。",
            "5. Chrome 登录态适合用来触发接口；路由连续切换时，CDP 的响应体可能在事后不可读取。此时使用页面已经渲染的表格 DOM 作为结构化兜底，并保存 `capture_mode`，同时以页面“总计”与抓到的分页行数做对照。",
            "6. 产业链导出按来源标签投影：`chain_updown`（上游/中游/下游）进入分类1，节点路径从分类2开始；`tier0` 的未分配节点保留原标签。",
            "7. 节点 ID 集合、节点名称/行业编码、分页总数和页面可见总数应至少各做一次交叉核验；单一接口返回成功不等于结果完整。",
            "",
            "## 对照验证口径",
            "",
            "- 结构对照：`dynamicChainMapNew` 递归节点集合与 `industry-info` 节点集合应一致。",
            "- 节点对照：每个采集文件的 `node_id`、节点名称、行业编码和上下游标签与链路元数据逐项比较。",
            "- 分页对照：每个节点分别比较声明的 `total`、页数和各页实际行数。",
            "- 页面对照：抽样节点读取 Chrome 可见表格的“总计”数字，与接口/采集汇总并列；若不一致，保留差异，不强行合并为一个数字。",
        ]
    )
    validation_path = raw_dir.parent / "processed" / "newenergy_validation.json"
    if validation_path.exists():
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        comparison = validation.get("comparison", {})
        lines.extend(
            [
                "",
                "当前新能源对照结果：",
                "",
                f"- 预期节点：{comparison.get('expected_nodes', 0)}；采集文件：{comparison.get('capture_files', 0)}；缺失节点：{len(comparison.get('missing_nodes', []))}。",
                f"- 元数据不一致：{len(comparison.get('metadata_mismatches', []))}；分页不一致：{len(comparison.get('pagination_failures', []))}。",
                f"- 对照结论：{'通过' if comparison.get('pass') else '未通过，需按报告中的差异逐项复核'}。",
            ]
        )
    ui_comparison_path = raw_dir.parent / "processed" / "newenergy_ui_comparison.json"
    if ui_comparison_path.exists():
        ui_comparison = json.loads(ui_comparison_path.read_text(encoding="utf-8"))
        summary = ui_comparison.get("summary", {})
        lines.extend(
            [
                "",
                "当前新能源页面对照样本：",
                "",
                f"- 样本数：{summary.get('sample_count', 0)}；API total 与页面可见总数一致：{summary.get('passed_count', 0)}。",
                f"- 对照解释：{summary.get('interpretation', '')}",
                "- 页面企业列表、年报产品披露和行业编码检索的统计口径不同，不能把三者直接相加作为企业总数。",
            ]
        )
    lines.extend(["", f"报告生成时间：{datetime.now(timezone.utc).isoformat()}", ""])
    return "\n".join(lines)


def main() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=project_dir / "api_report.md")
    parser.add_argument("--raw-dir", type=Path, default=project_dir / "data" / "raw")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_report(args.raw_dir), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
