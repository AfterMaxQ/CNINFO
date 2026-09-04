# CNINFO 全主题产业链采集实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Use <code>- [ ]</code> to track progress.

**Goal:** 实现一个 Windows 单机批处理程序，复用业务人员已登录的 Chrome，采集 CNINFO 全主题产业链，按节点原子写入 MySQL，并持续生成九字段 XLSX。

**Architecture:** Chrome/CDP 负责登录态接口调用；解析层负责确定性字段映射和企业去重；MySQL 保存当前主题、节点、企业、关系与运行状态；XLSX 从数据库当前成功数据物化。首期保持单进程顺序采集，不建设服务端、队列、定时调度或管理后台。

**Tech Stack:** Python 3.11、Playwright、PyMySQL、MySQL 8.0、openpyxl、pytest。

**Spec:** [CNINFO 全主题产业链采集技术设计](../specs/2026-09-04-cninfo-full-chain-collection-design.md)

## 实施约束

- MySQL 使用 InnoDB、utf8mb4；物理模型固定为规格中的 6 张表、45 个字段。
- 每张表和每个字段都必须在 MySQL 中写入简洁中文 COMMENT。
- 企业去重顺序：CNINFO 企业 ID、股票代码、规范化原名。
- company_short_name 不参与去重；非上市接口无明确简称时写 NULL，但企业和节点关系仍入库。
- 一个节点完成全部接口分页和数量校验后，才能在单个事务中替换该节点结果。
- 每个主题完成后原子重建一次 XLSX；全站完成后生成最终版；支持手动 --export-now。
- XLSX 固定九列：主题、信源主体、分类1、分类2、分类3、分类4、公司、信源URL、备注。
- Cookie、Authorization、token、sign、密码不得进入 Python 输出、日志、raw、MySQL 或 XLSX。
- raw JSON 只用于故障排查，不新增逐请求证据表、节点历史表或企业标识历史表。
- 生产代码、测试、工具脚本、fixture 和运行产物分目录保存，不混放。
- README 和用户文档只描述实施完成后的当前项目状态，不记录旧版本、修改过程、评审反馈或未来路线图。
- 目标仓库为 <code>https://github.com/AfterMaxQ/CNINFO.git</code>；全部验收通过前不推送。

## 目标项目结构

~~~text
cninfo-chain-explorer/
├─ pyproject.toml
├─ README.md
├─ src/
│  └─ cninfo_chain/
│     ├─ __init__.py
│     ├─ __main__.py
│     ├─ config.py
│     ├─ errors.py
│     ├─ models.py
│     ├─ endpoints.py
│     ├─ parsers.py
│     ├─ normalization.py
│     ├─ companies.py
│     ├─ browser.py
│     ├─ bridge.js
│     ├─ storage.py
│     ├─ runner.py
│     ├─ raw_files.py
│     ├─ exporter.py
│     └─ migrations/
│        └─ 001_initial.sql
├─ scripts/
│  ├─ start_cninfo_chrome.ps1
│  └─ 现有探索脚本
├─ tests/
├─ data/
│  ├─ raw/       固定测试样本
│  └─ runs/      运行期调试响应
└─ export/
   └─ result.xlsx
~~~

现有 <code>scripts/discover_api.py</code>、<code>fetch_chain.py</code>、<code>fetch_company.py</code>、<code>validate_newenergy.py</code> 保留为辅助探索工具，不直接扩写成生产入口。

---

### Task 1: 建立仓库边界和 Python 工程骨架

**Files**

- Create: <code>.gitignore</code>
- Create: <code>pyproject.toml</code>
- Create: <code>src/cninfo_chain/__init__.py</code>
- Create: <code>src/cninfo_chain/config.py</code>
- Create: <code>src/cninfo_chain/errors.py</code>
- Create: <code>src/cninfo_chain/models.py</code>
- Create: <code>tests/conftest.py</code>

**Work**

