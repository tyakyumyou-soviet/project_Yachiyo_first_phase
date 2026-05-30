from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class EmotionPayload(BaseModel):
    emotion_type: Literal["smile", "sad", "angry", "surprised", "neutral"]
    intensity: float = Field(default=1.0, ge=0.0, le=1.0)


class MotionPayload(BaseModel):
    motion_type: Literal["nod", "wave", "think", "tilt_head", "bow"]


class ToolApprovalPayload(BaseModel):
    tool_name: str
    args: Dict[str, str]
    reason: str


class ToolResultPayload(BaseModel):
    tool_name: str
    ok: bool
    result: str


class StatusPayload(BaseModel):
    status: str
    detail: Optional[str] = None


ControlPayload = Union[
    str,
    EmotionPayload,
    MotionPayload,
    ToolApprovalPayload,
    ToolResultPayload,
    StatusPayload,
    Dict[str, Any],
]


class ControlPacket(BaseModel):
    event_type: Literal[
        "text_chunk",
        "emotion_trigger",
        "motion_trigger",
        "thinking_summary",
        "plan_summary",
        "tool_pending",
        "memory_recall",
        "tool_approval_req",
        "tool_result",
        "system_status",
    ]
    payload: ControlPayload
    timestamp: float


class ChatRequest(BaseModel):
    text: str
    session_id: Optional[str] = None


class ModelSelectRequest(BaseModel):
    model_id: str


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ToolDefinition(BaseModel):
    name: str
    description: str
    args: Dict[str, str]
    destructive: bool = False


class SessionSnapshot(BaseModel):
    session_id: str
    history_size: int
    completed_turns: int
    recent_messages: List[ChatMessage]
