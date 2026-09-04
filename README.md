# CNINFO 产业链采集器

面向 Windows 业务人员的 CNINFO 全主题批处理工具。程序连接业务人员已登录的专用 Chrome，从 CNINFO 产业分析系统读取产业链、节点和企业接口数据，按节点原子写入 MySQL，并生成固定九字段 XLSX。

## 环境要求

- Windows 10/11
- Python 3.11 或更高版本
- Google Chrome
- MySQL 8.0，数据库字符集建议使用 `utf8mb4`

安装项目：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

## MySQL 配置

先创建一个供采集器独占表名的数据库，并授予采集账号建表、查询和写入权限。程序首次执行 `doctor` 时会创建 6 张业务及运行表；遇到部分同名表或不兼容结构时会停止，不会自动删除或修改已有表。

在启动命令的 PowerShell 会话中设置：

```powershell
$env:CNINFO_MYSQL_HOST = "127.0.0.1"
$env:CNINFO_MYSQL_PORT = "3306"
$env:CNINFO_MYSQL_USER = "cninfo_collector"
$env:CNINFO_MYSQL_PASSWORD = "请替换为实际密码"
$env:CNINFO_MYSQL_DATABASE = "cninfo_chain"
```

可选配置：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CNINFO_CDP_URL` | `http://127.0.0.1:9222` | Chrome 调试地址，只允许本机回环地址 |
| `CNINFO_RAW_DIR` | `data/runs` | 运行期接口响应目录 |
| `CNINFO_EXPORT_PATH` | `export/result.xlsx` | 九字段 XLSX 输出位置 |
| `CNINFO_PAGE_SIZE` | `15` | 企业分页大小 |

密码只从环境变量读取，不进入配置摘要、raw JSON、MySQL 业务字段或 XLSX。

## 启动已登录 Chrome

运行专用启动脚本：

```powershell
.\scripts\start_cninfo_chrome.ps1
```

脚本使用 `%LOCALAPPDATA%\CNINFOChromeProfile` 作为独立浏览器目录，并将调试端口限制在 `127.0.0.1:9222`。首次打开后，在该 Chrome 窗口中登录 CNINFO 并保持产业分析系统页面打开。采集器通过页面内桥接复用同源请求上下文，认证头不会返回 Python。

## 使用命令

先执行预检：

```powershell
cninfo-chain doctor
```

预检会验证 MySQL 表结构、Chrome 页面与登录态，以及 CNINFO 根目录接口。

手动启动全主题采集：

```powershell
cninfo-chain crawl --all
```

命令输出 `run_id`。需要从中断或失败节点继续时：

```powershell
cninfo-chain crawl --resume <run_id>
```

查看运行状态：

```powershell
cninfo-chain status <run_id>
```

只根据 MySQL 当前数据重建 XLSX，不连接 Chrome：

```powershell
cninfo-chain --export-now
```

节点完成后立即提交 MySQL。一个主题的全部节点成功后会原子重建一次 XLSX，全站完成后再生成最终文件。若 XLSX 正被 Excel 占用，数据库提交不受影响；关闭文件后执行 `--export-now` 即可。

## 数据表联动

| 表 | 用途 | 主要关联 |
| --- | --- | --- |
| `industry_chain` | 产业链主题和目录 | 一对多关联 `industry_chain_node` |
| `industry_chain_node` | 节点、完整路径、定义、行业编码和数据状态 | 自关联父节点；关联主题、企业关系和节点任务 |
| `company` | 企业原名、明确简称、CNINFO 企业 ID、股票代码和上市状态 | 多对多关联产业链节点 |
| `industry_chain_company` | 节点与企业的当前关系、节点级上市状态和来源顺序 | 连接 `industry_chain_node` 与 `company` |
| `crawl_run` | 一次全站采集的状态和导出位置 | 一对多关联 `crawl_node_task` |
| `crawl_node_task` | 每次运行中每个节点的进度、重试次数和错误 | 连接运行与节点 |

企业先在单个节点内按 CNINFO 企业 ID、股票代码、规范化原名依次去重，再写入全局 `company` 表。企业跨节点或跨主题出现时复用同一企业记录，通过多条 `industry_chain_company` 关系保留各自归属。上市和非上市接口同时命中时，关系及企业的 `listing_status` 为 `2`。

`company_short_name` 只映射接口明确提供的简称：年报取 `secname_one/secname_two`，上市检索取 `companyShortName`。非上市接口没有明确简称时写入 `NULL`，企业及节点关系仍正常保存。

全部 6 张表和 45 个字段都在 MySQL DDL 中带简洁中文 `COMMENT`。字段、约束和联表查询见 [技术设计](docs/superpowers/specs/2026-09-04-cninfo-full-chain-collection-design.md)。

## XLSX 输出

工作表固定包含：

```text
主题、信源主体、分类1、分类2、分类3、分类4、公司、信源URL、备注
```

- 一行对应一个节点，不是一家企业一行。
- 分类1为 `上游/中游/下游/其他`，节点路径依次写入分类2至分类4。
- 父节点、无企业节点和无行业编码节点都保留。
- 公司列优先写明确的 `company_short_name`；没有简称时写接口原始 `company_name`，保证企业不漏出，并按来源顺序去重后用顿号连接。
- 信源 URL 是可点击超链接；每个主题只有首行填写备注。

## 项目结构

```text
cninfo-chain-explorer/
├─ src/cninfo_chain/             采集、解析、MySQL、Chrome 桥和 XLSX 代码
├─ src/cninfo_chain/migrations/  MySQL 顺序 migration
├─ scripts/                      Chrome 启动脚本和接口探索工具
├─ tests/                        自动化测试
├─ data/raw/                     脱敏的真实接口测试样本
├─ docs/                         业务需求、接口参考、技术设计和执行计划
├─ api_report.md                 接口响应结构报告
└─ pyproject.toml                Python 包和命令入口
```

`data/runs/` 和 `export/*.xlsx` 是运行产物，不纳入 Git。

## 测试

```powershell
python -m pytest -q
```

测试使用 `data/raw/` 中的真实脱敏响应校验 134 个主题、124 个新能源节点、企业分页、简称映射、87 条候选合并为 85 家企业、MySQL DDL 注释、事务边界、断点恢复和九字段 XLSX。

接口参数和样本说明见 [API 报告](api_report.md) 与 [爬取实现参考](docs/cninfo-crawl-implementation-reference.md)。
