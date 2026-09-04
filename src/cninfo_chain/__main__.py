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
from cninfo_chain.runner import CollectorRunner, safe_error_message
from cninfo_chain.storage import MySQLStore


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
    return parser


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
            store.migrate()
            path = XlsxExporter(store, settings.export_path).export()
            print(json.dumps({"status": "ok", "export_path": str(path)}, ensure_ascii=False))
            return 0
        if args.command == "doctor":
            print(json.dumps(doctor(settings, store), ensure_ascii=False))
            return 0
        if args.command == "status":
            store.assert_schema_current()
            result = store.get_run(args.run_id)
            if result is None:
                raise CollectorError(f"run not found: {args.run_id}")
            print(json.dumps(result, ensure_ascii=False, default=str))
            return 0
        if args.command == "crawl":
            doctor(settings, store)
            exporter = XlsxExporter(store, settings.export_path)
            with connect_browser(settings.cdp_url) as browser:
                runner = CollectorRunner(
                    store,
                    browser,
                    settings.raw_dir,
                    page_size=settings.page_size,
                    on_theme_complete=lambda _: exporter.export(),
                )
                run_id = runner.crawl_all() if args.all else runner.resume(args.resume)
            path = exporter.export(run_id=run_id)
            print(
                json.dumps(
                    {"status": "ok", "run_id": run_id, "export_path": str(path)},
                    ensure_ascii=False,
                )
            )
            return 0
        raise ValueError("unknown command")
    except (AuthenticationPaused, KeyboardInterrupt) as error:
        print(safe_error_message(error), file=sys.stderr)
        return 2
    except CollectorError as error:
        print(safe_error_message(error), file=sys.stderr)
        return 3
    except (ValueError, pymysql.MySQLError, PlaywrightError) as error:
        print(safe_error_message(error), file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
