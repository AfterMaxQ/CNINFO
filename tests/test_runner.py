from __future__ import annotations

import json
from dataclasses import replace

import pytest

from cninfo_chain.errors import AuthenticationPaused, PaginationMismatch, SecurityBoundaryError
from cninfo_chain.models import ChainNode
from cninfo_chain.raw_files import RawRunWriter
from cninfo_chain.runner import CollectorRunner, safe_error_message


class FakeStore:
    def __init__(self):
        self.task_statuses = []
        self.commits = []
        self.run_statuses = []
        self.rows = []
        self.disabled = []

    def set_task_status(self, run_id, node_db_id, status, **kwargs):
        self.task_statuses.append((run_id, node_db_id, status, kwargs))

    def commit_node(self, run_id, node_db_id, node, companies):
        self.commits.append((run_id, node_db_id, node, list(companies)))

    def set_run_status(self, run_id, status, **kwargs):
        self.run_statuses.append((run_id, status, kwargs))

    def run_nodes(self, run_id):
        return list(self.rows)

    def disable_missing_nodes(self, chain_id, active_node_ids):
        self.disabled.append((chain_id, list(active_node_ids)))

    def run_summary(self, run_id):
        return {"completed_nodes": len(self.commits), "failed_nodes": 0}


class FakeBrowser:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def call(self, endpoint, params):
        self.calls.append((endpoint, params))
        response = self.responses.pop(0)
        return {"status": 200, "json": response}


@pytest.fixture
def eva_node():
    return ChainNode(
        chain_id="lsx019",
        node_id="A02n019",
        parent_node_id="A02n027",
        node_name="太阳能EVA胶膜",
        node_definition="定义",
        business_zone="上游",
        sort_no=1,
        path=("太阳能电池零部件", "太阳能EVA胶膜"),
        industry_code="A02010201",
        industry_name="太阳能EVA胶膜",
        source_url="https://pis.cninfo.com.cn/ics/index.html#/industryChain/test",
    )


def test_raw_writer_is_atomic_and_rejects_sensitive_keys(tmp_path):
    writer = RawRunWriter(tmp_path, "run-1")
    path = writer.write_json("chain_lsx019.json", {"code": 200, "data": []})
    assert json.loads(path.read_text(encoding="utf-8"))["code"] == 200
    assert not list(path.parent.glob("*.tmp"))

    with pytest.raises(SecurityBoundaryError):
        writer.write_json("unsafe.json", {"data": {"Authorization": "secret"}})
    assert not (path.parent / "unsafe.json").exists()


def test_node_without_industry_code_commits_empty_without_company_calls(tmp_path, eva_node):
    store = FakeStore()
    browser = FakeBrowser([])
    runner = CollectorRunner(store, browser, tmp_path, page_size=15, sleep=lambda _: None)

    runner.collect_node("run-1", 7, replace(eva_node, industry_code=None))

    assert browser.calls == []
    assert len(store.commits) == 1
    assert store.commits[0][3] == []


def test_pagination_mismatch_never_calls_node_commit(tmp_path, load_json, eva_node):
    income = load_json("node_A02n019_companyIncome.json")
    listed = load_json("node_A02n019_searchOtherListed.json")
    non_listed_first = load_json("node_A02n019_searchglobalNew.json")
    broken_last = load_json("node_A02n019_searchglobalNew_page5.json")
    broken_last["data"]["page"] = 4
    browser = FakeBrowser(
        [income, listed, non_listed_first]
        + [load_json(f"node_A02n019_searchglobalNew_page{i}.json") for i in (2, 3, 4)]
        + [broken_last]
    )
    store = FakeStore()
    runner = CollectorRunner(store, browser, tmp_path, page_size=15, sleep=lambda _: None)

    with pytest.raises(PaginationMismatch):
        runner.collect_node("run-1", 7, eva_node)

    assert store.commits == []


def test_complete_real_fixture_node_commits_85_companies(tmp_path, load_json, eva_node):
    browser = FakeBrowser(
        [
            load_json("node_A02n019_companyIncome.json"),
            load_json("node_A02n019_searchOtherListed.json"),
            load_json("node_A02n019_searchglobalNew.json"),
            *[
                load_json(f"node_A02n019_searchglobalNew_page{i}.json")
                for i in (2, 3, 4, 5)
            ],
        ]
    )
    store = FakeStore()
    runner = CollectorRunner(store, browser, tmp_path, page_size=15, sleep=lambda _: None)

    runner.collect_node("run-1", 7, eva_node)

    assert len(store.commits) == 1
    assert len(store.commits[0][3]) == 85
    assert [call[0] for call in browser.calls[:3]] == [
        "company_income",
        "listed_search",
        "non_listed_search",
    ]


def test_resume_skips_terminal_nodes_and_finishes_remaining_node(tmp_path, eva_node):
    store = FakeStore()
    base = {
        "chain_id": eva_node.chain_id,
        "chain_name": "新能源",
        "parent_node_id": eva_node.parent_node_id,
        "node_name": eva_node.node_name,
        "node_definition": eva_node.node_definition,
        "business_zone": eva_node.business_zone,
        "sort_no": eva_node.sort_no,
        "path_json": json.dumps(eva_node.path, ensure_ascii=False),
        "industry_code": None,
        "industry_name": eva_node.industry_name,
        "source_url": eva_node.source_url,
    }
    store.rows = [
        {**base, "industry_chain_node_id": 7, "node_id": "done", "status": "committed"},
        {**base, "industry_chain_node_id": 8, "node_id": "remaining", "status": "failed"},
    ]
    browser = FakeBrowser([])
    runner = CollectorRunner(store, browser, tmp_path, page_size=15, sleep=lambda _: None)

    assert runner.resume("run-1") == "run-1"

    assert [commit[1] for commit in store.commits] == [8]
    assert store.run_statuses[-1][1] == "complete"
    assert store.disabled == [("lsx019", ["done", "remaining"])]


def test_authentication_business_code_pauses_instead_of_marking_node_failed(
    tmp_path, eva_node
):
    store = FakeStore()
    browser = FakeBrowser([{"code": 403, "ok": False, "msg": "login expired", "data": {}}])
    runner = CollectorRunner(store, browser, tmp_path, page_size=15, sleep=lambda _: None)

    with pytest.raises(AuthenticationPaused):
        runner.collect_node("run-1", 7, eva_node)

    assert store.commits == []


def test_error_message_redacts_common_secret_assignments():
    message = safe_error_message(
        RuntimeError("Authorization: bearer-abc password=mysql-secret token=qwerty")
    )
    assert "bearer-abc" not in message
    assert "mysql-secret" not in message
    assert "qwerty" not in message
    assert message.count("[REDACTED]") == 3
