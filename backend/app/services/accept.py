"""验收确认业务规则：状态流转、结论回写台账与历史结论保留都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "accept"
REQUIRED_FIELDS = ["验收单号", "关联任务", "验收项目"]

STATUS_WAIT = "待验收"
STATUS_DOING = "验收中"
STATUS_PASS = "已通过"
STATUS_REWORK = "需返工"
STATUS_ORDER = [STATUS_WAIT, STATUS_DOING, STATUS_PASS, STATUS_REWORK]

# 已通过/需返工 属于办结状态，不再占用待处理量
PENDING_STATUSES = {STATUS_WAIT, STATUS_DOING}
VIEW_FIELDS = ["验收单号", "关联任务", "验收项目", "验收标准", "验收结论", "验收人员", "验收日期"]


def to_view(entry: dict[str, Any]) -> dict[str, Any]:
    """台账记录 -> 接口出参：列表页、详情页、导出统一口径。"""
    view: dict[str, Any] = {"id": entry.get("id")}
    for field in VIEW_FIELDS:
        view[field] = entry.get(field)
    view["验收状态"] = entry.get("status")
    # 结论历史只暴露副本，避免前端误改台账
    view["结论历史"] = [dict(item) for item in (entry.get("结论历史") or [])]
    return view


class AcceptService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("验收单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [to_view(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return to_view(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["验收标准"] = values.get("验收标准")
        entry["验收结论"] = values.get("验收结论")
        entry["验收人员"] = values.get("验收人员")
        entry["验收日期"] = values.get("验收日期")
        entry["status"] = STATUS_WAIT
        entry["pending"] = True
        entry["abnormal"] = False
        entry["结论历史"] = []
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"验收单 {entry_id} 不存在或已归档"
        status = entry.get("status")
        if action == "开始验收":
            return self._start(entry, status)
        if action == "确认通过":
            return self._pass(entry, status, values)
        if action == "下发返工":
            return self._rework(entry, status, values)
        return None, f"动作「{action}」不属于验收确认可执行范围"

    def _start(self, entry: dict[str, Any], status: Any) -> tuple[dict[str, Any] | None, str]:
        if status == STATUS_DOING:
            return entry, "该验收单已在验收中，无需重复开始"
        if status in (STATUS_PASS, STATUS_REWORK):
            return None, f"验收单已办结（{status}），不能重新开始验收"
        entry["status"] = STATUS_DOING
        entry["pending"] = True
        return entry, "验收已开始"

    def _pass(
        self,
        entry: dict[str, Any],
        status: Any,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        if status == STATUS_REWORK:
            return None, "验收单已下发返工，请先复验后重新出具结论"
        conclusion = str(values.get("验收结论") or "").strip() or "合格"
        inspector = str(values.get("验收人员") or entry.get("验收人员") or "").strip()
        if not inspector:
            return None, "保存失败：请填写验收人员"
        today = date.today().isoformat()

        # 幂等：同一结论、同一验收人员、同一天的重复提交只算一次，历史等级原样保留
        history = entry.setdefault("结论历史", [])
        if history:
            latest = history[-1]
            if (
                status == STATUS_PASS
                and latest.get("验收结论") == conclusion
                and latest.get("验收人员") == inspector
                and latest.get("验收日期") == today
            ):
                return entry, f"验收结论「{conclusion}」已回写台账，重复提交只算一次"

        record = {"验收结论": conclusion, "验收人员": inspector, "验收日期": today}
        history.append(record)
        entry["验收结论"] = conclusion
        entry["验收人员"] = inspector
        entry["验收日期"] = today
        entry["status"] = STATUS_PASS
        entry["pending"] = False
        entry["abnormal"] = False
        return entry, f"验收结论「{conclusion}」已回写台账，历史结论共 {len(history)} 条"

    def _rework(
        self,
        entry: dict[str, Any],
        status: Any,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        if status == STATUS_REWORK:
            return entry, "该验收单已下发返工，重复提交只算一次"
        if status == STATUS_PASS:
            return None, "验收单已通过，如需推翻结论请走复验流程"
        inspector = str(values.get("验收人员") or entry.get("验收人员") or "").strip()
        if not inspector:
            return None, "保存失败：请填写验收人员"
        today = date.today().isoformat()
        history = entry.setdefault("结论历史", [])
        if history:
            latest = history[-1]
            if (
                latest.get("验收结论") == "不合格"
                and latest.get("验收人员") == inspector
                and latest.get("验收日期") == today
            ):
                return entry, "返工结论已回写台账，重复提交只算一次"
        record = {"验收结论": "不合格", "验收人员": inspector, "验收日期": today}
        history.append(record)
        entry["验收结论"] = "不合格"
        entry["验收人员"] = inspector
        entry["验收日期"] = today
        entry["status"] = STATUS_REWORK
        entry["pending"] = False
        entry["abnormal"] = True
        return entry, "返工结论已回写台账，验收单状态更新为需返工"
