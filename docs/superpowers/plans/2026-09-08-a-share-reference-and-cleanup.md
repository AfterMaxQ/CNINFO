# A 股证券参考表与旧数据清洗 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 MySQL 中建立可复用的完整 A 股证券参考表，提供本地代码/名称匹配，并安全清洗现有 `company.stock_code` 数据。

**Architecture:** 新增独立的 `a_share_security` 参考表和惰性 AkShare 适配器。`reference init/refresh` 才允许访问 AkShare；产业链 `crawl`、`resume` 和 Excel 导出只读 MySQL。旧代码清洗由独立脚本调用共享清洗函数，默认预览，显式执行时使用单事务更新。

**Tech Stack:** Python 3.11、MySQL 8.0、PyMySQL、AkShare、argparse、pytest、openpyxl。

**Spec:** `docs/superpowers/specs/2026-09-08-a-share-reference-table-design.md`

## Global Constraints

- 标准完整代码必须是六位数字加 `.SH`、`.SZ` 或 `.BJ`，例如 `600519.SH`。
- AkShare 代码必须是小写交易所前缀加六位数字，例如 `sh600519`。
- `company.stock_code` 继续保存清洗后的 CNINFO 原始六位代码；标准完整代码来自 `a_share_security.full_code`。
- 清洗代码字段中的 `*`、空白和明确交易所前缀；公司简称字段只过滤 `*`，保留 `ST`。
- `crawl`、`resume` 和 `--export-now` 不得调用 AkShare。
- 参考表写入必须先完成整批校验；失败时保留旧数据。
- 旧数据清洗必须默认只读预览，执行前再次展示摘要，并在一个 MySQL 事务中提交。
- 现有九字段 XLSX 契约不变。
- 所有新增 MySQL 表和字段必须有简洁中文注释。

---

### Task 1: 扩展 MySQL 迁移和存储契约

**Files:**
- Create: `src/cninfo_chain/migrations/002_a_share_security.sql`
- Modify: `src/cninfo_chain/storage.py`
- Modify: `tests/test_schema.py`
- Modify: `tests/test_storage.py`

**Interfaces:**
- Produces `MySQLStore.replace_a_share_security(rows)`, `MySQLStore.find_a_share_security(stock_code=None, security_name=None)` and `MySQLStore.preview_stock_code_cleanup()` / `MySQLStore.execute_stock_code_cleanup(changes)` for later tasks.
- Keeps existing six-table databases upgradeable by adding only `a_share_security`; rejects unrelated partial schemas.

- [ ] **Step 1: Write migration and storage regression tests**

Add assertions for a seven-table current schema, six new columns, Chinese comments, the `full_code` primary key, and the `akshare_symbol` unique key. Add a migration test proving a legacy six-table set takes the 002 migration path while an unrelated partial set still raises `SchemaConflict`.

Run:

```powershell
python -m pytest tests/test_schema.py tests/test_storage.py -q
```

Expected: new tests fail because the seventh table and migration path do not exist yet.

- [ ] **Step 2: Add the `a_share_security` migration**

Create `002_a_share_security.sql` with these columns and comments:

```sql
`full_code` VARCHAR(16) NOT NULL COMMENT '标准完整代码，如600519.SH',
`stock_code` CHAR(6) NOT NULL COMMENT '去除标记后的六位股票代码，如600519',
`exchange` CHAR(2) NOT NULL COMMENT '交易所标识：SH、SZ或BJ',
`security_name` VARCHAR(255) NOT NULL COMMENT '证券名称，按AkShare来源原文保存',
`akshare_symbol` VARCHAR(16) NOT NULL COMMENT 'AkShare代码，如sh600519',
`updated_at` DATETIME(6) NOT NULL COMMENT '参考记录最近更新时间（UTC）'
```

Use `PRIMARY KEY (full_code)`, `UNIQUE (akshare_symbol)`, and non-unique indexes on `stock_code` and `security_name`.

- [ ] **Step 3: Make migration upgrade six-table installations**

Update `TABLE_NAMES`, `EXPECTED_COLUMN_COUNT`, `_migrate_target_schema`, `_migration_statements`, and `assert_schema_current` so that:

