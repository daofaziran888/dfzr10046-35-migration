"""统一资源接口：查询、导出、登记和动作按模块 key 分派到领域服务。"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import (
    ActionResult,
    ActionPayload,
    ApplyMeasurePayload,
    EditResult,
    EntryPayload,
    PageResult,
    UpdatePayload,
)
from app.services import service_for

router = APIRouter(prefix="/api", tags=["业务资源"])


def require_service(module: str):
    service = service_for(module)
    if service is None:
        raise HTTPException(status_code=404, detail=f"未知业务模块：{module}")
    return service


def require_metric_bind():
    from app.services.metric_bind import MetricBindService

    service = service_for("metric_bind")
    if not isinstance(service, MetricBindService):
        raise HTTPException(status_code=500, detail="指标绑定服务未装配")
    return service


# ---- 指标绑定专用路由：必须放在通用 /{module}/{entry_id} 之前注册 ----

@router.get("/metric_bind/by-code/{bind_code}", response_model=dict)
def resolve_metric_bind_by_code(bind_code: str) -> dict[str, Any]:
    """老书签可能只带绑定编号：按编号解析到当前绑定对象。"""
    service = require_metric_bind()
    row = service.resolve_by_code(bind_code)
    if row is None:
        raise HTTPException(status_code=404, detail=f"绑定编号 {bind_code} 不存在或已归档")
    return row


@router.get("/metric_bind/{entry_id}/context", response_model=dict)
def metric_bind_context(entry_id: int) -> dict[str, Any]:
    """直连某份绑定时的完整上下文：归属、度量快照、可编辑性与后续动作。"""
    service = require_metric_bind()
    context = service.binding_context(entry_id)
    if context is None:
        raise HTTPException(status_code=404, detail=f"绑定 {entry_id} 不存在或已归档")
    return context


@router.post("/metric_bind/{entry_id}/edit", response_model=EditResult)
def commit_metric_bind_edit(entry_id: int, payload: ApplyMeasurePayload) -> EditResult:
    """绑定页选完度量后提交；绑定或度量的版本被他人推进时返回分型冲突。"""
    service = require_metric_bind()
    row, conflict = service.commit_edit(
        entry_id,
        fields=payload.values,
        measure_ref=payload.measureRef,
        expected_binding_revision=payload.expectedBindingRevision,
        expected_measure_revision=payload.expectedMeasureRevision,
    )
    if conflict is not None:
        return EditResult(ok=False, message=conflict["message"], conflict=conflict)
    return EditResult(ok=True, message="绑定修改已提交", entry=row)


@router.patch("/metric_bind/{entry_id}", response_model=EditResult)
def update_metric_bind(entry_id: int, payload: UpdatePayload) -> EditResult:
    """按版本号更新绑定字段，用于模拟他人并发修改。"""
    service = require_metric_bind()
    row, conflict = service.update_fields(
        entry_id, payload.values, expected_revision=payload.expectedRevision)
    if conflict is not None:
        return EditResult(ok=False, message=conflict["message"], conflict=conflict)
    return EditResult(ok=True, message="绑定已更新", entry=row)


@router.post("/metric_bind/{entry_id}/duplicate", response_model=EditResult)
def duplicate_metric_bind(entry_id: int) -> EditResult:
    service = require_metric_bind()
    row = service.duplicate_binding(entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"绑定 {entry_id} 不存在或已归档")
    return EditResult(ok=True, message=f"已复制为新绑定 {row.get('绑定编号')}", entry=row)


@router.post("/metric_bind/{entry_id}/restore", response_model=EditResult)
def restore_metric_bind(entry_id: int) -> EditResult:
    service = require_metric_bind()
    row, message = service.restore_binding(entry_id)
    if row is None:
        return EditResult(ok=False, message=message)
    return EditResult(ok=True, message=message, entry=row)


@router.patch("/measure_catalog/{entry_id}", response_model=EditResult)
def update_measure(entry_id: int, payload: UpdatePayload) -> EditResult:
    """按版本号更新度量字段，用于模拟编制绑定期间度量被他人改动。"""
    service = require_service("measure_catalog")
    row, error = service.update_fields(
        entry_id, payload.values, expected_revision=payload.expectedRevision)
    if row is None:
        return EditResult(ok=False, message=error or "度量更新失败")
    return EditResult(ok=True, message="度量已更新", entry=row)


@router.get("/{module}", response_model=PageResult[dict])
def list_entries(
    module: str,
    request: Request,
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResult[dict]:
    service = require_service(module)
    filters = {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in service.LIST_FIELDS and value.strip()
    }
    items, total = service.list_entries(
        filters=filters, keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{module}/export")
def export_entries(
    module: str,
    request: Request,
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> StreamingResponse:
    service = require_service(module)
    filters = {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in service.LIST_FIELDS and value.strip()
    }
    items, _ = service.list_entries(
        filters=filters, keyword=keyword, status=status, page=1, size=1_000_000)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", *service.LIST_FIELDS, "status"])
    for item in items:
        values = [item.get("id"), *(item.get(field, "") for field in service.LIST_FIELDS),
                  item.get("status", "")]
        writer.writerow([
            "'" + str(value) if str(value or "").startswith(("=", "+", "-", "@")) else value
            for value in values
        ])
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{module}.csv"'},
    )


@router.get("/{module}/{entry_id}", response_model=dict)
def get_entry(module: str, entry_id: int) -> dict[str, Any]:
    service = require_service(module)
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"{service.ENTITY} {entry_id} 不存在或已归档")
    return entry


@router.post("/{module}", response_model=ActionResult)
def create_entry(module: str, payload: EntryPayload) -> ActionResult:
    service = require_service(module)
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message=f"{service.ENTITY}已登记", entry=entry)


@router.post("/{module}/{entry_id}/actions", response_model=ActionResult)
def run_action(module: str, entry_id: int, payload: ActionPayload) -> ActionResult:
    service = require_service(module)
    entry, message = service.run_action(entry_id, payload.action.strip())
    return ActionResult(ok=entry is not None, message=message, entry=entry)
