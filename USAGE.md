# CNINFO 产业链采集器使用说明

本文是当前项目的完整操作手册。请按章节顺序执行，不要跳过“配置”“启动专用 Chrome”和“doctor”步骤。所有命令均在项目根目录 `cninfo-chain-explorer` 执行，示例使用 Windows PowerShell 或 Windows Terminal，不依赖 VSCode。

## 1. 当前运行方式

这是一个 Windows 单机批处理程序：

- 业务人员在专用 Chrome 中登录 CNINFO 产业分析系统。
- Python 进程通过本机 `127.0.0.1:9222` 连接这个 Chrome，并在页面上下文中调用同源接口。
- 产业链主题、节点、企业和运行状态写入 MySQL。
- 每个主题完成后重建一次九字段 XLSX，全站结束后再生成最终文件。
- `--export-now` 只读 MySQL 重建 XLSX，不连接 Chrome，也不发网络请求。

当前不包含服务端、定时调度、任务队列或管理后台。

当前采集只请求年报产品和上市公司检索接口。公司列只输出当前节点具有上市证据的非空 `company_short_name`；没有明确简称时写入 `NULL`，不使用企业全称兜底。

企业接口必须分页请求。程序内部使用接口需要的单页大小，并根据响应中的总数和总页数自动遍历所有页面；单页大小不是企业总量限制，用户不需要配置或调整它。

采集过程中会在终端持续打印简洁中文进度，例如 `[预检]`、`[发现]`、`[主题]`、`[节点]`、`[续跑]` 和 `[导出]`。最终结果仍会输出一行 JSON，便于复制或被其他脚本读取。

## 2. 环境要求

- Windows 10/11。
- Python 3.11 或更高版本。
- Google Chrome。
- MySQL 8.0 或兼容版本，数据库使用 `utf8mb4`。

Chrome、MySQL 和 Python 应安装在运行采集任务的同一台 Windows 机器上。

项目日常运行不需要管理员权限。只有安装软件或电脑安全策略禁止脚本时，才需要管理员或 IT 协助；不要为了运行采集器把普通终端改成管理员终端。

## 3. 安装项目

在项目根目录的普通 PowerShell 或 Windows Terminal 中执行：

```powershell
py -3.11 -m venv .venv
```

如果 `py` 命令不存在，改用：

```powershell
python -m venv .venv
```

创建环境后，先激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

激活成功后，安装项目依赖：

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

如果 PowerShell 阻止执行虚拟环境脚本，只对当前窗口临时放开（不需要管理员权限），再重复激活命令：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

如果使用的是 `cmd.exe` 而不是 PowerShell，激活命令改为：

```bat
.\.venv\Scripts\activate.bat
```

项目通过 CDP 连接本机已安装的 Chrome，不需要额外执行 `playwright install`。

## 4. MySQL 自动初始化

采集器不会启动 MySQL 服务本身，请先确认服务正在运行：

```powershell
Get-Service MySQL* | Select-Object Name, Status
```

至少有一个 MySQL 服务的 `Status` 为 `Running`。如果服务是 `Stopped`，可在 Windows“服务”中启动；启动系统服务可能需要管理员权限，请联系 IT，不要为了运行采集器修改数据库权限。

不需要手工执行 `CREATE DATABASE` 或六张表的建表 SQL。程序使用 `config.yaml` 中的 MySQL 账号，在首次执行 `doctor` 或 `--export-now` 时自动完成：

1. 目标数据库不存在时，执行 `CREATE DATABASE IF NOT EXISTS`，字符集为 `utf8mb4`。
2. 目标数据库存在时，直接复用该数据库。
3. 执行项目 migration，创建六张业务及运行表并写入中文表、字段注释。
4. 校验表结构和注释，发现部分表或不兼容结构时停止，不删除已有数据。

默认配置使用 `root / 12345`，该账号通常具备建库建表权限。若改用权限受限的专用账号，需要由数据库管理员预先授予建库权限（数据库已存在时至少需要目标库的建表、查询和写入权限）。程序不会创建第二个 MySQL 账号。

首次执行 `doctor` 时，程序会在该数据库中创建以下六张表，并检查表结构和中文注释：

