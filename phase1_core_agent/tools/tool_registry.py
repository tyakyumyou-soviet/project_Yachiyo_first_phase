from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from schemas import ToolDefinition
from tools.pc_control import delete_file, list_directory, read_text_file, write_text_file
from tools.time_calendar import get_current_date, get_current_time
from tools.web_search import search_web


ToolHandler = Callable[..., Any]


TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "definition": ToolDefinition(
            name="get_current_time",
            description="Return the current local datetime in ISO 8601 format.",
            args={},
            destructive=False,
        ),
        "handler": get_current_time,
    },
    {
        "definition": ToolDefinition(
            name="get_current_date",
            description="Return the current local date in ISO 8601 format.",
            args={},
            destructive=False,
        ),
        "handler": get_current_date,
    },
    {
        "definition": ToolDefinition(
            name="list_directory",
            description="List files and folders under a workspace-relative path.",
            args={"path": "Workspace-relative or absolute path."},
            destructive=False,
        ),
        "handler": list_directory,
    },
    {
        "definition": ToolDefinition(
            name="read_text_file",
            description="Read a UTF-8 text file from the allowed workspace roots.",
            args={"path": "Workspace-relative or absolute path."},
            destructive=False,
        ),
        "handler": read_text_file,
    },
    {
        "definition": ToolDefinition(
            name="write_text_file",
            description="Write UTF-8 text to a file under the allowed workspace roots.",
            args={"path": "Target path.", "content": "Full file contents."},
            destructive=True,
        ),
        "handler": write_text_file,
    },
    {
        "definition": ToolDefinition(
            name="delete_file",
            description="Delete a file under the allowed workspace roots.",
            args={"path": "Target path."},
            destructive=True,
        ),
        "handler": delete_file,
    },
    {
        "definition": ToolDefinition(
            name="search_web",
            description="Search the web and return short extracted summaries from top pages.",
            args={"query": "Search query."},
            destructive=False,
        ),
        "handler": search_web,
    },
]


def render_tool_definitions() -> str:
    lines: List[str] = []
    for tool in TOOL_DEFINITIONS:
        definition: ToolDefinition = tool["definition"]
        rendered_args = ", ".join(f"{name}: {description}" for name, description in definition.args.items()) or "none"
        lines.append(
            f"- {definition.name}: {definition.description} / destructive={definition.destructive} / args: {rendered_args}"
        )
    return "\n".join(lines)


def get_tool(name: str) -> Optional[Dict[str, Any]]:
    for tool in TOOL_DEFINITIONS:
        definition: ToolDefinition = tool["definition"]
        if definition.name == name:
            return tool
    return None


def get_tool_catalog() -> List[Dict[str, Any]]:
    return [tool["definition"].model_dump(mode="json") for tool in TOOL_DEFINITIONS]
