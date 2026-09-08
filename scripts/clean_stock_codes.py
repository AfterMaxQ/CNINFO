from __future__ import annotations

import argparse
import sys

from cninfo_chain.cleanup import cleanup_summary, execute_stock_code_cleanup
from cninfo_chain.config import Settings
from cninfo_chain.storage import MySQLStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="预览或清洗 CNINFO 企业股票代码")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="只预览，不写入数据库")
    mode.add_argument("--execute", action="store_true", help="显示预览并确认后执行清洗")
    return parser


def _print_preview(changes, invalid, total) -> None:
    print(
        f"[清洗] 总记录={total}，将修改={len(changes)}，无需修改={total - len(changes) - len(invalid)}，异常={len(invalid)}"
    )
    for change in changes[:10]:
        print(f"[清洗] 示例 company_id={change.company_id}: {change.old_value!r} -> {change.new_value!r}")
    for change in invalid[:10]:
        print(f"[清洗] 异常 company_id={change.company_id}: {change.old_value!r} ({change.reason})")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        store = MySQLStore(settings)
        store.migrate()
        changes, invalid, total = cleanup_summary(store)
        _print_preview(changes, invalid, total)
        if not args.execute or not changes:
            if args.execute and not changes:
                print("[清洗] 没有可更新的合法代码")
            return 0
        answer = input("[清洗] 确认执行请输入 CLEAN，其他输入取消：").strip()
        if answer != "CLEAN":
            print("[取消] 未更新数据库")
            return 2
        updated = execute_stock_code_cleanup(store, changes)
        print(f"[清洗] 完成：更新 {updated} 条，异常 {len(invalid)} 条")
        print("[下一步] python -m cninfo_chain --export-now")
        return 0
    except (KeyboardInterrupt, EOFError):
        print("[取消] 未更新数据库", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"[错误] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