| 表 | 作用 |
| --- | --- |
| `industry_chain` | 产业链主题和目录顺序 |
| `industry_chain_node` | 节点、完整路径、定义、行业编码和数据状态 |
| `company` | 企业原名、明确简称、CNINFO 企业 ID、股票代码和上市状态 |
| `industry_chain_company` | 节点与企业的当前关系、来源顺序和节点级上市状态 |
| `crawl_run` | 一次采集运行的状态和导出位置 |
| `crawl_node_task` | 运行中每个节点的状态、重试次数和错误信息 |

如果目标数据库中只存在部分采集器表，或表结构/字段注释不符合当前 migration，程序会停止并提示错误，不会自动删除已有表。

MySQL 的业务状态由 MySQL 数据目录持久化保存，不保存在 Python 进程内存中。只要正式数据库的数据目录没有被删除，程序重启或 MySQL 服务重启后，运行记录、节点结果和企业关系都会保留。正式环境不要把数据库放在 Windows 临时目录。

## 5. 填写 YAML 配置

直接编辑项目根目录的 `config.yaml`。默认配置为 MySQL `root` 用户、密码 `12345`、数据库 `cninfo_chain`；正式运行前请替换为实际账号密码。

配置文件分为3组：

```yaml
mysql:
  host: 127.0.0.1
  port: 3306
  user: root
  password: "12345"
  database: cninfo_chain

chrome:
  cdp_url: http://127.0.0.1:9222

paths:
  raw_dir: data/runs
  export_path: export/result.xlsx
```

## 6. 可选环境变量覆盖

配置优先级为：内置默认值 → YAML 文件 → 环境变量。默认读取项目根目录的 `config.yaml`；需要使用其他文件时设置 `CNINFO_CONFIG_FILE`：

```powershell
$env:CNINFO_CONFIG_FILE = ".\config.production.yaml"
```

环境变量也可以覆盖 YAML 中的具体配置项：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CNINFO_CONFIG_FILE` | `config.yaml` | YAML 配置文件路径 |
| `CNINFO_MYSQL_HOST` | `127.0.0.1` | MySQL 地址 |
| `CNINFO_MYSQL_PORT` | `3306` | MySQL 端口 |
| `CNINFO_MYSQL_USER` | `root` | MySQL 用户 |
| `CNINFO_MYSQL_PASSWORD` | `12345` | MySQL 密码 |
| `CNINFO_MYSQL_DATABASE` | `cninfo_chain` | MySQL 数据库 |
| `CNINFO_CDP_URL` | `http://127.0.0.1:9222` | Chrome 调试地址；当前实现要求使用本机 9222 端口 |
| `CNINFO_RAW_DIR` | `data/runs` | 每次运行保存的原始接口响应目录 |
| `CNINFO_EXPORT_PATH` | `export/result.xlsx` | 九字段 XLSX 输出路径 |

例如临时使用测试数据库：

```powershell
$env:CNINFO_MYSQL_DATABASE = "cninfo_chain_test"
$env:CNINFO_MYSQL_PORT = "3307"
$env:CNINFO_RAW_DIR = "data\runs"
$env:CNINFO_EXPORT_PATH = "export\result.xlsx"
```

密码来自 YAML 或环境变量，不写入配置摘要、日志、原始 JSON、MySQL 业务字段或 XLSX。关闭 PowerShell 窗口后，环境变量会失效；YAML 文件仍然保留配置。

## 7. 启动并登录专用 Chrome

执行 `doctor`、`crawl --all` 或 `crawl --resume` 之前，必须先启动项目专用 Chrome。采集命令不会自动启动 Chrome，也不会使用普通 Chrome 的登录窗口；如果 9222 端口没有监听，会报 `connect ECONNREFUSED 127.0.0.1:9222`。

使用项目脚本启动专用 Chrome：

```powershell
# 当前目录为 cninfo-chain-explorer
.\scripts\start_cninfo_chrome.ps1
```

执行后会新打开一个 Chrome 窗口；脚本本身执行完返回 PowerShell 是正常现象，Chrome 窗口会继续运行。该窗口使用独立的 `CNINFOChromeProfile` 用户目录，并自动打开 CNINFO 产业分析系统页面。