1. an empty database runs 001 and 002;
2. a database with exactly the original six tables runs only 002;
3. a database with all seven tables validates without re-running DDL;
4. any other target-table subset raises the existing schema error.

Keep all existing crawl table behavior unchanged.

- [ ] **Step 4: Run storage/schema tests**

Run:

```powershell
python -m pytest tests/test_schema.py tests/test_storage.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the migration boundary**

```powershell
git add src/cninfo_chain/migrations/002_a_share_security.sql src/cninfo_chain/storage.py tests/test_schema.py tests/test_storage.py
git commit -m "feat: add A-share reference table schema"
```

### Task 2: Implement AkShare row normalization

**Files:**
- Create: `src/cninfo_chain/securities.py`
- Modify: `src/cninfo_chain/errors.py`
- Create: `tests/test_securities.py`

**Interfaces:**
- `AShareSecurity` dataclass fields: `full_code: str`, `stock_code: str`, `exchange: str`, `security_name: str`, `akshare_symbol: str`.
- `normalize_akshare_row(symbol: object, name: object) -> AShareSecurity`.
- `parse_akshare_rows(rows: Sequence[Mapping[str, object]]) -> list[AShareSecurity]`.
- `clean_cninfo_stock_code(value: object) -> str | None`.
- `load_akshare_rows() -> Sequence[Mapping[str, object]]` lazily imports `akshare` and calls `ak.stock_zh_a_spot()`.

- [ ] **Step 1: Write normalization tests**

Cover the three canonical inputs and invalid rows:

```python
assert normalize_akshare_row("sh600519", "贵州茅台").full_code == "600519.SH"
assert normalize_akshare_row("sz000001", "平安银行").akshare_symbol == "sz000001"
assert normalize_akshare_row("bj920047", "北交所示例").exchange == "BJ"
assert clean_cninfo_stock_code("*600519") == "600519"
assert clean_cninfo_stock_code("sh600519") == "600519"
assert clean_cninfo_stock_code("*ST") is None
```

Also verify blank names, invalid prefixes, non-six-digit codes, duplicate `full_code`, and preservation of `*ST某某` as a name.

- [ ] **Step 2: Run tests to verify failure**

```powershell
python -m pytest tests/test_securities.py -q
```

Expected: FAIL because the module and functions are not present.

- [ ] **Step 3: Implement the pure normalizer**

Parse only `sh`, `sz`, and `bj` prefixes. Do not infer an exchange from the first digit. Reject malformed rows instead of dropping them silently. The CNINFO cleaner may remove code markers and explicit prefixes, but returns `None` for ambiguous or non-six-digit values.

- [ ] **Step 4: Implement the lazy AkShare adapter**

Import AkShare inside `load_akshare_rows()` so a normal crawl with a populated reference table does not require importing or calling AkShare. Convert the returned DataFrame with `to_dict("records")` and require columns `代码` and `名称`.

- [ ] **Step 5: Run normalization tests**

```powershell
python -m pytest tests/test_securities.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit normalization**

```powershell
git add src/cninfo_chain/securities.py src/cninfo_chain/errors.py tests/test_securities.py
git commit -m "feat: normalize A-share security codes"
```

### Task 3: Add reference-table import, preview, refresh, and matching

**Files:**
- Create: `src/cninfo_chain/reference.py`
- Modify: `src/cninfo_chain/storage.py`
- Create: `tests/test_reference.py`

**Interfaces:**
- `ReferencePreview` fields: `total`, `sh_count`, `sz_count`, `bj_count`, `invalid_count`, `duplicate_count`, `sample_rows`.
- `build_reference_preview(rows: Sequence[AShareSecurity]) -> ReferencePreview`.
- `replace_reference_table(store: MySQLStore, rows: Sequence[AShareSecurity]) -> int`.
- `SecurityMatch` fields: `status`, `full_code`, `akshare_symbol`, `security_name`, `reason`.
- `match_security(store: MySQLStore, *, stock_code: object = None, security_name: object = None) -> SecurityMatch`.

