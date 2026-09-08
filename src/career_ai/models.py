"""Strict public contracts for the portable Career AI workflow."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


NonEmpty = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=3, max_length=120)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


def relative_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("path must be workspace-relative and cannot contain '..'")
    return path.as_posix()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Binding(StrictModel):
    path: str
    sha256: Sha256

    _path = field_validator("path")(relative_path)


class WorkspaceStatus(str, Enum):
    ONBOARDING_REQUIRED = "onboarding_required"
    READY = "ready"


class WorkspaceManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    workspace_id: Slug
    project_name: NonEmpty
    subject_name: NonEmpty | None = None
    status: WorkspaceStatus = WorkspaceStatus.ONBOARDING_REQUIRED
    profile: Binding | None = None
    strategy: Binding | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def ready_requires_inputs(self) -> "WorkspaceManifest":
        if self.status is WorkspaceStatus.READY and (
            not self.subject_name or not self.profile or not self.strategy
        ):
            raise ValueError("ready workspace requires subject, profile and strategy")
        return self


class ProviderAdapter(str, Enum):
    MANUAL = "manual"
    OPENAI_RESPONSES = "openai_responses"
    OPENAI_COMPATIBLE_CHAT = "openai_compatible_chat"


class ProviderProfile(StrictModel):
    provider_id: Slug
    display_name: NonEmpty
    adapter: ProviderAdapter
    model: NonEmpty
    endpoint_url: NonEmpty | None = None
    api_key_env: Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]+$")] | None = None
    enabled: bool = False
    allow_personal_data: bool = False
    structured_outputs: bool = True
    timeout_seconds: Annotated[int, Field(ge=5, le=600)] = 180

    @model_validator(mode="after")
    def validate_adapter(self) -> "ProviderProfile":
        if self.adapter is ProviderAdapter.MANUAL:
            if self.endpoint_url or self.api_key_env:
                raise ValueError("manual provider cannot contain endpoint or credential")
        elif not self.endpoint_url or not self.api_key_env:
            raise ValueError("HTTP provider requires endpoint and credential environment name")
        elif self.endpoint_url:
            parsed = urlparse(self.endpoint_url)
            if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("remote provider endpoints must use HTTPS")
        return self


class AppConfig(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    default_provider_id: Slug
    providers: Annotated[list[ProviderProfile], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_providers(self) -> "AppConfig":
        ids = [item.provider_id for item in self.providers]
        if len(ids) != len(set(ids)):
            raise ValueError("provider IDs must be unique")
        if self.default_provider_id not in ids:
            raise ValueError("default provider must exist")
        return self


class JobRecord(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    job_id: Slug
    company: NonEmpty
    role: NonEmpty
    source_url: NonEmpty | None = None
    source: Binding
    captured_at: datetime


class AIRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: Slug
    capability: Literal["evaluate-job", "write-application"]
    provider_id: Slug
    instructions: NonEmpty
    inputs: Annotated[list[Binding], Field(min_length=1)]
    output_schema: Binding
    output_schema_name: Slug
    max_output_tokens: Annotated[int, Field(ge=128, le=50000)] = 4000
    created_at: datetime


class TokenUsage(StrictModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class AIResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    result_id: Slug
    request: Binding
    provider_id: Slug
    model: NonEmpty
    status: Literal["manual_pending", "completed", "failed"]
    output: Binding | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    error: NonEmpty | None = None
    completed_at: datetime

    @model_validator(mode="after")
    def validate_status(self) -> "AIResult":
        if self.status == "completed" and (self.output is None or self.error is not None):
            raise ValueError("completed result requires output and no error")
        if self.status == "failed" and not self.error:
            raise ValueError("failed result requires an error")
        if self.status == "manual_pending" and (self.output is not None or self.error is not None):
            raise ValueError("manual pending result cannot contain output or error")
        return self


class JobEvaluation(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    job_id: Slug
    recommendation: Literal["apply", "consider", "reject"]
    summary: NonEmpty
    strengths: Annotated[list[NonEmpty], Field(min_length=1, max_length=6)]
    gaps: Annotated[list[NonEmpty], Field(max_length=6)] = Field(default_factory=list)
    conditions: Annotated[list[NonEmpty], Field(max_length=6)] = Field(default_factory=list)
    evidence_used: Annotated[list[NonEmpty], Field(min_length=1, max_length=12)]
    confidence: Annotated[float, Field(ge=0, le=1)]


class ContentSection(StrictModel):
    heading: NonEmpty
    content: Annotated[list[NonEmpty], Field(min_length=1)]


class ApplicationContent(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    job_id: Slug
    cv_sections: Annotated[list[ContentSection], Field(min_length=3)]
    cover_letter_sections: Annotated[list[ContentSection], Field(min_length=3)]
    omitted_claims: list[NonEmpty] = Field(default_factory=list)
    review_notes: list[NonEmpty] = Field(default_factory=list)
