from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

import pymysql
from playwright.sync_api import Error as PlaywrightError

from cninfo_chain.browser import connect_browser, doctor
from cninfo_chain.config import Settings
from cninfo_chain.errors import AuthenticationPaused, CollectorError
from cninfo_chain.exporter import XlsxExporter
from cninfo_chain.reference import (
    build_reference_preview,
    replace_reference_table,
)
from cninfo_chain.runner import CollectorRunner, safe_error_message
from cninfo_chain.securities import load_akshare_rows, parse_akshare_rows
from cninfo_chain.storage import MySQLStore


def console_log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cninfo-chain")
    parser.add_argument(
        "--export-now",
        action="store_true",
        help="仅从 MySQL 原子重建九字段 XLSX",
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor", help="检查 MySQL、Chrome 登录态和根目录接口")
    crawl = commands.add_parser("crawl", help="采集全站或恢复已有运行")
    mode = crawl.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true", help="新建全主题采集运行")
    mode.add_argument("--resume", metavar="RUN_ID", help="恢复指定运行")
    status = commands.add_parser("status", help="查看运行状态")
    status.add_argument("run_id")
    reference = commands.add_parser("reference", help="初始化或刷新本地 A 股证券参考表")
    reference_commands = reference.add_subparsers(dest="reference_command", required=True)
    reference_commands.add_parser("init", help="首次初始化参考表")
    reference_commands.add_parser("refresh", help="重新抓取并刷新参考表")
    return parser


def _print_reference_preview(preview) -> None:
    console_log(
        "[参考表] 预览：总数={total}，沪={sh}，深={sz}，北={bj}，"
        "无效={invalid}，重复={duplicate}".format(
            total=preview.total,
            sh=preview.sh_count,
            sz=preview.sz_count,
            bj=preview.bj_count,
            invalid=preview.invalid_count,
            duplicate=preview.duplicate_count,
        )
    )
    for row in preview.sample_rows:
        console_log(
            f"[参考表] 示例：{row.security_name} {row.full_code} {row.akshare_symbol}"
        )


def _run_reference_command(store: MySQLStore, command: str) -> int:
    store.migrate()
    existing_count = store.a_share_security_count()
    if command == "init" and existing_count:
        raise CollectorError(
            f"A 股参考表已有 {existing_count} 条记录，请使用 reference refresh"
        )
    console_log("[参考表] 正在读取 AkShare A 股列表")
    rows = parse_akshare_rows(load_akshare_rows())
    preview = build_reference_preview(rows)
    _print_reference_preview(preview)
    try:
        answer = input("[参考表] 确认写入请输入 CONFIRM，其他输入取消：").strip()
    except EOFError:
        answer = ""
    if answer != "CONFIRM":
        console_log("[取消] 未写入参考表")
        return 2
    written = replace_reference_table(store, rows)
    console_log(f"[参考表] 写入完成：{written} 条")
    print(json.dumps({"status": "ok", "count": written}, ensure_ascii=False))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.export_now and args.command is None:
        parser.print_help(sys.stderr)
        return 4
    if args.export_now and args.command is not None:
        print("--export-now cannot be combined with a command", file=sys.stderr)
        return 4
    try:
        settings = Settings.from_env()
        store = MySQLStore(settings)
        if args.export_now:
            console_log("[导出] 正在从 MySQL 重建 XLSX")
            store.migrate()
            path = XlsxExporter(store, settings.export_path).export()
            console_log(f"[导出] 完成：{path}")
            print(json.dumps({"status": "ok", "export_path": str(path)}, ensure_ascii=False))
            return 0
        if args.command == "doctor":
            console_log("[预检] 正在检查 MySQL、Chrome 和 CNINFO 登录态")
            print(json.dumps(doctor(settings, store), ensure_ascii=False))
            console_log("[预检] 通过")
            return 0
        if args.command == "status":
            store.assert_schema_current()
            result = store.get_run(args.run_id)
            if result is None:
                raise CollectorError(f"run not found: {args.run_id}")
            print(json.dumps(result, ensure_ascii=False, default=str))
            return 0
        if args.command == "reference":
            return _run_reference_command(store, args.reference_command)
        if args.command == "crawl":
            console_log("[预检] 正在检查 MySQL、Chrome 和 CNINFO 登录态")
            doctor(settings, store)
            console_log("[预检] 通过")
            exporter = XlsxExporter(store, settings.export_path)

            def export_theme(chain_id: str) -> None:
                path = exporter.export()
                console_log(f"[导出] 主题 {chain_id} 已更新：{path}")

            with connect_browser(settings.cdp_url) as browser:
                runner = CollectorRunner(
                    store,
                    browser,
                    settings.raw_dir,
                    page_size=settings.page_size,
                    on_theme_complete=export_theme,
                    on_log=console_log,
                )
                run_id = runner.crawl_all() if args.all else runner.resume(args.resume)
            console_log("[导出] 正在生成最终 XLSX")
            path = exporter.export(run_id=run_id)
            console_log(f"[导出] 最终文件：{path}")
            run = store.get_run(run_id)
            if run is None:
                raise CollectorError(f"run not found after crawl: {run_id}")
            status = str(run["status"])
            print(
                json.dumps(
                    {"status": status, "run_id": run_id, "export_path": str(path)},
                    ensure_ascii=False,
                )
            )
            return 0 if status == "complete" else 3
        raise ValueError("unknown command")
    except (AuthenticationPaused, KeyboardInterrupt) as error:
        console_log(f"[暂停] {safe_error_message(error)}")
        return 2
    except CollectorError as error:
        console_log(f"[错误] {safe_error_message(error)}")
        return 3
    except (ValueError, pymysql.MySQLError, PlaywrightError) as error:
        console_log(f"[启动错误] {safe_error_message(error)}")
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