如果 PowerShell 提示禁止运行脚本，只对当前终端临时放开权限后重试：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\start_cninfo_chrome.ps1
```

如果公司组策略仍然禁止脚本，不要反复修改系统执行策略；请让 IT 放行该脚本，或使用公司批准的 PowerShell 终端。项目运行本身不要求管理员权限。

脚本会：

- 使用 `%LOCALAPPDATA%\CNINFOChromeProfile` 作为独立用户目录。
- 使用 `127.0.0.1:9222` 开启本机 CDP。
- 打开 CNINFO 产业分析系统页面。

首次启动后，在新打开的 Chrome 窗口中完成 CNINFO 登录，并保持至少一个 `pis.cninfo.com.cn` 页面打开。采集期间不要关闭这个窗口；普通 Chrome 窗口不能替代项目专用 Chrome。

确认 CDP 端口已就绪：

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/version
```

能返回 Chrome 版本信息后，再进入下一节执行 `doctor`。

如果需要指定专用目录：

```powershell
.\scripts\start_cninfo_chrome.ps1 -ProfileDir "$env:LOCALAPPDATA\CNINFOChromeProfile"
```

如果 9222 端口已被其他调试进程占用，先关闭占用该端口的进程，再重新运行启动脚本。当前程序只接受 `http://127.0.0.1:9222`，不会连接远程或非回环地址。

## 8. 启动前预检

确保虚拟环境已激活、MySQL 已启动、YAML 配置已填写，且专用 Chrome 已启动、已登录并通过上一节的 CDP 检查，然后执行：

```powershell
python -m cninfo_chain doctor
```

安装成功后也可以使用命令入口：

```powershell
cninfo-chain doctor
```

如果没有激活虚拟环境，统一使用项目虚拟环境中的解释器：

```powershell
.\.venv\Scripts\python.exe -m cninfo_chain doctor
```

预检会依次检查：

1. MySQL 连接。
2. 六张表是否存在且结构、中文注释正确；首次运行时执行 migration。
3. Chrome CDP 是否可连接。
4. 页面内桥接是否就绪。
5. CNINFO 登录态和根目录主题接口是否可用。

成功时返回 JSON，`status` 为 `ok`。预检失败时先按错误信息处理，不要直接开始全站采集。

## 9. 全主题采集

预检成功后启动新的全主题运行：

```powershell
python -m cninfo_chain crawl --all
```

或：

```powershell
cninfo-chain crawl --all
```

程序会先读取主题目录和节点树，然后按主题、节点顺序依次采集。每个节点完成接口分页和数量校验后，在一个 MySQL 事务中提交；单个主题的全部节点完成后重建一次 XLSX。

全部节点成功时输出类似：

```json
{"status":"complete","run_id":"<run_id>","export_path":"export\\result.xlsx"}
```

请保存 `run_id`，后续查询状态或恢复运行时需要使用它。

可以使用 `Ctrl+C` 中断当前进程。已提交节点不会回滚，运行会记录为可恢复状态。

如果有节点失败，命令仍会导出当前已成功提交的数据，并输出 `status=partial`，进程返回码为 `3`；使用相同的 `run_id` 执行 `crawl --resume`。

## 10. 查看运行状态

```powershell
python -m cninfo_chain status <run_id>
```

状态输出包含运行状态、节点总数、已完成节点数、失败节点数和最近错误信息。运行状态包括：

| 状态 | 含义 |
| --- | --- |
| `running` | 正在采集 |
| `paused` | 被中断，可恢复 |
| `paused_auth` | 登录态失效或认证暂停 |
| `partial` | 部分节点失败或未完成 |
| `complete` | 全部节点完成 |
| `failed` | 运行级错误 |

节点任务的成功终态为 `committed` 或 `committed_empty`。恢复运行时，这些节点会跳过。

采集命令的退出码：

| 退出码 | 含义 |
| ---: | --- |
| `0` | 运行完整成功（`complete`） |
| `2` | 登录态失效或手动中断，运行可恢复 |
| `3` | 运行结束但存在失败节点或数据质量问题（`partial`） |
| `4` | 配置、MySQL 结构或启动检查错误 |

## 11. 恢复中断或部分失败的运行

先确保 Chrome 重新登录并通过预检，再使用原来的 `run_id`：

```powershell
python -m cninfo_chain crawl --resume <run_id>
```

恢复命令只处理该运行中尚未成功提交的节点，不重新创建运行，也不重复采集已经处于成功终态的节点。恢复成功后输出 `status=complete`；仍有失败节点时输出 `status=partial` 并返回 `3`。

如果错误是登录态失效：

1. 在专用 Chrome 中重新登录 CNINFO。
2. 保持 CNINFO 页面打开。
3. 执行 `python -m cninfo_chain doctor`。
4. 使用原 `run_id` 执行 `crawl --resume`。