- [ ] 初始化本地 main 分支并添加远端，但不推送；执行前再次确认远端没有分支。
- [ ] .gitignore 排除 __pycache__、测试缓存、虚拟环境、data/runs、data/processed、export/*.xlsx 等运行产物。
- [ ] pyproject.toml 声明 Python 3.11、Playwright、PyMySQL、openpyxl、pytest 和 cninfo-chain 命令入口。
- [ ] Settings 从环境变量读取 MySQL、CDP、raw 和 export 配置；密码不进入 repr 或安全摘要。
- [ ] 建立主题、节点、企业候选和合并企业 dataclass，以及稳定异常类型。
- [ ] tests/conftest.py 提供 data/raw 路径和 JSON fixture。

**Acceptance**

- <code>python -m pip install -e ".[test]"</code> 成功。
- 配置测试证明缺失环境变量时只输出变量名，任何输出不包含数据库密码。
- 本地 Git 只跟踪代码、文档和测试需要的根级 raw fixture；远端仍为空。

---

### Task 2: 实现 MySQL 最小模型与表联动

**Files**

- Create: <code>src/cninfo_chain/migrations/001_initial.sql</code>
- Create: <code>src/cninfo_chain/storage.py</code>
- Create: <code>tests/test_schema.py</code>
- Create: <code>tests/test_storage.py</code>

**Work**

- [ ] 按规格第 9 章建立 crawl_run、industry_chain、industry_chain_node、company、industry_chain_company、crawl_node_task。
- [ ] DDL 写全 45 个字段、主键、唯一约束、外键、必要索引、6 个表注释和 45 个字段注释。
- [ ] MySQLStore 提供 migration、运行创建、节点任务状态、节点事务、恢复查询和四表导出查询。
- [ ] 节点事务内完成企业全局识别、当前节点旧关系替换、节点状态和任务状态更新。
- [ ] 关系变化后根据全部节点关系重新汇总 company.listing_status。
- [ ] 同一 database 中存在其他业务表可以继续使用；如果六个目标表出现同名但不兼容结构，抛出 SCHEMA_CONFLICT，不执行 DROP 或自动 ALTER。
- [ ] 如现有 database 已有不兼容的 industry_chain 表，改用独立 CNINFO_MYSQL_DATABASE。

**Acceptance**

- information_schema 查询得到 6 张目标表和 45 个字段，所有中文注释非空。
- 企业可以关联多个节点，节点可以关联多个企业。
- 重采同一节点只替换该节点关系，不影响其他节点。
- 模拟事务异常后，节点旧数据和旧关系保持不变。

---

### Task 3: 实现接口解析、节点投影和企业识别

**Files**

- Create: <code>src/cninfo_chain/endpoints.py</code>
- Create: <code>src/cninfo_chain/parsers.py</code>
- Create: <code>src/cninfo_chain/normalization.py</code>
- Create: <code>src/cninfo_chain/companies.py</code>
- Create: <code>tests/test_parsers.py</code>
- Create: <code>tests/test_normalization.py</code>
- Create: <code>tests/test_companies.py</code>

**Work**

- [ ] 建立 chain_list、dynamic_map、chain_info、node_info、company_income、listed_search、non_listed_search 静态注册表。
- [ ] 对 HTTP、业务 code、ok、字段类型和分页 total/pages/page 做严格校验。
- [ ] companyIncome 从 data.list.list 读取；上市和非上市检索从 data.companys 读取。
- [ ] 只按 dynamicChainMapNew.children 建树，使用主题级 industry-info 补充节点定义、行业编码和上下游分区。
- [ ] 节点按上游、中游、下游、其他和父先子后的来源顺序投影；完整路径保留原始名称。
- [ ] node_definition 直接映射 chain_introduction，不摘要、不改写。
- [ ] 年报简称映射 secname_one/secname_two；上市映射 companyShortName；非上市简称固定为 NULL。
- [ ] 节点内合并三类接口和全部分页，再由 MySQL company 表做跨节点、跨主题全局去重。
- [ ] 标识冲突抛出 IDENTITY_CONFLICT，不做模糊合并。

**Acceptance**

- 根目录 fixture：17 个目录、134 个唯一主题。
- 新能源 fixture：动态树和元数据均为 124 个节点，14 个节点无 industry_code。
- EVA fixture：年报 9 条、上市 7 条、非上市 71 条，分页为 15/15/15/15/11。
- 87 条候选合并为 85 个企业。
- 天洋新材按股票代码合并；苏州优乐赛按 CNINFO 企业 ID 合并且 listing_status=2。
- 非上市无明确简称时 company_short_name 为 NULL，不从 fullname 或 stock_name 猜简称。

---

### Task 4: 实现已登录 Chrome 的安全 CDP 桥

**Files**

- Create: <code>src/cninfo_chain/bridge.js</code>
- Create: <code>src/cninfo_chain/browser.py</code>
- Create: <code>scripts/start_cninfo_chrome.ps1</code>
- Create: <code>tests/test_browser.py</code>

**Work**

- [ ] 启动脚本使用非默认 Chrome 用户目录，只监听 127.0.0.1:9222，并保持可见供业务人员登录。
- [ ] Python 只允许连接回环 CDP 地址并选择 pis.cninfo.com.cn 页面。
- [ ] bridge.js 在页面闭包内观察同源 Fetch/XHR 请求模板；对 Python 只暴露端点键、响应状态和 JSON。
- [ ] 页面桥根据端点注册表发送 form 或 JSON 请求，不把认证头返回 Python。
- [ ] doctor 检查 CDP、CNINFO 页面、桥模板、根目录接口、MySQL 连接和 schema。
- [ ] 日志与错误对象经过递归敏感键过滤。

**Acceptance**

- 非回环 CDP 地址被拒绝。
- 桥接结果中出现 cookie、authorization、token、sign、password 等键时立即失败。
- 登录态 Chrome 上 doctor 成功，输出中不存在认证材料。
- 根目录接口和 EVA 三类企业接口第一页可以返回有效 JSON。

---

### Task 5: 实现节点状态机、raw 文件和断点恢复

**Files**

- Create: <code>src/cninfo_chain/raw_files.py</code>
- Create: <code>src/cninfo_chain/runner.py</code>
- Modify: <code>src/cninfo_chain/storage.py</code>
- Create: <code>tests/test_runner.py</code>

**Work**

- [ ] crawl --all 完成全部主题和节点发现后创建新 run_id 和节点任务。
- [ ] 有行业编码节点依次完成年报、上市、非上市全部分页；无行业编码节点直接提交 committed_empty。
- [ ] 每页响应以确定性文件名原子写入 data/runs/{run_id}，不保存认证材料或逐文件哈希。
- [ ] 分页和字段校验通过后才调用 MySQL 节点事务。
- [ ] 网络超时、连接重置、HTTP 408/429/5xx 最多按 2/5/15 秒重试三次。
- [ ] HTTP 401/403 或认证业务错误把运行置为 paused_auth。
- [ ] resume 只读取本次运行未提交节点，已 committed/committed_empty 节点跳过。
- [ ] 主题全部节点完成后再禁用本轮已不存在的旧节点，并触发一次 XLSX 重建。
- [ ] Ctrl+C 在当前请求完成后把运行置为 paused，不留下半个事务。
- [ ] capture_manifest 只保存运行 ID、UTC 时间、主题数、节点完成/失败数和运行状态。

**Acceptance**

- 分页不一致时不调用节点提交，旧业务结果不变。
- 无行业编码节点不调用企业接口，但数据库和 XLSX 保留节点。
- 中断恢复后不重复提交已完成节点。
- 只有所有节点成功时运行状态才能变为 complete。

---

### Task 6: 实现 XLSX、CLI 和当前状态 README

**Files**

- Create: <code>src/cninfo_chain/exporter.py</code>
- Create: <code>src/cninfo_chain/__main__.py</code>
- Create: <code>tests/test_exporter.py</code>
- Create: <code>tests/test_cli.py</code>
- Modify: <code>README.md</code>

**Work**

- [ ] exporter 用 LEFT JOIN 读取启用主题、成功节点、节点企业关系、企业简称和原始名称。
- [ ] 同一节点只输出一行，优先使用 company_short_name；简称为空时以 company_name 兜底，按来源顺序去重并用顿号连接。
- [ ] 分类1为业务分区，分类2/3为路径前两层，第三层及更深合并进分类4。
- [ ] URL 写为可点击超链接，每个主题仅首行写备注。
- [ ] 先写临时 XLSX，重新打开校验九列、行数和超链接，再用 os.replace 替换 result.xlsx。
- [ ] 实现 doctor、crawl --all、crawl --resume、status 和 --export-now。
- [ ] --export-now 只访问 MySQL，不连接 Chrome、不发网络请求。
- [ ] README 按最终真实结构重写为用户手册，包含安装、环境变量、Chrome、MySQL 表职责、命令、输出和测试方法。
- [ ] README 删除实施后失效的“下一步”“尚未实现”“与旧方案比较”等内容，不写本次新增、原来、此前、旧版、修改后、评审反馈或迁移过程。

**Acceptance**

- XLSX 恰好九列，父节点、无企业节点和 committed_empty 节点存在。
- 公司列不输出 company_name、normalized_name 或 node_definition。
- 目标 XLSX 被 Excel 锁定时数据库提交不回滚，并返回 EXPORT_LOCKED。
- CLI 退出码：0 成功，2 可恢复暂停，3 业务或数据质量失败，4 启动配置错误。
- README 中的目录和命令都能在当前公开项目中找到，只描述当前行为。

---

### Task 7: 全量验收并推送 GitHub

**Files**

- Verify: <code>src/</code>、<code>tests/</code>、<code>scripts/</code>、<code>README.md</code>、<code>docs/</code>
- Push: <code>https://github.com/AfterMaxQ/CNINFO.git</code>

**Work**

- [ ] 运行全部非 MySQL 单元测试。
- [ ] 在一次性 MySQL 测试 schema 运行 migration、表联动和节点事务测试。
- [ ] 使用专用已登录 Chrome 做 EVA 最小在线冒烟，不扩大到过度验证。
- [ ] 执行 --export-now 并检查 result.xlsx 九列、超链接、主题首行备注和空简称全称兜底行为。
- [ ] 检查 README 目录树与当前公开文件一致，删除开发过程和旧版本措辞。
- [ ] 检查 Git 暂存范围，不提交 data/runs、data/processed、export/*.xlsx、缓存或凭据。
- [ ] 工作区干净且全部验收通过后推送 main。
- [ ] 比较本地 HEAD、origin/main 和 git ls-remote 返回的 refs/heads/main SHA。

**Commands**

~~~powershell
python -m pytest -m "not mysql" -q
python -m pytest -m mysql -q
python -m cninfo_chain doctor
python -m cninfo_chain --export-now
rg -n "本次新增|原来|此前|旧版|修改后|下一步|后续将|评审反馈|迁移过程" README.md
git status --short
git push -u origin main
$localSha = (git rev-parse HEAD).Trim()
$remoteSha = (git ls-remote origin refs/heads/main).Split([char]9)[0]
if ($localSha -ne $remoteSha) { throw "Remote SHA mismatch." }
~~~

**Acceptance**

- 离线测试、MySQL 集成测试和 Chrome 冒烟均通过。
- 6 张表、45 个字段和所有中文注释已在实际 MySQL 中验证。
- 全站任务未完整成功时不标记 complete。
- 本地 HEAD、跟踪分支和远端 main SHA 一致。

## 完成条件

- Windows 单机采集、MySQL 节点事务、断点恢复和九字段 XLSX 均可实际运行。
- 真实 JSON 样本数量、分页、节点定义、简称和去重规则全部有测试覆盖。
- 数据模型保持 6 张表，不增加严格溯源表。
- README 只描述当前项目状态，目录树与公开文件一致。
- 验收通过的 main 已推送到指定 GitHub 空仓库。
