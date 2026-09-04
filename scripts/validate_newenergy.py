"""Reconcile the captured New Energy nodes against the chain and page totals."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_nodes(nodes: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for node in nodes:
        yield node
        yield from iter_nodes(node.get("children", []))


def page_check(capture: dict[str, Any], key: str, total_key: str, pages_key: str) -> dict[str, Any]:
    pages = capture.get("responses", {}).get(key, [])
    actual = sum(len(page.get("rows", [])) for page in pages)
    expected = int(capture.get("pagination", {}).get(total_key, 0) or 0)
    declared_pages = int(capture.get("pagination", {}).get(pages_key, 0) or 0)
    expected_pages = max(1, math.ceil(expected / 15))
    return {
        "expected_total": expected,
        "captured_rows": actual,
        "declared_pages": declared_pages,
        "expected_pages": expected_pages,
        "pass": actual == expected and declared_pages == expected_pages and len(pages) == expected_pages,
    }


def validate(chain: dict[str, Any], capture_dir: Path) -> dict[str, Any]:
    expected = list(iter_nodes(chain.get("tree", [])))
    expected_by_id = {node.get("node_id", ""): node for node in expected}
    captures = {path.stem: load_json(path) for path in sorted(capture_dir.glob("*.json"))}
    metadata_mismatches = []
    pagination_failures = []
    status_counts: dict[str, int] = {}
    node_results = []
    for node_id, capture in captures.items():
        status = capture.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        expected_node = expected_by_id.get(node_id)
        metadata_ok = bool(expected_node) and all(
            capture.get("node_name") == expected_node.get("name", "")
            and capture.get("industry_code", "") == expected_node.get("industry_code", "")
            and capture.get("chain_updown", "") == expected_node.get("chain_updown", "")
            for _ in [0]
        )
        if not metadata_ok:
            metadata_mismatches.append(node_id)
        listed = page_check(capture, "listed_pages", "listed_total", "listed_pages")
        non_listed = page_check(capture, "non_listed_pages", "non_listed_total", "non_listed_pages")
        if status == "ok" and (not listed["pass"] or not non_listed["pass"]):
            pagination_failures.append(node_id)
        node_results.append({"node_id": node_id, "status": status, "metadata_pass": metadata_ok, "listed": listed, "non_listed": non_listed})

    missing = sorted(set(expected_by_id) - set(captures))
    result = {
        "chain_id": chain.get("chain_id", ""),
        "chain_name": chain.get("chain_name", ""),
        "comparison": {
            "expected_nodes": len(expected),
            "capture_files": len(captures),
            "missing_nodes": missing,
            "metadata_mismatches": metadata_mismatches,
            "pagination_failures": pagination_failures,
            "status_counts": status_counts,
            "pass": not missing and not metadata_mismatches and not pagination_failures,
        },
        "nodes": node_results,
    }
    return result


def main() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chain-json", type=Path, default=project_dir / "data/processed/chain_lsx019.json")
    parser.add_argument("--capture-dir", type=Path, default=project_dir / "data/raw/newenergy_companies")
    parser.add_argument("--output", type=Path, default=project_dir / "data/processed/newenergy_validation.json")
    args = parser.parse_args()
    result = validate(load_json(args.chain_json), args.capture_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["comparison"], ensure_ascii=False))


if __name__ == "__main__":
    main()
