"""通用接口契约；模块字段由领域服务持有，不再为每个模块复制一份模型类。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ActionPayload(BaseModel):
    action: str
    remark: str | None = None


class UpdatePayload(BaseModel):
    """带版本号的局部更新：expectedRevision 为空时按强制更新处理。"""

    values: dict[str, Any] = Field(default_factory=dict)
    expectedRevision: int | None = None


class ApplyMeasurePayload(BaseModel):
    """绑定页选完度量后的提交：同时核对绑定与度量两份版本。"""

    measureRef: str
    values: dict[str, Any] = Field(default_factory=dict)
    expectedBindingRevision: int | None = None
    expectedMeasureRevision: int | None = None


class ConflictInfo(BaseModel):
    """冲突分型：能否沿用当前所选度量、是否须重新取得编辑确认，由领域服务判定。"""

    type: str
    message: str
    canKeepMeasure: bool
    mustReconfirm: bool
    binding: dict[str, Any] | None = None
    measure: dict[str, Any] | None = None


class EditResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None
    conflict: ConflictInfo | None = None