## 12. 手动重建 XLSX

只根据 MySQL 当前成功数据重建 XLSX：

```powershell
python -m cninfo_chain --export-now
```

该命令不会连接 Chrome，也不会请求 CNINFO。适用于：

- 关闭被 Excel 占用的输出文件后重新导出。
- 手工确认数据库数据后重新生成交付文件。
- 采集完成但上一次导出被文件锁阻止。

输出路径由 `CNINFO_EXPORT_PATH` 决定，默认是 `export\result.xlsx`。

如果出现 `target XLSX is locked`：

1. 关闭 Excel 或其他正在预览该文件的程序。
2. 不需要重新采集。
3. 重新执行 `python -m cninfo_chain --export-now`。

## 13. XLSX 输出规则

工作表固定为九列：

```text
主题、信源主体、分类1、分类2、分类3、分类4、公司、信源URL、备注
```

- 一行对应一个产业链节点，不是一家公司一行。
- 父节点、无企业节点和无行业编码节点仍保留。
- 公司列只拼接上市证据企业的非空 `company_short_name`，按来源顺序去重后使用顿号连接。
- 若数据库中存在非上市记录，其没有明确简称时 `company_short_name` 为 `NULL`，不使用 `company_name` 全称代替，也不进入公司列。
- `信源URL` 为当前节点 CNINFO 页面地址，并生成可点击超链接。
- 每个主题只在该主题第一行填写来源备注。

## 14. 运行产物

默认产物位置：

```text
data/runs/<run_id>/       # 本次运行的原始接口 JSON
export/result.xlsx        # 当前数据库状态生成的九字段 XLSX
```

`data/runs/` 和 `export/*.xlsx` 是运行产物，不提交到 Git。raw JSON 不包含 Cookie、Authorization、token、sign 或密码。

## 15. 常见问题

### 配置文件不存在或配置项无效

默认会使用内置配置；如果指定了 `CNINFO_CONFIG_FILE`，确认路径存在、YAML 格式正确，并且 `mysql.host`、`mysql.user`、`mysql.password`、`mysql.database` 非空。环境变量覆盖项为空时也会导致配置错误。

### 无法连接 Chrome 或提示打开登录页面

如果看到 `connect ECONNREFUSED 127.0.0.1:9222`，说明专用 Chrome 尚未启动或已被关闭。先在项目目录执行：

```powershell
.\scripts\start_cninfo_chrome.ps1 -ProfileDir "$env:LOCALAPPDATA\CNINFOChromeProfile"
```

等待窗口打开后，用 `Invoke-RestMethod http://127.0.0.1:9222/json/version` 确认端口，再执行 `doctor` 和采集命令。

确认：

- 使用的是 `scripts\start_cninfo_chrome.ps1` 打开的专用窗口。
- 窗口中已经登录 CNINFO。
- 至少有一个 `pis.cninfo.com.cn` 页面保持打开。
- 9222 端口没有被其他进程占用。
- `CNINFO_CDP_URL` 没有改成远程地址或其他端口。

### 提示 `CNINFO schema must contain exactly the six required tables`

目标数据库已有部分表或结构不匹配。选择一个专用空数据库重新配置 `CNINFO_MYSQL_DATABASE`，不要在已有业务表上直接改名或删除。

### 运行显示 `paused_auth`

登录态已失效或接口返回认证错误。重新登录专用 Chrome，先通过 `doctor`，再使用相同 `run_id` 执行 `crawl --resume`。

### 运行显示 `partial` 或存在失败节点

执行 `status <run_id>` 查看失败数量和错误信息。确认 Chrome、MySQL 和网络状态正常后，使用相同 `run_id` 执行 `crawl --resume`。

### 只有数据库没有 XLSX，或 XLSX 不是最新结果

采集提交和文件导出是两个步骤。关闭占用文件的程序后执行：

```powershell
python -m cninfo_chain --export-now
```

## 16. 本地测试

开发或升级后，在项目根目录运行：

```powershell
python -m pytest -q
python -m compileall -q src tests
node --check src/cninfo_chain/bridge.js
```

测试使用仓库中的脱敏接口样本，覆盖接口解析、企业去重、MySQL DDL 注释、节点事务、断点恢复、Chrome 桥接和九字段 XLSX 导出。
