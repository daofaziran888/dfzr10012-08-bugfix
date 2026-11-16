"""窗口计算配置业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "window"
VERSION_MODULE = "window_version"
TRIGGER_MODULE = "window_trigger"
REQUIRED_FIELDS = ["窗口编号", "数据流名称", "窗口类型"]
STATUS_ORDER = ["草稿", "生效中", "已暂停", "已关闭"]
# 动作 → (允许执行的前置状态, 落库后的目标状态)：暂停窗口必须真正把窗口写成已暂停。
ACTION_RULES = {
    "启用窗口": (["草稿", "已暂停"], "生效中"),
    "暂停窗口": (["生效中"], "已暂停"),
    "关闭窗口": (["已暂停"], "已关闭"),
}
NEGATIVE_ACTIONS: list[str] = []

# 导入配置包时参与校验与落库的字段：窗口类型、延迟容忍、暂停标记必须读得出。
IMPORT_REQUIRED_FIELDS = ["窗口编号", "窗口类型", "延迟容忍"]
VERSION_COPY_FIELDS = ["数据流名称", "窗口类型", "窗口长度", "滑动步长", "延迟容忍", "触发策略"]

PAUSE_TRUE_VALUES = {"true", "1", "是", "暂停", "已暂停", "pause", "paused", "yes"}
PAUSE_FALSE_VALUES = {"false", "0", "否", "运行", "生效中", "运行中", "run", "running", "no"}


def parse_pause_flag(value: Any) -> bool | None:
    """把配置包里的暂停标记解析成布尔值；认不出来的写法返回 None 交给校验报错。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in PAUSE_TRUE_VALUES:
        return True
    if text in PAUSE_FALSE_VALUES:
        return False
    return None


