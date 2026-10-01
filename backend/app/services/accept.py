"""验收确认业务规则：状态流转、字段校验、幂等确认与台账回写都收在这里。

要点：
- 「确认通过」「下发返工」都是幂等的：同一份验收单重复提交只算一次，不重复写台账；
- 验收结论会回写到关联的检修任务台账，当前结论覆盖展示，历次结论与等级按时间
  顺序完整保留在「验收结论历史」里；
- 列表与详情共用 serialize() 输出，验收状态始终取内部 status，避免两处读到的值不一致。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "accept"
LEDGER_MODULE = "maintjob"
LEDGER_KEY_FIELD = "任务编号"
REQUIRED_FIELDS = ["验收单号", "关联任务", "验收项目"]
DISPLAY_FIELDS = ["验收单号", "关联任务", "验收项目", "验收标准", "验收结论", "验收人员", "验收日期"]

STATUS_WAITING = "待验收"
STATUS_IN_PROGRESS = "验收中"
STATUS_PASSED = "已通过"
STATUS_REWORK = "需返工"

ACTION_START = "开始验收"
ACTION_PASS = "确认通过"
ACTION_REWORK = "下发返工"
ACTION_RULES = {
    ACTION_START: STATUS_IN_PROGRESS,
    ACTION_PASS: STATUS_PASSED,
    ACTION_REWORK: STATUS_REWORK,
}

# 每个结论对应的验收等级，回写台账用。
GRADE_OF_ACTION = {ACTION_PASS: "合格", ACTION_REWORK: "不合格"}
DEFAULT_CONCLUSION = {
    ACTION_PASS: "验收通过",
    ACTION_REWORK: "验收不通过，需返工",
}


class AcceptService:
    # ---- 读取口径 ----

    def serialize(self, row: dict[str, Any]) -> dict[str, Any]:
        status = str(row.get("status") or STATUS_WAITING)
        item: dict[str, Any] = {"id": row.get("id")}
        for field in DISPLAY_FIELDS:
            item[field] = row.get(field)
        item["status"] = status
        item["验收状态"] = status
        item["pending"] = status in (STATUS_WAITING, STATUS_IN_PROGRESS)
        item["abnormal"] = status == STATUS_REWORK
        item["last_action"] = row.get("last_action")
        return item

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
            rows = [row for row in rows if str(row.get("status") or "") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self.serialize(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self.serialize(row) if row is not None else None

    # ---- 登记 ----

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values.get(field)).strip() for field in REQUIRED_FIELDS})
        entry["验收标准"] = str(values.get("验收标准") or "").strip()
        entry["验收结论"] = ""
        entry["验收人员"] = str(values.get("验收人员") or "").strip()
        entry["验收日期"] = ""
        entry["status"] = STATUS_WAITING
        entry["pending"] = True
        entry["abnormal"] = False
        entry["last_action"] = None
        rows.append(entry)
        return self.serialize(entry), []

    # ---- 状态流转 ----

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"验收单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于验收确认可执行范围"

        values = values or {}
        current = str(entry.get("status") or STATUS_WAITING)

        if action == ACTION_START:
            if current == STATUS_IN_PROGRESS:
                return self.serialize(entry), "该验收单已在验收中，无需重复开始"
            if current in (STATUS_PASSED, STATUS_REWORK):
                return None, f"验收单当前为「{current}」，不能重新开始验收"
            entry["status"] = STATUS_IN_PROGRESS
            entry["pending"] = True
            entry["last_action"] = ACTION_START
            return self.serialize(entry), "验收已开始"

        return self._finish(entry, current, action, values)

    def _finish(
        self,
        entry: dict[str, Any],
        current: str,
        action: str,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        target = ACTION_RULES[action]

        # 幂等：结论动作重复提交只算一次，台账历史不追加重复记录。
        if current == target and entry.get("last_action") == action:
            return self.serialize(entry), f"该验收单已{action}，重复提交不会重复记录"
        if current == STATUS_PASSED:
            return None, "该验收单已确认通过并归档，不能再重复提交结论"
        if current == STATUS_WAITING:
            return None, "请先开始验收，再提交验收结论"

        try:
            finished_on = _parse_date(values.get("验收日期") or entry.get("验收日期")).isoformat()
        except ValueError as exc:
            return None, str(exc)

        conclusion = str(
            values.get("验收结论") or entry.get("验收结论") or DEFAULT_CONCLUSION[action]
        ).strip()
        inspector = str(values.get("验收人员") or entry.get("验收人员") or "值班验收员").strip()

        # 回写关联检修任务台账：当前结论更新为最新值，历史等级完整保留。
        ledger = store.find_by_field(LEDGER_MODULE, LEDGER_KEY_FIELD, str(entry.get("关联任务")))
        if ledger is None:
            return None, (
                f"关联任务「{entry.get('关联任务')}」在检修任务台账中不存在，"
                "验收结论无法回写，请核对关联任务编号"
            )

        grade = GRADE_OF_ACTION[action]
        history = ledger.setdefault("验收结论历史", [])
        history.append({
            "验收单号": entry.get("验收单号"),
            "结论": conclusion,
            "等级": grade,
            "验收人员": inspector,
            "验收日期": finished_on,
        })
        ledger["验收结论"] = conclusion
        ledger["验收等级"] = grade
        ledger["验收人员"] = inspector
        ledger["验收日期"] = finished_on

        entry["验收结论"] = conclusion
        entry["验收人员"] = inspector
        entry["验收日期"] = finished_on
        entry["status"] = target
        entry["pending"] = False
        entry["abnormal"] = action == ACTION_REWORK
        entry["last_action"] = action
        return self.serialize(entry), f"验收结论已提交并回写检修任务台账（等级：{grade}）"


def _parse_date(value: Any) -> date:
    text = str(value or "").strip()
    if not text:
        return date.today()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            f"验收日期格式不正确，请使用 YYYY-MM-DD（例如 {date.today().isoformat()}）"
        ) from None
