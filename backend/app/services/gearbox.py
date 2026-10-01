"""齿轮箱业务规则：状态流转、字段校验与筛选口径都收在这里。

设计要点：
- 列表与详情都走 serialize() 输出同一份口径，保证「齿轮箱状态」、油温上限、
  下次换油日等字段在任何页面读到的值一致；
- 「确认换油」在校验通过后一次性改定状态、油温上限、油品型号、上次/下次换油日
  与异常标记，不会留下半截更新；
- 动作按状态机执行并做幂等处理：重复确认只返回一次成功，不会把记录推回待换油。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.store import store

MODULE = "gearbox"
REQUIRED_FIELDS = ["齿轮箱编号", "所属机组", "油温上限"]
# 允许通过编辑接口修改的业务字段；status/pending/abnormal 等内部字段不在此列。
EDITABLE_FIELDS = ["所属机组", "油温上限", "振动值", "上次换油日", "下次换油日", "油品型号"]
DISPLAY_FIELDS = [
    "齿轮箱编号", "所属机组", "油温上限", "振动值",
    "上次换油日", "下次换油日", "油品型号",
]

STATUS_PENDING = "待换油"
STATUS_NORMAL = "运行正常"
STATUS_HIGH_TEMP = "油温偏高"
STATUS_REPLACED = "已更换"

ACTION_OIL_CHANGE = "确认换油"
ACTION_REPORT_HIGH_TEMP = "登记油温异常"
ACTION_REPLACE = "更换齿轮箱"
ACTION_RULES = {
    ACTION_OIL_CHANGE: STATUS_NORMAL,
    ACTION_REPORT_HIGH_TEMP: STATUS_HIGH_TEMP,
    ACTION_REPLACE: STATUS_REPLACED,
}

# 未指定下次换油日时，按 180 天换油周期自动推算。
OIL_CHANGE_CYCLE_DAYS = 180


class GearboxService:
    # ---- 读取口径（列表 / 详情 / 导出共用，杜绝两处读值不一致）----

    def serialize(self, row: dict[str, Any]) -> dict[str, Any]:
        """把仓库里的原始行整理成对外统一结构。

        「齿轮箱状态」始终以内部 status 为准同步输出，前端各页不需要再各算一遍。
        """
        status = str(row.get("status") or STATUS_PENDING)
        item: dict[str, Any] = {"id": row.get("id")}
        for field in DISPLAY_FIELDS:
            item[field] = row.get(field)
        item["status"] = status
        item["齿轮箱状态"] = status
        item["pending"] = status == STATUS_PENDING
        item["abnormal"] = bool(row.get("abnormal")) or status == STATUS_HIGH_TEMP
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
            rows = [row for row in rows if keyword in str(row.get("齿轮箱编号", ""))]
        if status:
            rows = [row for row in rows if str(row.get("status") or "") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self.serialize(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self.serialize(row) if row is not None else None

    # ---- 登记 / 编辑 ----

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        try:
            temp_limit = _parse_temp_limit(values.get("油温上限"))
        except ValueError as exc:
            return None, [str(exc)]
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["齿轮箱编号"] = str(values.get("齿轮箱编号")).strip()
        entry["所属机组"] = str(values.get("所属机组")).strip()
        entry["油温上限"] = temp_limit
        entry["振动值"] = _clean(values.get("振动值"))
        entry["油品型号"] = _clean(values.get("油品型号"))
        entry["上次换油日"] = _clean(values.get("上次换油日"))
        entry["下次换油日"] = _clean(values.get("下次换油日"))
        entry["status"] = STATUS_PENDING
        entry["pending"] = True
        entry["abnormal"] = False
        entry["last_action"] = None
        rows.append(entry)
        return self.serialize(entry), []

    def update_entry(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """编辑台账字段：先把全部字段校验完，再一次性落库，避免保存一半。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"齿轮箱 {entry_id} 不存在或已归档"
        changes: dict[str, Any] = {}
        try:
            for field in EDITABLE_FIELDS:
                if field not in values or values.get(field) is None:
                    continue
                text = str(values.get(field)).strip()
                if not text:
                    continue
                if field == "油温上限":
                    changes[field] = _parse_temp_limit(text)
                elif field in ("上次换油日", "下次换油日"):
                    changes[field] = _parse_date(text, field).isoformat()
                else:
                    changes[field] = text
        except ValueError as exc:
            return None, str(exc)
        if not changes:
            return None, "没有可保存的字段，请填写油温上限、油品型号或换油日期后再提交"
        entry.update(changes)
        return self.serialize(entry), "齿轮箱台账已更新"

    # ---- 状态流转 ----

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"齿轮箱 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于齿轮箱可执行范围"

        values = values or {}
        current = str(entry.get("status") or STATUS_PENDING)
        if current == STATUS_REPLACED:
            return None, "该齿轮箱已更换归档，不能再执行换油或异常登记动作"

        if action == ACTION_OIL_CHANGE:
            return self._confirm_oil_change(entry, current, values)
        if action == ACTION_REPORT_HIGH_TEMP:
            return self._report_high_temp(entry, current)
        return self._replace_gearbox(entry)

    def _confirm_oil_change(
        self, entry: dict[str, Any], current: str, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        # 幂等：已经确认过换油且没有新的异常登记，重复提交不再改动任何字段。
        if current == STATUS_NORMAL and entry.get("last_action") == ACTION_OIL_CHANGE:
            return self.serialize(entry), "该齿轮箱已完成换油确认，无需重复提交"

        # 先把这次要改的字段全部校验好，任何一项不通过都保持原记录不动。
        # 换油确认必须显式提交本次加注的油品型号与油温上限，不允许静默沿用旧值。
        changes: dict[str, Any] = {}
        try:
            temp_limit = _parse_temp_limit(values.get("油温上限"))
            oil_brand = str(values.get("油品型号") or "").strip()
            if not oil_brand:
                raise ValueError("油品型号不能为空，请填写本次加注的油品型号")
            today = date.today()
            next_raw = values.get("下次换油日")
            if str(next_raw or "").strip():
                next_day = _parse_date(next_raw, "下次换油日")
            else:
                next_day = today + timedelta(days=OIL_CHANGE_CYCLE_DAYS)
        except ValueError as exc:
            return None, str(exc)

        changes.update({
            "status": STATUS_NORMAL,
            "pending": False,
            "abnormal": False,  # 换油确认同时消除油温异常标记
            "油温上限": temp_limit,
            "油品型号": oil_brand,
            "上次换油日": today.isoformat(),
            "下次换油日": next_day.isoformat(),
            "last_action": ACTION_OIL_CHANGE,
        })
        entry.update(changes)
        return self.serialize(entry), "换油确认成功，状态、油温上限、油品型号与异常标记已一并更新"

    def _report_high_temp(
        self, entry: dict[str, Any], current: str
    ) -> tuple[dict[str, Any] | None, str]:
        if current == STATUS_HIGH_TEMP:
            return self.serialize(entry), "油温异常已登记过，等待换油处理，无需重复登记"
        entry["status"] = STATUS_HIGH_TEMP
        entry["pending"] = False
        entry["abnormal"] = True
        entry["last_action"] = ACTION_REPORT_HIGH_TEMP
        return self.serialize(entry), "油温异常已登记，请尽快安排换油"

    def _replace_gearbox(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry["status"] = STATUS_REPLACED
        entry["pending"] = False
        entry["abnormal"] = False
        entry["last_action"] = ACTION_REPLACE
        return self.serialize(entry), "齿轮箱已更换并归档"


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _parse_temp_limit(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("油温上限不能为空，请填写数字（摄氏度）")
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"油温上限需为数字（摄氏度），收到的是「{text}」") from None
    if not 0 < number <= 200:
        raise ValueError(f"油温上限 {number}℃ 超出合理范围（0~200℃），请核对后再提交")
    return str(int(number)) if number.is_integer() else str(number)


def _parse_date(value: Any, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field}不能为空，请填写 YYYY-MM-DD 格式的日期")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            f"{field}格式不正确，请使用 YYYY-MM-DD（例如 {date.today().isoformat()}）"
        ) from None
