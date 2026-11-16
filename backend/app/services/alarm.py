"""流告警规则业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.window import WindowService
from app.store import store

MODULE = "alarm"
RESULT_MODULE = "alarm_result"
REQUIRED_FIELDS = ["规则编号", "监控指标", "告警条件"]
STATUS_ORDER = ["草稿", "已启用", "已暂停", "已关闭"]
ACTION_RULES = {"启用告警": "草稿", "暂停告警": "已启用", "关闭告警": "已暂停"}
NEGATIVE_ACTIONS = []

window_service = WindowService()


class AlarmService:
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
            rows = [row for row in rows if keyword in str(row.get("规则编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"告警规则 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于流告警规则可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"告警规则已{action}"

    # ---- 消费窗口配置版本数据：跨页面链路只读同一份共享数据，消费侧写回自身状态 ----

    def consume_window_version(
        self, entry_id: int, version_code: str
    ) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None, str]:
        """按版本编号消费共享的窗口配置版本数据。

        返回 (告警规则, 消费结论, 新告警结果, 提示信息)。暂停结论与新告警结果互斥：
        版本数据带暂停标记时只写回暂停结论，不再产生新的告警结果。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, None, None, f"告警规则 {entry_id} 不存在或已归档"
        version = window_service.get_version(version_code)
        if version is None:
            return None, None, None, f"窗口配置版本数据 {version_code} 不存在或已归档"
        paused = bool(version.get("暂停标记"))
        with store.transaction():
            if paused:
                entry["status"] = "已暂停"
                entry["规则状态"] = "已暂停"
                entry["pending"] = True
                return entry, "已暂停", None, (
                    f"告警规则已消费 {version_code}：窗口配置版本数据带暂停标记，"
                    "写回暂停结论，不产生新的告警结果"
                )
            if entry.get("status") in ("草稿", "已暂停"):
                entry["status"] = "已启用"
                entry["规则状态"] = "已启用"
            rows = store.rows(RESULT_MODULE)
            result = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            result["规则编号"] = entry.get("规则编号")
            result["版本编号"] = version_code
            result["告警结论"] = "触发告警"
            result["产生时间"] = datetime.now().isoformat(timespec="seconds")
            result["status"] = "已产生"
            rows.append(result)
        return entry, "触发告警", result, f"告警规则已消费 {version_code}：窗口运行中，生成新的告警结果"

    def list_results(self, *, rule_code: str | None = None) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(RESULT_MODULE)
        if rule_code:
            rows = [row for row in rows if row.get("规则编号") == rule_code]
        return list(rows), len(rows)