- [ ] **Step 1: Write reference preview and matching tests**

Use a fake store with two rows and assert:

```python
assert match_security(store, stock_code="600519").full_code == "600519.SH"
assert match_security(store, security_name="贵州茅台").status == "matched"
assert match_security(store, security_name="不存在").status == "unmatched"
assert match_security(store, security_name="同名证券").status == "ambiguous"
```

Add a code/name mismatch case returning `conflict`, and assert replacing a valid row set calls one transaction boundary and never performs an AkShare call.

- [ ] **Step 2: Run tests to verify failure**

```powershell
python -m pytest tests/test_reference.py -q
```

Expected: FAIL because the reference service and store methods are not present.

- [ ] **Step 3: Implement storage operations**

Add a dictionary-cursor query by `stock_code` and `security_name`. Make name matching exact and allow multiple rows so the caller can return `ambiguous`. Implement `replace_reference_table` as delete-and-insert inside the existing `transaction()` context; validate all rows before entering the transaction.

- [ ] **Step 4: Implement preview and matching**

Use the normalized rows to count exchanges and examples. Match by code first; if multiple rows share the code, use exact name; if code and name resolve to different rows, return `conflict`; never fuzzy-match or call AkShare.

- [ ] **Step 5: Run reference tests**

```powershell
python -m pytest tests/test_reference.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the reference service**

```powershell
git add src/cninfo_chain/reference.py src/cninfo_chain/storage.py tests/test_reference.py
git commit -m "feat: add local A-share reference matching"
```

### Task 4: Expose reference initialization and refresh in the CLI

**Files:**
- Modify: `src/cninfo_chain/__main__.py`
- Modify: `src/cninfo_chain/browser.py`
- Create: `tests/test_reference_cli.py`

**Interfaces:**
- Add `python -m cninfo_chain reference init` and `python -m cninfo_chain reference refresh`.
- Both commands print Chinese preview summaries; only an explicit confirmation writes data.
- `doctor` verifies the reference table exists and reports its row count, but does not call AkShare.

- [ ] **Step 1: Write CLI tests**

Mock `load_akshare_rows`, `build_reference_preview`, and the store. Assert `reference init` prints the three exchange counts, requires confirmation before mutation, and returns exit code 0 after a confirmed write. Assert `doctor` never imports or calls the AkShare loader.

- [ ] **Step 2: Run CLI tests to verify failure**

```powershell
python -m pytest tests/test_reference_cli.py -q
```

Expected: FAIL because the parser and handlers do not exist.

- [ ] **Step 3: Add the reference subparser and handlers**

Use lazy imports in the command branch. Run `store.migrate()` first, load and validate all rows, print the preview, prompt with an explicit Chinese confirmation phrase, and call `replace_reference_table` only after confirmation. `refresh` uses the same path but allows a populated table; `init` refuses to overwrite without the refresh command.

- [ ] **Step 4: Extend `doctor` without adding a network dependency**

After the existing MySQL migration check, query the reference count and include it in the JSON result. Leave the browser health request unchanged. If the reference table is empty, return a clear warning field rather than fetching AkShare.

- [ ] **Step 5: Run all CLI tests**

```powershell
python -m pytest tests/test_cli.py tests/test_reference_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the CLI boundary**

```powershell
git add src/cninfo_chain/__main__.py src/cninfo_chain/browser.py tests/test_reference_cli.py
git commit -m "feat: add A-share reference commands"
```

### Task 5: Implement the one-time legacy stock-code cleanup

**Files:**
- Create: `src/cninfo_chain/cleanup.py`
- Create: `scripts/clean_stock_codes.py`
- Create: `tests/test_cleanup.py`
- Modify: `src/cninfo_chain/storage.py`

