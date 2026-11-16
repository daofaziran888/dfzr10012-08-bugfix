"""窗口计算配置接口：维护窗口定义，覆盖启用窗口、暂停窗口、关闭窗口等动作。"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.window import WindowService

router = APIRouter(prefix="/api/window", tags=["窗口计算配置"])

service = WindowService()

LIST_FIELDS = ["窗口编号", "数据流名称", "窗口类型", "窗口长度", "滑动步长", "延迟容忍", "触发策略", "窗口状态"]
STATUSES = ["草稿", "生效中", "已暂停", "已关闭"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按窗口编号检索"),
    status: str | None = Query(default=None, description="草稿、生效中、已暂停、已关闭"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按窗口编号与状态过滤窗口计算配置列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 固定路径必须排在 /{entry_id} 之前，否则导出、版本、下载接口会被当成编号解析而 422。


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出窗口计算配置清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "window", "total": total, "items": items}


@router.post("/import", response_model=ActionResult)
def import_package(payload: EntryPayload) -> ActionResult:
    """导入窗口配置包：与详情视图共享同一条故障链，重复导入同一配置包只生效一次。"""
    created, skipped, errors = service.import_package(payload.values)
    if errors and not created and not skipped:
        return ActionResult(ok=False, message="；".join(errors))
    parts: list[str] = []
    if created:
        parts.append(f"写入 {len(created)} 条窗口配置版本数据")
    if skipped:
        parts.append(f"重复导入只生效一次：{'、'.join(skipped)} 已存在")
    if errors:
        parts.append("；".join(errors))
    entry = created[0] if len(created) == 1 else None
    return ActionResult(ok=not errors, message="；".join(parts) or "配置包为空", entry=entry)


@router.get("/versions", response_model=PageResult[dict])
def list_versions(
    window_code: str | None = Query(default=None, description="按窗口编号过滤版本数据"),
    page: int = 1,
    size: int = 200,
) -> PageResult[dict]:
    """列出窗口配置版本数据：暂停标记与迟到容忍随版本一起保留，历史版本可追溯。"""
    items, total = service.list_versions(window_code=window_code, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/versions/export")
def export_versions() -> dict[str, Any]:
    """导出窗口配置版本数据：与下载流程共用同一份可核对交换结果。"""
    items, total = service.export_versions()
    return {"module": "window_version", "total": total, "items": items}


@router.get("/versions/file")
def download_versions_file() -> Response:
    """下载窗口配置版本数据文件：内容可直接作为配置包重新导入，形成可核对交换闭环。"""
    items, total = service.export_versions()
    payload = {"module": "window_version", "total": total, "items": items}
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=window_versions.json"},
    )


@router.get("/versions/{version_code}", response_model=dict)
def get_version(version_code: str) -> dict:
    """读取单条窗口配置版本数据；不存在时给出与导入链路一致的可读错误说明。"""
    version = service.get_version(version_code)
    if version is None:
        raise HTTPException(status_code=404, detail=f"窗口配置版本数据 {version_code} 不存在或已归档")
    return version


@router.get("/triggers")
def list_triggers(
    window_code: str | None = Query(default=None, description="按窗口编号过滤触发结果"),
) -> dict[str, Any]:
    """列出窗口触发结果：暂停期间不会产生新记录，便于核对。"""
    items, total = service.list_triggers(window_code=window_code)
    return {"module": "window_trigger", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条窗口定义明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"窗口定义 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条窗口定义，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="窗口定义已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条窗口定义执行启用窗口、暂停窗口、关闭窗口；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/trigger", response_model=ActionResult)
def trigger_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """尝试触发窗口：已暂停的窗口不生成新的窗口触发结果，迟到事件一并拦下。"""
    record, message = service.trigger(entry_id, payload.values)
    if record is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=record)
