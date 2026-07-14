from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from prettytable import PrettyTable

from screener.screeners.base import Signal


def format_results_table(results: list[dict[str, Any]]) -> str:
    table = PrettyTable()
    passes = [r for r in results if r.get("signal") == Signal.BUY]

    if not passes:
        return "No stocks matched the screening criteria."

    columns = ["Ticker", "Last Price", "Signal", "Reason"]
    extra_cols = []
    for r in passes:
        for k in r:
            if k not in ("ticker", "last_price", "signal", "reason") and k not in extra_cols:
                extra_cols.append(k)
    columns[3:3] = extra_cols

    table.field_names = columns
    table.align = "r"
    table.align["Ticker"] = "l"
    table.align["Reason"] = "l"

    for r in passes:
        row = [
            r.get("ticker", ""),
            r.get("last_price", ""),
            r.get("signal", ""),
        ]
        for col in extra_cols:
            row.append(r.get(col, ""))
        row.append(r.get("reason", ""))
        table.add_row(row)

    table.title = f"Results: {len(passes)} / {len(results)} stocks matched"
    return table.get_string()


def export_csv(results: list[dict[str, Any]], path: str | Path) -> None:
    df = pd.DataFrame(results)
    df.to_csv(path, index=False)
