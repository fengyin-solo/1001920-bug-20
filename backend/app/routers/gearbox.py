"""齿轮箱接口：维护齿轮箱，覆盖确认换油、登记油温异常、更换齿轮箱等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.gearbox import GearboxService

router = APIRouter(prefix="/api/gearbox", tags=["齿轮箱"])

service = GearboxService()

LIST_FIELDS = ["齿轮箱编号", "所属机组", "油温上限", "振动值", "上次换油日", "下次换油日", "油品型号", "齿轮箱状态"]
STATUSES = ["待换油", "运行正常", "油温偏高", "已更换"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按齿轮箱编号检索"),
    status: str | None = Query(default=None, description="待换油、运行正常、油温偏高、已更换"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按齿轮箱编号与状态过滤齿轮箱列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出齿轮箱清单：与列表接口同一序列化口径，导出值与页面一致。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "gearbox", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条齿轮箱明细；不存在时给出可读的错误说明。

    明细与列表来自同一份 service 序列化结果，油温上限、下次换油日等不会两页两个值。
    """
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"齿轮箱 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条齿轮箱，缺字段或格式不对时说明原因而不是静默丢弃。"""
    entry, problems = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=f"登记未成功：{'、'.join(problems)}")
    return ActionResult(ok=True, message="齿轮箱已登记", entry=entry)


@router.patch("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """编辑齿轮箱台账字段（油温上限、油品型号、换油日期等），失败时返回可读原因。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条齿轮箱执行确认换油、登记油温异常、更换齿轮箱。

    确认换油可携带 油温上限 / 油品型号 / 下次换油日；不允许的动作或不满足的前置状态
    会被拦下并说明原因，重复确认是幂等的，不会把已换油记录推回待换油。
    """
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