**Interfaces:**
- `StockCodeChange` fields: `company_id: int`, `old_value: str | None`, `new_value: str | None`, `reason: str`.
- `ShortNameChange` fields: `company_id: int`, `old_value: str`, `new_value: str`, `reason: str`.
- `preview_stock_code_cleanup(store: MySQLStore) -> tuple[list[StockCodeChange], list[StockCodeChange]]` returns `(changes, invalid)` without writing.
- `preview_short_name_cleanup(store: MySQLStore) -> list[ShortNameChange]` finds only names containing `*`.
- `execute_company_cleanup(store: MySQLStore, stock_code_changes: Sequence[StockCodeChange], short_name_changes: Sequence[ShortNameChange]) -> int` updates both fields inside one transaction.
- Script modes: `python scripts/clean_stock_codes.py --preview` and `python scripts/clean_stock_codes.py --execute`.

- [ ] **Step 1: Write cleanup tests**

Use fake rows for `*600519`, ` sh600519 `, `*ST`, `None`, and `000001`, plus a `company_short_name` value `*ST示例`; assert only the first two become six-digit values, the name becomes `ST示例`, invalid codes remain untouched, preview performs no `UPDATE`, and an exception causes rollback.

- [ ] **Step 2: Run cleanup tests to verify failure**

```powershell
python -m pytest tests/test_cleanup.py -q
```

Expected: FAIL because the cleanup module and script do not exist.

- [ ] **Step 3: Implement the preview and transactional update**

Read `id`, `stock_code`, and `company_short_name`. Reuse `clean_cninfo_stock_code` for codes and `normalize_short_name` for abbreviations; never update `company_name`. `--preview` exits after the summary. `--execute` prints the same summary, asks the user to type `CLEAN`, then calls one transaction; any other input exits without writing.

- [ ] **Step 4: Implement the Windows-friendly script entrypoint**

Load `Settings.from_env()`, call `store.migrate()`, print concise Chinese logs, and return nonzero on invalid configuration or database failure. Do not invoke AkShare or Chrome. After a successful execution, print the command to run for re-export:

```text
python -m cninfo_chain --export-now
```

- [ ] **Step 5: Run cleanup tests**

```powershell
python -m pytest tests/test_cleanup.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the cleanup tool**

```powershell
git add src/cninfo_chain/cleanup.py scripts/clean_stock_codes.py src/cninfo_chain/storage.py tests/test_cleanup.py
git commit -m "feat: add previewable stock code cleanup"
```

### Task 6: Update user-facing usage and complete verification

**Files:**
- Modify: `USAGE.md`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Create or modify: `tests/test_end_to_end_reference.py`

- [ ] **Step 1: Add the optional AkShare dependency**

Add an optional `reference` dependency extra for AkShare. Keep the import lazy so installed reference data is sufficient for normal crawl/export operation.

- [ ] **Step 2: Document current commands only**

Add a short section explaining:

```powershell
python -m cninfo_chain reference init
python -m cninfo_chain reference refresh
python scripts/clean_stock_codes.py --preview
python scripts/clean_stock_codes.py --execute
python -m cninfo_chain --export-now
```

State that init/refresh are the only AkShare network operations, cleanup does not alter names, and the Excel output remains nine columns. Update the MySQL table count from six to seven where the current schema is listed.

- [ ] **Step 3: Add an offline end-to-end reference test**

Seed a fake reference table, run a local candidate match, and assert the AkShare loader is not called. Run a cleanup preview and assert the database update method is not called until `--execute` confirmation.

- [ ] **Step 4: Run the full verification suite**

```powershell
python -m pytest -q
python -m compileall -q src scripts tests
git diff --check
```

Expected: all tests pass, compilation succeeds, and there are no whitespace errors.

- [ ] **Step 5: Run safe live checks**

With the configured MySQL available, run `python -m cninfo_chain doctor` and then `python scripts/clean_stock_codes.py --preview`. Confirm no `UPDATE` occurred during preview. Do not run `--execute` against the production database until the preview counts and examples are reviewed.

- [ ] **Step 6: Commit and push the complete implementation**

```powershell
git add README.md USAGE.md pyproject.toml src tests scripts
git commit -m "feat: add reusable A-share reference workflow"
$env:GIT_CONFIG_GLOBAL='NUL'
git push https://github.com/AfterMaxQ/CNINFO.git HEAD:main
```

Verify local and remote `HEAD` are equal and the working tree is clean.
