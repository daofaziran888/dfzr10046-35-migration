"""指标绑定领域服务：校验指标与度量的绑定关系数据集，版本切换保留历史口径和导出持久化。

除通用列表/登记/动作外，这里承载“直连某份绑定”所需的编辑语义：

- 绑定与引用度量各自带 revision，提交时同时核对两份版本；
- 冲突按“能否沿用当前所选度量 / 是否须重新取得编辑确认”两个维度分型；
- 已失效（已替换、已解除）的绑定仍可解析归属，并给出可执行的后续动作。
"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.store import store

EDITABLE_STATUSES = {"待生效", "生效中"}
INVALID_STATUSES = {"已替换", "已解除"}
RESTORABLE_STATUSES = {"已解除"}
EDITABLE_FIELDS = ["指标名称", "绑定维度", "统计口径", "时间窗口", "绑定版本"]


def revision_of(row: dict[str, Any]) -> int:
    """存量行没有 revision 字段时按 1 处理，避免迁移前后版本号语义漂移。"""
    try:
        return int(row.get("revision") or 1)
    except (TypeError, ValueError):
        return 1


class MetricBindService(BaseModuleService):
    MODULE = "metric_bind"
    ENTITY = "绑定关系"
    LIST_FIELDS = ["绑定编号", "指标名称", "引用度量", "绑定维度", "统计口径", "时间窗口", "绑定版本", "最近生效"]
    REQUIRED_FIELDS = ["绑定编号", "指标名称", "引用度量"]
    STATUS_ORDER = ["待生效", "生效中", "已替换", "已解除"]
    ACTION_RULES = {"启效绑定": "生效中", "替换绑定": "已替换", "解除绑定": "已解除"}
    NEGATIVE_ACTIONS = []

    # ---------- 读取：归属、度量快照与编辑能力 ----------

    def _measure_for(self, measure_ref: str | None) -> dict[str, Any] | None:
        if not measure_ref:
            return None
        for row in store.rows("measure_catalog"):
            if row.get("度量编号") == measure_ref:
                return row
        return None

    @staticmethod
    def measure_snapshot(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": int(row.get("id", 0)),
            "code": row.get("度量编号", ""),
            "name": row.get("度量名称", ""),
            "expression": row.get("计算表达式", ""),
            "status": row.get("status", ""),
            "revision": revision_of(row),
        }

    @staticmethod
    def binding_snapshot(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(row.get("id", 0)),
            "code": row.get("绑定编号", ""),
            "name": row.get("指标名称", ""),
            "measureRef": row.get("引用度量", ""),
            "dimension": row.get("绑定维度", ""),
            "caliber": row.get("统计口径", ""),
            "timeWindow": row.get("时间窗口", ""),
            "version": row.get("绑定版本", ""),
            "status": row.get("status", ""),
            "revision": revision_of(row),
        }

    def _ownership(self, row: dict[str, Any]) -> dict[str, Any]:
        """对象归属：链接失效时仍要告诉用户这是哪个模块下的哪一份绑定。"""
        return {
            "moduleKey": self.MODULE,
            "moduleName": "指标绑定",
            "entity": self.ENTITY,
            "entryId": int(row.get("id", 0)),
            "bindingCode": row.get("绑定编号", ""),
            "metricName": row.get("指标名称", ""),
            "dimension": row.get("绑定维度", ""),
            "measureRef": row.get("引用度量", ""),
            "status": row.get("status", ""),
        }

    def _follow_ups(self, row: dict[str, Any]) -> list[dict[str, str]]:
        status = str(row.get("status", ""))
        actions: list[dict[str, str]] = []
        if status in INVALID_STATUSES:
            actions.append({"action": "duplicate", "label": "复制为新绑定"})
            if status in RESTORABLE_STATUSES:
                actions.append({"action": "restore", "label": "重新启用绑定"})
            actions.append({"action": "open_measure", "label": "查看引用度量"})
            actions.append({"action": "open_list", "label": "回到指标绑定列表"})
        else:
            actions.append({"action": "open_measure", "label": "查看引用度量"})
            actions.append({"action": "open_list", "label": "回到指标绑定列表"})
        return actions

    def binding_context(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(self.MODULE, entry_id)
        if row is None:
            return None
        status = str(row.get("status", ""))
        measure = self._measure_for(row.get("引用度量"))
        return {
            "binding": self.binding_snapshot(row),
            "measure": self.measure_snapshot(measure),
            "editable": status in EDITABLE_STATUSES,
            "invalid": status in INVALID_STATUSES,
            "ownership": self._ownership(row),
            "followUps": self._follow_ups(row),
        }

    def resolve_by_code(self, bind_code: str) -> dict[str, Any] | None:
        """旧书签可能只带绑定编号，按编号兜底解析到同一份绑定。"""
        code = (bind_code or "").strip()
        if not code:
            return None
        for row in store.rows(self.MODULE):
            if row.get("绑定编号") == code:
                return row
        return None

    # ---------- 冲突分型 ----------

    @staticmethod
    def _conflict(
        kind: str,
        message: str,
        *,
        can_keep_measure: bool,
        must_reconfirm: bool,
        binding: dict[str, Any] | None = None,
        measure: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": kind,
            "message": message,
            "canKeepMeasure": can_keep_measure,
            "mustReconfirm": must_reconfirm,
            "binding": binding,
            "measure": measure,
        }

    def _compare_revisions(
        self,
        *,
        row: dict[str, Any],
        measure: dict[str, Any] | None,
        expected_binding_revision: int | None,
        expected_measure_revision: int | None,
    ) -> dict[str, Any] | None:
        binding_snapshot = self.binding_snapshot(row)
        measure_snapshot = self.measure_snapshot(measure)
        binding_stale = (
            expected_binding_revision is not None
            and int(expected_binding_revision) != binding_snapshot["revision"]
        )
        if measure is None:
            measure_stale = True
        else:
            measure_stale = (
                expected_measure_revision is not None
                and int(expected_measure_revision) != revision_of(measure)
            )
        if binding_stale and measure_stale:
            return self._conflict(
                "binding_and_measure_changed",
                "所选绑定与引用度量都已被他人修改：度量不能沿用，且须重新取得编辑确认。",
                can_keep_measure=False,
                must_reconfirm=True,
                binding=binding_snapshot,
                measure=measure_snapshot,
            )
        if binding_stale:
            return self._conflict(
                "binding_changed",
                "这份绑定的指标信息已被他人修改：所选度量仍可沿用，但须重新取得编辑确认。",
                can_keep_measure=True,
                must_reconfirm=True,
                binding=binding_snapshot,
                measure=measure_snapshot,
            )
        if measure_stale:
            if measure is None:
                return self._conflict(
                    "measure_missing",
                    f"引用的度量 {row.get('引用度量') or '（空）'} 已不存在：不能沿用，须重新选择度量。",
                    can_keep_measure=False,
                    must_reconfirm=False,
                    binding=binding_snapshot,
                    measure=None,
                )
            return self._conflict(
                "measure_changed",
                "所选度量已被他人修改：不能沿用当前度量定义，须重新选择度量后提交。",
                can_keep_measure=False,
                must_reconfirm=False,
                binding=binding_snapshot,
                measure=measure_snapshot,
            )
        return None

    # ---------- 写入：提交编辑 ----------

    def commit_edit(
        self,
        entry_id: int,
        *,
        fields: dict[str, Any],
        measure_ref: str,
        expected_binding_revision: int | None,
        expected_measure_revision: int | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """提交绑定编辑：版本对不上就不落库，并把冲突分型交回调用方。"""
        row = store.find(self.MODULE, entry_id)
        if row is None:
            return None, self._conflict(
                "binding_missing",
                f"绑定 {entry_id} 不存在或已归档，无法提交修改。",
                can_keep_measure=False,
                must_reconfirm=False,
            )
        if str(row.get("status", "")) not in EDITABLE_STATUSES:
            return None, self._conflict(
                "binding_invalid",
                f"绑定 {row.get('绑定编号')} 当前为「{row.get('status')}」，已失效，不能直接编辑；请复制为新绑定或重新启用。",
                can_keep_measure=False,
                must_reconfirm=False,
                binding=self.binding_snapshot(row),
                measure=self.measure_snapshot(self._measure_for(row.get("引用度量"))),
            )
        measure_ref = (measure_ref or "").strip()
        if not measure_ref:
            return None, self._conflict(
                "measure_missing",
                "尚未选择引用度量，无法提交绑定。",
                can_keep_measure=False,
                must_reconfirm=False,
                binding=self.binding_snapshot(row),
            )
        measure = self._measure_for(measure_ref)
        conflict = self._compare_revisions(
            row=row,
            measure=measure,
            expected_binding_revision=expected_binding_revision,
            expected_measure_revision=expected_measure_revision,
        )
        if conflict is not None:
            return None, conflict

        for field in EDITABLE_FIELDS:
            if field in fields and str(fields[field] or "").strip():
                row[field] = str(fields[field]).strip()
        row["引用度量"] = measure_ref
        row["revision"] = revision_of(row) + 1
        return row, None

    def update_fields(
        self,
        entry_id: int,
        values: dict[str, Any],
        *,
        expected_revision: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """通用字段更新；并发演示与正常编辑共用，版本不一致时拒绝覆盖。"""
        row = store.find(self.MODULE, entry_id)
        if row is None:
            return None, self._conflict(
                "binding_missing",
                f"绑定 {entry_id} 不存在或已归档。",
                can_keep_measure=False,
                must_reconfirm=False,
            )
        if expected_revision is not None and int(expected_revision) != revision_of(row):
            return None, self._conflict(
                "binding_changed",
                "这份绑定已被他人修改，请重新载入后再提交。",
                can_keep_measure=True,
                must_reconfirm=True,
                binding=self.binding_snapshot(row),
                measure=self.measure_snapshot(self._measure_for(row.get("引用度量"))),
            )
        for field in EDITABLE_FIELDS:
            if field in values and str(values[field] or "").strip():
                row[field] = str(values[field]).strip()
        row["revision"] = revision_of(row) + 1
        return row, None

    def duplicate_binding(self, entry_id: int) -> dict[str, Any] | None:
        """把失效绑定复制成一份新的待生效绑定，保留原绑定作为历史口径。"""
        source = store.find(self.MODULE, entry_id)
        if source is None:
            return None
        rows = store.rows(self.MODULE)
        copy_no = 1
        existing = {str(row.get("绑定编号", "")) for row in rows}
        base = f"{source.get('绑定编号', 'BND')}-COPY"
        candidate = base
        while candidate in existing:
            copy_no += 1
            candidate = f"{base}{copy_no}"
        entry = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "status": "待生效",
            "pending": True,
            "abnormal": False,
            "绑定编号": candidate,
            "指标名称": source.get("指标名称", ""),
            "引用度量": source.get("引用度量", ""),
            "绑定维度": source.get("绑定维度", ""),
            "统计口径": source.get("统计口径", ""),
            "时间窗口": source.get("时间窗口", ""),
            "绑定版本": source.get("绑定版本", ""),
            "最近生效": "",
            "revision": 1,
        }
        rows.append(entry)
        return entry

    def restore_binding(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """已解除的绑定重新启用为待生效，并推进版本号。"""
        row = store.find(self.MODULE, entry_id)
        if row is None:
            return None, f"绑定 {entry_id} 不存在或已归档"
        if str(row.get("status", "")) not in RESTORABLE_STATUSES:
            return None, f"绑定 {row.get('绑定编号')} 当前为「{row.get('status')}」，不能重新启用"
        row["status"] = "待生效"
        row["pending"] = True
        row["abnormal"] = False
        row["revision"] = revision_of(row) + 1
        return row, f"绑定 {row.get('绑定编号')} 已重新启用，可继续编辑"

    # ---------- 兼容原有领域方法 ----------

    def bind_metric(
        self, bind_id: str, metric_name: str, measure_ref: str,
        dim_ref: str, caliber: str, time_window: str, version: str,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """绑定指标到度量与维度：历史读数值保留原绑定口径。"""
        rows = store.rows(self.MODULE)
        entry = {
            "绑定编号": bind_id, "指标名称": metric_name,
            "引用度量": measure_ref, "绑定维度": dim_ref,
            "统计口径": caliber, "时间窗口": time_window,
            "绑定版本": version, "最近生效": "2026-11-21",
            "status": "生效中", "pending": False, "abnormal": False,
            "revision": 1,
        }
        entry["id"] = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        rows.append(entry)
        return True, f"指标 {metric_name}={measure_ref} 已绑定生效", entry

    def replace_binding(self, bind_id: str, new_measure: str, new_version: str) -> tuple[bool, str]:
        """替换绑定版本：旧版本口径保留，新版本独立。"""
        rows = store.rows(self.MODULE)
        for r in rows:
            if r.get("绑定编号") == bind_id:
                r["status"] = "已替换"
                r["引用度量"] = new_measure
                r["绑定版本"] = new_version
                r["pending"] = False
                r["revision"] = revision_of(r) + 1
                return True, f"指标绑定 {bind_id} 已替换为版本 {new_version}"
        return False, f"绑定 {bind_id} 不存在"
