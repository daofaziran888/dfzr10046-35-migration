"""度量目录领域服务：维护校验度量计算表达式聚合方式的数据集，导入导出单位声明。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class MeasureCatalogService(BaseModuleService):
    MODULE = "measure_catalog"
    ENTITY = "度量条目"
    LIST_FIELDS = ["度量编号", "度量名称", "计算表达式", "聚合方式", "单位声明", "精度位数", "适用粒度", "目录版本"]
    REQUIRED_FIELDS = ["度量编号", "度量名称", "计算表达式"]
    STATUS_ORDER = ["草稿", "已收录", "已修订", "已下线"]
    ACTION_RULES = {"收录度量": "已收录", "提交修订": "已修订", "下线度量": "已下线"}
    NEGATIVE_ACTIONS = []

    def catalog_measure(
        self, measure_id: str, name: str, expression: str,
        aggregation: str, unit: str, precision: int, applicable_grain: str,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """收录度量条目到目录。"""
        rows = store.rows(self.MODULE)
        entry = {
            "度量编号": measure_id, "度量名称": name,
            "计算表达式": expression, "聚合方式": aggregation,
            "单位声明": unit, "精度位数": precision,
            "适用粒度": applicable_grain, "目录版本": "v1",
            "status": "已收录", "pending": False, "abnormal": False,
        }
        entry["id"] = max((int(r.get("id", 0)) for r in rows), default=0) + 1
        rows.append(entry)
        return True, f"度量 {measure_id} 已收录", entry

    def revise_measure(self, measure_id: str, new_expression: str) -> tuple[bool, str]:
        """修订度量表达式：已修订的度量需通知依赖的指标绑定更新。"""
        rows = store.rows(self.MODULE)
        for r in rows:
            if r.get("度量编号") == measure_id:
                r["计算表达式"] = new_expression
                r["status"] = "已修订"
                r["目录版本"] = f"v{int(r.get('id', 1)) + 1}"
                r["revision"] = int(r.get("revision") or 1) + 1
                return True, f"度量 {measure_id} 已修订"
        return False, f"度量 {measure_id} 不存在"

    def update_fields(
        self,
        entry_id: int,
        values: dict[str, Any],
        *,
        expected_revision: int | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """修改度量字段：版本号单调递增，供绑定页判断所选度量是否仍可用。"""
        row = store.find(self.MODULE, entry_id)
        if row is None:
            return None, "度量不存在或已归档"
        current = int(row.get("revision") or 1)
        if expected_revision is not None and int(expected_revision) != current:
            return None, "度量已被他人修改，请重新载入后再提交"
        for field in self.LIST_FIELDS:
            if field in values and str(values[field] or "").strip():
                row[field] = str(values[field]).strip()
        row["revision"] = current + 1
        return row, None

    def find_by_code(self, measure_id: str) -> dict[str, Any] | None:
        for row in store.rows(self.MODULE):
            if row.get("度量编号") == measure_id:
                return row
        return None
