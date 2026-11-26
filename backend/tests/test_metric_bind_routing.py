"""指标绑定直连路由与并发编辑语义的测试。"""
from __future__ import annotations

import pytest

from app.services import service_for
from app.services.metric_bind import MetricBindService, revision_of
from app.store import Store


@pytest.fixture()
def bind_service() -> MetricBindService:
    service = service_for("metric_bind")
    assert isinstance(service, MetricBindService)
    return service


@pytest.fixture(autouse=True)
def fresh_store():
    """每个用例把内存仓库重置回种子数据，互不污染。"""
    from app.store import store

    original = store._tables
    store._tables = Store()._tables
    try:
        yield store
    finally:
        store._tables = original


def test_direct_context_for_active_binding(bind_service):
    context = bind_service.binding_context(1)
    assert context is not None
    assert context["binding"]["code"] == "BND-001"
    assert context["measure"]["code"] == "MSR-001"
    assert context["editable"] is True
    assert context["invalid"] is False
    assert context["ownership"]["moduleKey"] == "metric_bind"
    assert context["ownership"]["entryId"] == 1


def test_invalid_binding_still_reports_ownership_and_followups(bind_service):
    """绑定已失效：链接仍能给出归属与可执行的后续动作。"""
    context = bind_service.binding_context(3)
    assert context is not None
    assert context["invalid"] is True
    assert context["editable"] is False
    assert context["ownership"]["bindingCode"] == "BND-003"
    assert context["ownership"]["metricName"] == "季度毛利"
    actions = {item["action"] for item in context["followUps"]}
    assert {"duplicate", "restore", "open_measure", "open_list"} <= actions


def test_resolve_by_code_backs_old_bookmarks(bind_service):
    row = bind_service.resolve_by_code("BND-002")
    assert row is not None
    assert int(row["id"]) == 2


def test_commit_edit_without_conflict_advances_revision(bind_service):
    row, conflict = bind_service.commit_edit(
        1,
        fields={"指标名称": "月度销售额（新）", "统计口径": "含税"},
        measure_ref="MSR-002",
        expected_binding_revision=1,
        expected_measure_revision=1,
    )
    assert conflict is None
    assert row is not None
    assert row["指标名称"] == "月度销售额（新）"
    assert row["引用度量"] == "MSR-002"
    assert revision_of(row) == 2


def test_measure_changed_conflict_blocks_and_cannot_keep(bind_service):
    """选度量期间度量被改动：不能沿用所选度量，但不要求重新取得编辑确认。"""
    measure = service_for("measure_catalog")
    measure.update_fields(1, {"度量名称": "日销售额-他人改"})

    row, conflict = bind_service.commit_edit(
        1, fields={"指标名称": "月度销售额"}, measure_ref="MSR-001",
        expected_binding_revision=1, expected_measure_revision=1)
    assert row is None
    assert conflict is not None
    assert conflict["type"] == "measure_changed"
    assert conflict["canKeepMeasure"] is False
    assert conflict["mustReconfirm"] is False


def test_binding_changed_conflict_allows_measure_but_requires_reconfirm(bind_service):
    """另一份同编号绑定的指标名被改：所选度量可沿用，但须重新取得编辑确认。"""
    bind_service.update_fields(1, {"指标名称": "月度销售额-他人改"})

    row, conflict = bind_service.commit_edit(
        1, fields={"指标名称": "月度销售额"}, measure_ref="MSR-001",
        expected_binding_revision=1, expected_measure_revision=1)
    assert row is None
    assert conflict is not None
    assert conflict["type"] == "binding_changed"
    assert conflict["canKeepMeasure"] is True
    assert conflict["mustReconfirm"] is True


def test_both_changed_reports_combined_conflict(bind_service):
    bind_service.update_fields(1, {"指标名称": "月度销售额-他人改"})
    service_for("measure_catalog").update_fields(1, {"度量名称": "日销售额-他人改"})

    row, conflict = bind_service.commit_edit(
        1, fields={"指标名称": "月度销售额"}, measure_ref="MSR-001",
        expected_binding_revision=1, expected_measure_revision=1)
    assert row is None
    assert conflict["type"] == "binding_and_measure_changed"
    assert conflict["canKeepMeasure"] is False
    assert conflict["mustReconfirm"] is True


def test_invalid_binding_cannot_be_edited(bind_service):
    row, conflict = bind_service.commit_edit(
        3, fields={"指标名称": "季度毛利"}, measure_ref="MSR-003",
        expected_binding_revision=1, expected_measure_revision=1)
    assert row is None
    assert conflict["type"] == "binding_invalid"
    assert conflict["mustReconfirm"] is False


def test_duplicate_invalid_binding_creates_new_pending(bind_service):
    copy = bind_service.duplicate_binding(3)
    assert copy is not None
    assert copy["status"] == "待生效"
    assert copy["引用度量"] == "MSR-003"
    assert copy["绑定编号"] != "BND-003"


def test_restore_only_for_released_binding(bind_service):
    row, message = bind_service.restore_binding(3)
    assert row is not None
    assert row["status"] == "待生效"
    assert "重新启用" in message

    rejected, message = bind_service.restore_binding(1)
    assert rejected is None
    assert "不能重新启用" in message


def test_route_context_endpoint_shape():
    from app.routers import resource
    from app.schemas import ApplyMeasurePayload

    payload = resource.metric_bind_context(1)
    assert payload["binding"]["code"] == "BND-001"

    result = resource.commit_metric_bind_edit(
        1,
        ApplyMeasurePayload(
            measureRef="MSR-001",
            values={"指标名称": "月度销售额"},
            expectedBindingRevision=1,
            expectedMeasureRevision=1,
        ),
    )
    assert result.ok is True
    assert result.entry is not None


def test_route_conflict_surfaces_typed_result():
    from app.routers import resource
    from app.schemas import ApplyMeasurePayload

    resource.update_metric_bind(1, __import__("app.schemas", fromlist=["UpdatePayload"]).UpdatePayload(
        values={"指标名称": "他人改"}, expectedRevision=1))
    result = resource.commit_metric_bind_edit(
        1,
        ApplyMeasurePayload(
            measureRef="MSR-001",
            values={"指标名称": "我的"},
            expectedBindingRevision=1,
            expectedMeasureRevision=1,
        ),
    )
    assert result.ok is False
    assert result.conflict is not None
    assert result.conflict.type == "binding_changed"
    assert result.conflict.canKeepMeasure is True


def test_route_rejects_unknown_binding_code():
    from fastapi import HTTPException

    from app.routers import resource

    try:
        resource.resolve_metric_bind_by_code("BND-404")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("expected 404")
