from __future__ import annotations

import json
import re
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError

from cninfo_chain.companies import (
    candidates_from_income,
    candidates_from_listed,
    merge_companies,
)
from cninfo_chain.endpoints import request_parameters
from cninfo_chain.errors import (
    ApiBusinessError,
    AuthenticationPaused,
    CollectorError,
    PaginationMismatch,
)
from cninfo_chain.models import ChainNode, ChainSeed, PageResult
from cninfo_chain.parsers import (
    parse_chain_list,
    parse_company_income_page,
    parse_dynamic_nodes,
    parse_industry_metadata,
    parse_search_page,
    validate_pages,
)
from cninfo_chain.raw_files import RawRunWriter


RETRY_DELAYS = (2, 5, 15)


class CollectorRunner:
    def __init__(
        self,
        store: Any,
        browser: Any,
        raw_root: Path,
        *,
        page_size: int,
        sleep: Callable[[float], None] = time.sleep,
        on_theme_complete: Callable[[str], None] | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        self.store = store
        self.browser = browser
        self.raw_root = raw_root
        self.page_size = page_size
        self.sleep = sleep
        self.on_theme_complete = on_theme_complete
        self.on_log = on_log

    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log(message)

    def crawl_all(self) -> str:
        run_id = str(uuid.uuid4())
        self._log(f"[开始] 全主题采集，运行 ID：{run_id}")
        writer = RawRunWriter(self.raw_root, run_id)
        root = self._fetch_json(
            writer, "chain_list", request_parameters("chain_list"), "chainlist_ROOT.json"
        )
        chains = parse_chain_list(root)
        self._log(f"[目录] 读取完成，共 {len(chains)} 个主题")
        nodes_by_chain: dict[str, list[ChainNode]] = {}
        for index, chain in enumerate(chains, start=1):
            self._log(f"[发现 {index}/{len(chains)}] 读取主题：{chain.chain_name}")
            nodes_by_chain[chain.chain_id] = self._discover_theme(writer, chain)
            self._log(
                f"[发现 {index}/{len(chains)}] 主题节点：{len(nodes_by_chain[chain.chain_id])} 个"
            )

        self.store.create_run(run_id)
        all_nodes = [node for chain in chains for node in nodes_by_chain[chain.chain_id]]
        self._log(f"[任务] 已建立 {len(all_nodes)} 个节点任务")
        try:
            node_db_ids = self.store.sync_catalog(run_id, chains, all_nodes)
            complete = self._process_themes(run_id, chains, nodes_by_chain, node_db_ids)
            status = "complete" if complete else "partial"
            self.store.set_run_status(run_id, status)
            self._log(f"[结束] 全主题采集状态：{status}")
        except AuthenticationPaused as error:
            self.store.set_run_status(run_id, "paused_auth", error_message=str(error))
            self._write_manifest(writer, run_id, len(chains), "paused_auth")
            raise
        except KeyboardInterrupt:
            self.store.set_run_status(run_id, "paused")
            self._write_manifest(writer, run_id, len(chains), "paused")
            raise
        except BaseException as error:
            self.store.set_run_status(run_id, "failed", error_message=safe_error_message(error))
            self._write_manifest(writer, run_id, len(chains), "failed")
            raise
        self._write_manifest(writer, run_id, len(chains), status)
        return run_id

    def resume(self, run_id: str) -> str:
        rows = self.store.run_nodes(run_id)
        if not rows:
            raise CollectorError(f"run has no node tasks: {run_id}")
        self._log(f"[续跑] 运行 ID：{run_id}，共 {len(rows)} 个节点任务")
        self.store.set_run_status(run_id, "running")
        writer = RawRunWriter(self.raw_root, run_id)
        grouped: dict[str, list[tuple[int, ChainNode, str]]] = defaultdict(list)
        chain_names: dict[str, str] = {}
        for row in rows:
            node = _node_from_row(row)
            chain_names[node.chain_id] = str(row["chain_name"])
            grouped[node.chain_id].append(
                (int(row["industry_chain_node_id"]), node, str(row["status"]))
            )
        try:
            all_complete = True
            for chain_id, tasks in grouped.items():
                theme_complete = True
                completed_count = sum(
                    task_status in {"committed", "committed_empty"}
                    for _, _, task_status in tasks
                )
                self._log(
                    f"[续跑] 主题 {chain_names[chain_id]}：跳过 {completed_count} 个已完成节点，"
                    f"待处理 {len(tasks) - completed_count} 个"
                )
                for node_db_id, node, task_status in tasks:
                    if task_status in {"committed", "committed_empty"}:
                        continue
                    self._log(f"[节点] 开始：{node.node_name}")
                    if not self._collect_with_status(run_id, node_db_id, node):
                        theme_complete = False
                        all_complete = False
                if theme_complete:
                    self.store.disable_missing_nodes(
                        chain_id, [node.node_id for _, node, _ in tasks]
                    )
                    if self.on_theme_complete:
                        self.on_theme_complete(chain_id)
            status = "complete" if all_complete else "partial"
            self.store.set_run_status(run_id, status)
            self._log(f"[结束] 续跑状态：{status}")
        except AuthenticationPaused as error:
            self.store.set_run_status(run_id, "paused_auth", error_message=str(error))
            self._write_manifest(writer, run_id, len(grouped), "paused_auth")
            raise
        except KeyboardInterrupt:
            self.store.set_run_status(run_id, "paused")
            self._write_manifest(writer, run_id, len(grouped), "paused")
            raise
        self._write_manifest(writer, run_id, len(grouped), status)
        return run_id

    def _discover_theme(self, writer: RawRunWriter, chain: ChainSeed) -> list[ChainNode]:
        dynamic = self._fetch_json(
            writer,
            "dynamic_map",
            request_parameters("dynamic_map", chain_id=chain.chain_id),
            f"chain_{chain.chain_id}_dynamic_map.json",
        )
        info = self._fetch_json(
            writer,
            "chain_info",
            request_parameters("chain_info", chain_id=chain.chain_id),
            f"chain_{chain.chain_id}_industry_info.json",
        )
        return parse_dynamic_nodes(
            chain.chain_id, dynamic, parse_industry_metadata(info)
        )

    def _process_themes(
        self,
        run_id: str,
        chains: Sequence[ChainSeed],
        nodes_by_chain: dict[str, list[ChainNode]],
        node_db_ids: dict[tuple[str, str], int],
    ) -> bool:
        all_complete = True
        for theme_index, chain in enumerate(chains, start=1):
            nodes = nodes_by_chain[chain.chain_id]
            self._log(
                f"[主题 {theme_index}/{len(chains)}] 开始：{chain.chain_name}（{len(nodes)} 个节点）"
            )
            theme_complete = True
            for node_index, node in enumerate(nodes, start=1):
                self._log(
                    f"[节点 {theme_index}.{node_index}/{len(nodes)}] 开始：{node.node_name}"
                )
                node_db_id = node_db_ids[(chain.chain_id, node.node_id)]
                if not self._collect_with_status(run_id, node_db_id, node):
                    all_complete = False
                    theme_complete = False
            if theme_complete:
                self.store.disable_missing_nodes(
                    chain.chain_id, [node.node_id for node in nodes]
                )
                if self.on_theme_complete:
                    self.on_theme_complete(chain.chain_id)
                self._log(f"[主题 {theme_index}/{len(chains)}] 完成：{chain.chain_name}")
            else:
                self._log(f"[主题 {theme_index}/{len(chains)}] 未完成：{chain.chain_name}")
        return all_complete

    def _collect_with_status(self, run_id: str, node_db_id: int, node: ChainNode) -> bool:
        try:
            self.collect_node(run_id, node_db_id, node)
            self._log(f"[节点] 完成：{node.node_name}")
            return True
        except AuthenticationPaused:
            raise
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            message = safe_error_message(error)
            self.store.set_task_status(
                run_id,
                node_db_id,
                "failed",
                error_message=message,
                increment_retry=True,
            )
            self._log(f"[节点] 失败：{node.node_name}；{message}")
            return False

    def collect_node(self, run_id: str, node_db_id: int, node: ChainNode) -> None:
        writer = RawRunWriter(self.raw_root, run_id)
        self.store.set_task_status(run_id, node_db_id, "fetching")
        if not node.industry_code:
            self.store.commit_node(run_id, node_db_id, node, [])
            return

        income_pages = self._fetch_income_pages(writer, node)
        listed_pages = self._fetch_search_pages(writer, node, "listed_search")
        self.store.set_task_status(run_id, node_db_id, "validating")

        income_items = validate_pages(income_pages)
        listed_items = validate_pages(listed_pages)
        income_candidates = candidates_from_income(income_items, start_order=0)
        listed_candidates = candidates_from_listed(
            listed_items, start_order=len(income_candidates)
        )
        companies = merge_companies(income_candidates + listed_candidates)
        self.store.commit_node(run_id, node_db_id, node, companies)

    def _fetch_income_pages(
        self, writer: RawRunWriter, node: ChainNode
    ) -> list[PageResult]:
        first = self._fetch_income_page(writer, node, 1)
        return [first] + [
            self._fetch_income_page(writer, node, page)
            for page in range(2, first.pages + 1)
        ]

    def _fetch_income_page(
        self, writer: RawRunWriter, node: ChainNode, page: int
    ) -> PageResult:
        payload = self._fetch_json(
            writer,
            "company_income",
            request_parameters(
                "company_income",
                industry_code=node.industry_code,
                page=page,
                page_size=self.page_size,
            ),
            f"node_{node.node_id}_company_income_page_{page}.json",
        )
        return parse_company_income_page(payload)

    def _fetch_search_pages(
        self, writer: RawRunWriter, node: ChainNode, endpoint: str
    ) -> list[PageResult]:
        first = self._fetch_search_page(writer, node, endpoint, 1)
        pages = [first]
        for page in range(2, first.pages + 1):
            current = self._fetch_search_page(writer, node, endpoint, page)
            if current.page == first.page and current.items == first.items:
                raise PaginationMismatch(
                    f"{endpoint} 返回重复的第 1 页（{len(first.items)}/{first.total} 条），"
                    "当前登录账号可能没有完整分页权限"
                )
            pages.append(current)
        return pages

    def _fetch_search_page(
        self,
        writer: RawRunWriter,
        node: ChainNode,
        endpoint: str,
        page: int,
    ) -> PageResult:
        payload = self._fetch_json(
            writer,
            endpoint,
            request_parameters(
                endpoint,
                industry_code=node.industry_code,
                page=page,
                page_size=self.page_size,
            ),
            f"node_{node.node_id}_{endpoint}_page_{page}.json",
        )
        return parse_search_page(payload, endpoint, self.page_size)

    def _fetch_json(
        self,
        writer: RawRunWriter,
        endpoint: str,
        params: dict[str, Any],
        filename: str,
    ) -> dict[str, Any]:
        result = self._call_with_retry(endpoint, params)
        payload = result["json"]
        if isinstance(payload, dict) and str(payload.get("code")) in {"401", "403"}:
            raise AuthenticationPaused(f"{endpoint} returned authentication business code")
        writer.write_json(filename, payload)
        return payload

    def _call_with_retry(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: BaseException | None = None
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                result = self.browser.call(endpoint, params)
            except (ConnectionError, TimeoutError, OSError, PlaywrightError) as error:
                last_error = error
            else:
                status = int(result["status"])
                if status in {401, 403}:
                    raise AuthenticationPaused(f"{endpoint} returned HTTP {status}")
                if 200 <= status < 300:
                    return result
                if status in {408, 429} or status >= 500:
                    last_error = CollectorError(f"{endpoint} returned HTTP {status}")
                else:
                    raise CollectorError(f"{endpoint} returned HTTP {status}")
            if attempt == len(RETRY_DELAYS):
                break
            self.sleep(RETRY_DELAYS[attempt])
        raise CollectorError(
            f"{endpoint} failed after retries: {safe_error_message(last_error)}"
        )

    def _write_manifest(
        self, writer: RawRunWriter, run_id: str, theme_count: int, status: str
    ) -> None:
        summary = self.store.run_summary(run_id)
        writer.write_manifest(
            run_id=run_id,
            theme_count=theme_count,
            completed_nodes=int(summary.get("completed_nodes", 0)),
            failed_nodes=int(summary.get("failed_nodes", 0)),
            status=status,
        )


def _node_from_row(row: dict[str, Any]) -> ChainNode:
    raw_path = row["path_json"]
    path = json.loads(raw_path) if isinstance(raw_path, str) else raw_path
    return ChainNode(
        chain_id=str(row["chain_id"]),
        node_id=str(row["node_id"]),
        parent_node_id=(str(row["parent_node_id"]) if row.get("parent_node_id") else None),
        node_name=str(row["node_name"]),
        node_definition=row.get("node_definition"),
        business_zone=str(row["business_zone"]),
        sort_no=int(row["sort_no"]),
        path=tuple(path),
        industry_code=row.get("industry_code"),
        industry_name=row.get("industry_name"),
        source_url=str(row["source_url"]),
    )


def safe_error_message(error: BaseException | None) -> str:
    if error is None:
        return "unknown error"
    if isinstance(error, ApiBusinessError):
        return f"{type(error).__name__}: {error.code}"
    message = str(error)[:900]
    message = re.sub(
        r"(?i)\b(cookie|authorization|token|sign|password)\s*[:=]\s*[^\s,;]+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        message,
    )
    return f"{type(error).__name__}: {message}"
