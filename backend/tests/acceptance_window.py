"""窗口配置包导入验收脚本：对照验收样例逐项核对，只依赖标准库。

用法：先启动后端（./run.sh），再执行 python3 tests/acceptance_window.py
"""
from __future__ import annotations

import json
import urllib.request

BASE = "http://127.0.0.1:8000"


def call(method: str, path: str, values: dict | None = None) -> dict:
    body = None if values is None else json.dumps({"values": values}).encode()
    req = urllib.request.Request(BASE + path, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path) as resp:
        return json.loads(resp.read())


def check(name: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise SystemExit(f"验收失败：{name}")


# 验收样例一：WIND-0002-v1 写入 pause=true 后重开仍为暂停
result = call("POST", "/api/window/import", {
    "窗口编号": "WIND-0002", "版本号": "v1", "数据流名称": "窗口计算配置样例2",
    "窗口类型": "滑动窗口", "延迟容忍": "10s", "触发策略": "Watermark触发", "暂停标记": True,
})
check("导入 WIND-0002-v1 pause=true", result["ok"], result["message"])

entry = get("/api/window/2")
check("重开后 WIND-0002 仍为暂停", entry["status"] == "已暂停" and entry["暂停标记"] is True)

version = get("/api/window/versions/WIND-0002-v1")
check(
    "版本数据保留暂停标记和迟到容忍",
    version["暂停标记"] is True and version["延迟容忍"] == "10s" and version["窗口类型"] == "滑动窗口",
)

# 验收样例二：WIND-0001 保持草稿
entry1 = get("/api/window/1")
check("WIND-0001 保持草稿", entry1["status"] == "草稿" and entry1["暂停标记"] is False)

# 验收样例三：暂停期间无新触发
blocked = call("POST", "/api/window/2/trigger", {"迟到事件": True})
triggers = get("/api/window/triggers?window_code=WIND-0002")
check("暂停期间无新触发", blocked["ok"] is False and triggers["total"] == 0, blocked["message"])

# 重复导入同一配置包只生效一次
again = call("POST", "/api/window/import", {
    "窗口编号": "WIND-0002", "版本号": "v1", "窗口类型": "滑动窗口", "延迟容忍": "10s", "暂停标记": True,
})
versions = get("/api/window/versions?window_code=WIND-0002")
check("重复导入只生效一次", versions["total"] == 1 and "重复" in again["message"], again["message"])

# 告警消费侧：暂停结论与新告警结果互斥
consumed = call("POST", "/api/alarm/2/consume", {"版本编号": "WIND-0002-v1"})
results = get("/api/alarm/results")
check(
    "告警消费侧只产生暂停结论",
    consumed["conclusion"] == "已暂停" and consumed["alarm_result"] is None and results["total"] == 0,
    consumed["message"],
)
check("消费侧写回自身状态", consumed["entry"]["status"] == "已暂停")

# 导入校验：缺字段与无法识别的暂停标记都被拦下
missing = call("POST", "/api/window/import", {"窗口编号": "WIND-0009", "暂停标记": True})
bad_pause = call("POST", "/api/window/import", {
    "窗口编号": "WIND-0009", "窗口类型": "滚动窗口", "延迟容忍": "5s", "暂停标记": "也许",
})
check("导入字段校验", not missing["ok"] and not bad_pause["ok"], f"{missing['message']} / {bad_pause['message']}")

# 导出与下载流程形成可核对交换结果
exported = get("/api/window/versions/export")
check("版本数据可导出核对", exported["module"] == "window_version" and exported["total"] >= 3)
reimport = call("POST", "/api/window/import", {"items": exported["items"]})
check("导出结果再导入仍只生效一次", "重复" in reimport["message"], reimport["message"])

print("全部验收样例通过")
