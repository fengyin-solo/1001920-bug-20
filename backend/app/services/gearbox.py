"""齿轮箱业务规则：换油、油温异常登记与更换的状态流转都收在这里。

列表、详情与导出共用 to_view 一份取数口径，保证各处读到的齿轮箱状态、
油温上限、下次换油日、油品型号与异常标记完全一致。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "gearbox"
REQUIRED_FIELDS = ["齿轮箱编号", "所属机组", "油温上限"]

STATUS_PENDING = "待换油"
STATUS_NORMAL = "运行正常"
STATUS_HOT = "油温偏高"
STATUS_REPLACED = "已更换"
STATUS_ORDER = [STATUS_PENDING, STATUS_NORMAL, STATUS_HOT, STATUS_REPLACED]

OIL_CHANGE_INTERVAL_DAYS = 365
VIEW_FIELDS = ["齿轮箱编号", "所属机组", "油温上限", "振动值", "上次换油日", "下次换油日", "油品型号"]


def to_view(entry: dict[str, Any]) -> dict[str, Any]:
    """台账记录 -> 接口出参：列表页、详情页、导出都走这一个口径，避免两边读数不一致。"""
    view: dict[str, Any] = {"id": entry.get("id")}
    for field in VIEW_FIELDS:
        view[field] = entry.get(field)
    view["齿轮箱状态"] = entry.get("status")
    view["油温异常"] = bool(entry.get("abnormal"))
    view["换油记录"] = list(entry.get("换油记录") or [])
    return view


class GearboxService:
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
            rows = [row for row in rows if keyword in str(row.get("齿轮箱编号", ""))]
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
        entry["振动值"] = values.get("振动值")
        entry["油品型号"] = values.get("油品型号")
        entry["status"] = STATUS_PENDING
        entry["pending"] = True
        entry["abnormal"] = False
        entry["换油记录"] = []
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
            return None, f"齿轮箱 {entry_id} 不存在或已归档"
        status = entry.get("status")
        if action == "确认换油":
            return self._confirm_oil_change(entry, status, values)
        if action == "登记油温异常":
            return self._mark_hot(entry, status)
        if action == "更换齿轮箱":
            return self._replace(entry, status)
        return None, f"动作「{action}」不属于齿轮箱可执行范围"

    def _confirm_oil_change(
        self,
        entry: dict[str, Any],
        status: Any,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        """确认换油：校验通过后，状态/油温上限/油品型号/异常标记一次性原子落库。"""
        if status == STATUS_REPLACED:
            return None, "齿轮箱已更换，不能再确认换油"
        # 幂等：已经是运行正常时直接返回最近一次换油结果，不新增记录、不回退状态
        if status == STATUS_NORMAL:
            last_date = entry.get("上次换油日") or "此前"
            return entry, f"该齿轮箱已于 {last_date} 完成换油，重复提交只算一次"

        oil_model = str(values.get("油品型号") or entry.get("油品型号") or "").strip()
        if not oil_model:
            return None, "保存失败：请填写更换后的油品型号"

        limit_text = str(values.get("油温上限") or "").strip()
        if not limit_text:
            return None, "保存失败：请填写油温上限"
        try:
            limit = float(limit_text)
        except ValueError:
            return None, f"保存失败：油温上限需为数字（摄氏度），当前填写「{limit_text}」"
        if not 0 < limit <= 200:
            return None, f"保存失败：油温上限 {limit:g}℃ 不在合理范围（0~200℃）内"
        if not limit.is_integer():
            limit = round(limit, 1)
        else:
            limit = int(limit)

        # 全部校验通过后才改台账，任一项不通过都不会留下半成状态
        today = date.today()
        next_day = today + timedelta(days=OIL_CHANGE_INTERVAL_DAYS)
        record = {
            "油温上限": limit,
            "油品型号": oil_model,
            "上次换油日": today.isoformat(),
            "下次换油日": next_day.isoformat(),
        }
        entry["油温上限"] = limit
        entry["油品型号"] = oil_model
        entry["上次换油日"] = record["上次换油日"]
        entry["下次换油日"] = record["下次换油日"]
        entry["status"] = STATUS_NORMAL
        entry["pending"] = False
        entry["abnormal"] = False  # 换油后油温异常标记同步清除
        entry.setdefault("换油记录", []).append(record)
        return entry, "换油已确认：状态、油温上限、油品型号与异常标记已一并更新"

    def _mark_hot(self, entry: dict[str, Any], status: Any) -> tuple[dict[str, Any] | None, str]:
        if status == STATUS_REPLACED:
            return None, "齿轮箱已更换，不能再登记油温异常"
        if status == STATUS_HOT:
            return entry, "该齿轮箱已登记油温异常，无需重复登记"
        entry["status"] = STATUS_HOT
        entry["pending"] = True
        entry["abnormal"] = True
        return entry, "油温异常已登记，请尽快安排换油"

    def _replace(self, entry: dict[str, Any], status: Any) -> tuple[dict[str, Any] | None, str]:
        if status == STATUS_REPLACED:
            return entry, "该齿轮箱已完成更换，重复提交只算一次"
        entry["status"] = STATUS_REPLACED
        entry["pending"] = False
        entry["abnormal"] = False
        return entry, "齿轮箱已更换"
