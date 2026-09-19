from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=512)
    device_id: str = Field(default="", max_length=120)
    device_name: str = Field(default="", max_length=120)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=1024)
    device_id: str = Field(default="", max_length=120)
    device_name: str = Field(default="", max_length=120)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=12, max_length=512)


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=512)
    role: Literal["admin", "user"] = "user"
    active: bool = True
    profiles: list[str] = Field(default_factory=list, max_length=100)


class UserUpdateRequest(BaseModel):
    role: Literal["admin", "user"] | None = None
    active: bool | None = None
    profiles: list[str] | None = Field(default=None, max_length=100)


class AdminPasswordResetRequest(BaseModel):
    password: str = Field(min_length=12, max_length=512)


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="allow")

    input: str | list[dict[str, Any]]
    session_id: str | None = None
    model: str | None = None
    instructions: str | None = None
    conversation_history: list[dict[str, Any]] | None = None
    idempotency_key: str | None = None


class ApprovalRequest(BaseModel):
    choice: Literal["once", "session", "always", "deny"]
    resolve_all: bool = False


class SteerRequest(BaseModel):
    input: str = Field(min_length=1, max_length=20000)


class HandoffCreate(BaseModel):
    profile: str
    session_id: str = Field(min_length=1, max_length=256)


class NotificationReadRequest(BaseModel):
    read: bool = True


class SavedPromptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=100000)
    profile: str | None = Field(default=None, max_length=64)


class SavedPromptUpdate(SavedPromptCreate):
    pass


class SessionMetadataUpdate(BaseModel):
    pinned: bool = False
    tags: list[str] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=4000)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        return [str(tag).strip() for tag in value if str(tag).strip()]


class GatewayTicketCreate(BaseModel):
    profile: str


class BackupCreateRequest(BaseModel):
    label: str = Field(default="manual", max_length=80)