class WindowService:
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
            rows = [row for row in rows if keyword in str(row.get("窗口编号", ""))]
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
        # 重复登记只留一份记录：同一窗口编号直接返回既有记录。
        existing = store.find_by(MODULE, "窗口编号", str(values.get("窗口编号") or "").strip())
        if existing is not None:
            return existing, []
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["暂停标记"] = False
        entry["窗口状态"] = STATUS_ORDER[0]
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"窗口定义 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于窗口计算配置可执行范围"
        sources, target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        current = str(entry.get("status") or "")
        if current not in sources:
            return None, f"窗口定义当前状态「{current}」不允许执行{action}"
        # 暂停标记和窗口状态必须在同一事务内落库：窗口定义与当前版本数据一起改。
        with store.transaction():
            entry["status"] = target
            entry["窗口状态"] = target
            entry["暂停标记"] = target == "已暂停"
            entry["pending"] = target != STATUS_ORDER[-1]
            entry["abnormal"] = action in NEGATIVE_ACTIONS
            version = self.current_version(str(entry.get("窗口编号") or ""))
            if version is not None:
                version["暂停标记"] = entry["暂停标记"]
                version["窗口状态"] = target
                version["status"] = target
        return entry, f"窗口定义已{action}"

    # ---- 窗口配置版本数据：导入、导出、文件与下载流程共享的同一份数据 ----

    def list_versions(
        self,
        *,
        window_code: str | None = None,
        page: int = 1,
        size: int = 200,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(VERSION_MODULE)
        if window_code:
            rows = [row for row in rows if row.get("窗口编号") == window_code]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_version(self, version_code: str) -> dict[str, Any] | None:
        return store.find_by(VERSION_MODULE, "版本编号", version_code)

    def current_version(self, window_code: str) -> dict[str, Any] | None:
        """窗口当前生效的版本数据：编号最大的一条，历史版本保留不删，保持可追溯。"""
        versions = [row for row in store.rows(VERSION_MODULE) if row.get("窗口编号") == window_code]
        if not versions:
            return None
        return max(versions, key=lambda row: int(row.get("id", 0)))

    def is_paused(self, entry: dict[str, Any]) -> bool:
        """暂停结论只认一处：共享的窗口配置版本数据；没有版本数据时回看窗口状态。"""
        version = self.current_version(str(entry.get("窗口编号") or ""))
        if version is not None:
            return bool(version.get("暂停标记"))
        return entry.get("status") == "已暂停" or bool(entry.get("暂停标记"))

    def import_package(self, values: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        """导入窗口配置包：校验字段后写入窗口配置版本数据，重复导入同一配置包只生效一次。

        返回 (写入的版本数据, 重复跳过的版本编号, 校验错误列表)。
        """
        items = values.get("items")
        configs = items if isinstance(items, list) else [values]
        created: list[dict[str, Any]] = []
        skipped: list[str] = []
        errors: list[str] = []
        for config in configs:
            if not isinstance(config, dict):
                errors.append("配置包内存在无效的配置条目")
                continue
            version, skipped_code, error = self._import_one(config)
            if error:
                errors.append(error)
            elif skipped_code:
                skipped.append(skipped_code)
            elif version is not None:
                created.append(version)
        return created, skipped, errors

    def _import_one(self, config: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, str | None]:
        """导入单条窗口配置：返回 (写入的版本数据, 重复跳过的版本编号, 错误信息)。"""
        missing = [field for field in IMPORT_REQUIRED_FIELDS if not str(config.get(field) or "").strip()]
        if missing:
            return None, None, f"缺少必填字段：{'、'.join(missing)}"
        pause_flag = parse_pause_flag(config.get("暂停标记"))
        if pause_flag is None:
            return None, None, "暂停标记无法识别：请填写 true/false 或 是/否"
        window_code = str(config.get("窗口编号") or "").strip()
        version_no = str(config.get("版本号") or "").strip() or "v1"
        version_code = f"{window_code}-{version_no}"
        if self.get_version(version_code) is not None:
            return None, version_code, None  # 重复导入只生效一次，不再落库也不改状态
        # 校验通过后在同一事务内落库：版本数据、暂停标记、窗口状态一起写入。
        with store.transaction():
            entry = store.find_by(MODULE, "窗口编号", window_code)
            if entry is None:
                # 配置包首次带来这个窗口编号时补登记，重复登记只留一份记录。
                entry_rows = store.rows(MODULE)
                entry = {"id": max((int(row.get("id", 0)) for row in entry_rows), default=0) + 1}
                entry["窗口编号"] = window_code
                entry["数据流名称"] = config.get("数据流名称")
                entry["窗口类型"] = config.get("窗口类型")
                entry["status"] = STATUS_ORDER[0]
                entry["pending"] = True
                entry["abnormal"] = False
                entry_rows.append(entry)
            if pause_flag:
                entry["status"] = "已暂停"
            elif entry.get("status") == "已暂停":
                entry["status"] = "生效中"  # 配置包解除暂停，与版本数据保持一致
            entry["暂停标记"] = pause_flag
            entry["窗口状态"] = entry["status"]
            rows = store.rows(VERSION_MODULE)
            version = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            version["版本编号"] = version_code
            version["窗口编号"] = window_code
            version["版本号"] = version_no
            for field in VERSION_COPY_FIELDS:
                if field in config:
                    version[field] = config[field]
            # 可核对结果：窗口配置版本数据保留暂停标记和迟到容忍。
            version["暂停标记"] = pause_flag
            version["延迟容忍"] = config.get("延迟容忍")
            version["窗口状态"] = entry["status"]
            version["status"] = entry["status"]
            version["pending"] = entry["status"] != STATUS_ORDER[-1]
            version["abnormal"] = False
            version["来源"] = "导入"
            rows.append(version)
        return version, None, None

    def export_versions(self) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(VERSION_MODULE)
        return list(rows), len(rows)

    # ---- 窗口触发：暂停期间不得生成新的窗口触发结果 ----

    def trigger(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"窗口定义 {entry_id} 不存在或已归档"
        if self.is_paused(entry):
            return None, f"窗口 {entry.get('窗口编号')} 已暂停：暂停期间不生成新的窗口触发结果，迟到事件不再处理"
        if entry.get("status") != "生效中":
            return None, f"窗口 {entry.get('窗口编号')} 当前状态「{entry.get('status')}」不允许触发"
        with store.transaction():
            rows = store.rows(TRIGGER_MODULE)
            record = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            record["窗口编号"] = entry.get("窗口编号")
            record["触发时间"] = datetime.now().isoformat(timespec="seconds")
            record["迟到事件"] = bool(values.get("迟到事件"))
            record["触发结果"] = "已触发"
            record["status"] = "已触发"
            rows.append(record)
        return record, f"窗口 {entry.get('窗口编号')} 已生成窗口触发结果"

    def list_triggers(self, *, window_code: str | None = None) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(TRIGGER_MODULE)
        if window_code:
            rows = [row for row in rows if row.get("窗口编号") == window_code]
        return list(rows), len(rows)
