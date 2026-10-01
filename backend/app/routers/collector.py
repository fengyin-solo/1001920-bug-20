"""集电线路接口：维护集电线路，覆盖提交巡视、登记缺陷、停运线路等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.collector import CollectorService

router = APIRouter(prefix="/api/collector", tags=["集电线路"])

service = CollectorService()

LIST_FIELDS = ["线路编号", "电压等级", "起止杆塔", "线路长度", "所属场站", "上次巡视日", "缺陷数量", "线路状态"]
STATUSES = ["待巡视", "运行正常", "存在缺陷", "已停运"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按线路编号检索"),
    status: str | None = Query(default=None, description="待巡视、运行正常、存在缺陷、已停运"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按线路编号与状态过滤集电线路列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出集电线路清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "collector", "total": total, "items": items}


# 注意：/export 必须声明在 /{entry_id} 之前，否则会被当成 entry_id=export 匹配
@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条集电线路明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"集电线路 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条集电线路，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="集电线路已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条集电线路执行提交巡视、登记缺陷、停运线路；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
