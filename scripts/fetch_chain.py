"""Normalize captured CNINFO chain responses into a source-preserving tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CNINFO_BASE = "https://pis.cninfo.com.cn/ics/index.html"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def response_data(payload: dict[str, Any]) -> Any:
    if payload.get("code") not in (None, 200, "200"):
        raise RuntimeError(f"CNINFO response failed: {payload.get('code')} {payload.get('msg')}")
    return payload.get("data", payload)


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        nested = value.get("list")
        return nested if isinstance(nested, list) else []
    return []


def find_chain(chain_list: Any, chain_id: str) -> dict[str, Any]:
    for menu in chain_list if isinstance(chain_list, list) else []:
        for chain in menu.get("chains", []) if isinstance(menu, dict) else []:
            if chain.get("chain_id") == chain_id:
                return chain
    raise KeyError(f"chain_id not found: {chain_id}")


def build_node(node: dict[str, Any], source_group: str, metadata: dict[str, dict[str, Any]]) -> dict[str, Any]:
    node_id = node.get("node_id") or node.get("cnode_id") or ""
    meta = metadata.get(node_id, {})
    children = [
        build_node(child, source_group, metadata)
        for child in node.get("children", [])
        if isinstance(child, dict)
    ]
    result = {
        "node_id": node_id,
        "name": node.get("node_name") or node.get("cnode_name") or "",
        "source_group": source_group,
        "node_floor": node.get("node_floor") or meta.get("node_floor") or "",
        "chain_updown": node.get("chain_up_down") or meta.get("chain_updown") or meta.get("chain_up_down") or "",
        "chain_type": node.get("chain_type") or meta.get("chain_type") or "",
        "industry_code": meta.get("industry_code") or "",
        "industry_name": meta.get("industry_name") or "",
        "chain_introduction": meta.get("chain_introduction") or "",
        "children": children,
        "companies": [],
    }
    if node.get("node_pid"):
        result["node_pid"] = node["node_pid"]
    return result


def count_nodes(nodes: list[dict[str, Any]]) -> int:
    return sum(1 + count_nodes(node.get("children", [])) for node in nodes)


def normalize_chain(chain_id: str, chain_list_payload: dict[str, Any], dynamic_payload: dict[str, Any], info_payload: dict[str, Any]) -> dict[str, Any]:
    chain_list = response_data(chain_list_payload)
    chain = find_chain(chain_list, chain_id)
    dynamic_data = response_data(dynamic_payload)
    info_data = response_data(info_payload)
    info_rows = as_list(info_data.get("list") if isinstance(info_data, dict) else [])
    metadata = {row.get("cnode_id", ""): row for row in info_rows if row.get("cnode_id")}

    tree: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    for source_group, raw_nodes in dynamic_data.items() if isinstance(dynamic_data, dict) else []:
        nodes = [
            build_node(node, source_group, metadata)
            for node in raw_nodes
            if isinstance(node, dict)
        ] if isinstance(raw_nodes, list) else []
        groups.append({"source_group": source_group, "nodes": nodes})
        tree.extend(nodes)

    return {
        "chain_id": chain_id,
        "chain_name": chain.get("chain_name", ""),
        "source_url": f"{CNINFO_BASE}#/macroindustrial/ConstructionProject?chainId={chain_id}",
        "node_count": count_nodes(tree),
        "industry_info_count": len(info_rows),
        "groups": groups,
        "tree": tree,
    }


def main() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chain-id", default="lsx019")
    parser.add_argument("--list-input", type=Path, default=project_dir / "data/raw/chainlist_ROOT.json")
    parser.add_argument("--dynamic-input", type=Path)
    parser.add_argument("--info-input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    dynamic_input = args.dynamic_input or project_dir / f"data/raw/chain_{args.chain_id}_dynamicChainMapNew.json"
    info_input = args.info_input or project_dir / f"data/raw/chain_{args.chain_id}_industry_info.json"
    output = args.output or project_dir / f"data/processed/chain_{args.chain_id}.json"
    result = normalize_chain(args.chain_id, load_json(args.list_input), load_json(dynamic_input), load_json(info_input))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"chain_id": args.chain_id, "chain_name": result["chain_name"], "node_count": result["node_count"], "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
