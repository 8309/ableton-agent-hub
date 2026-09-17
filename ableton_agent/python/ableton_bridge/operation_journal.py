from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


MAX_RECEIPTS = 64


class OperationJournalError(RuntimeError):
    pass


def default_journal_path() -> Path:
    configured = os.environ.get("ABLETON_AGENT_OPERATION_JOURNAL")
    if configured:
        return Path(configured)
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return root / "AbletonAgentHub" / "operation_journal.json"


def append_receipt(receipt: dict[str, Any], *, path: Path | None = None, limit: int = MAX_RECEIPTS) -> Path:
    if not receipt.get("operation_id") or not receipt.get("route"):
        raise OperationJournalError("undo receipt requires operation_id and route")
    target = path or default_journal_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    records = _load_records(target)
    records = [item for item in records if item.get("operation_id") != receipt["operation_id"]]
    records.append(receipt)
    records = records[-max(1, int(limit)) :]
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps({"version": 1, "receipts": records}, indent=2), encoding="utf-8")
        temporary.replace(target)
    except OSError as error:
        raise OperationJournalError(f"cannot write operation journal {target}: {error}") from error
    return target


def load_receipt(operation_id: str, *, path: Path | None = None) -> dict[str, Any]:
    target = path or default_journal_path()
    for receipt in reversed(_load_records(target)):
        if receipt.get("operation_id") == operation_id:
            return receipt
    raise OperationJournalError(f"operation receipt not found: {operation_id}")


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OperationJournalError(f"cannot read operation journal {path}: {error}") from error
    records = payload.get("receipts", [])
    if not isinstance(records, list):
        raise OperationJournalError(f"invalid operation journal {path}")
    return [item for item in records if isinstance(item, dict)]
