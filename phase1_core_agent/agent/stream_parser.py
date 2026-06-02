from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple, Union

from schemas import ControlPacket, EmotionPayload, MotionPayload


EMOTION_PATTERN = re.compile(r'<emotion(?:\s+intensity="([0-9.]+)")?>([a-z_]+)</emotion>')
MOTION_PATTERN = re.compile(r"<motion>([a-z_]+)</motion>")
THINKING_PATTERN = re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL)
PLAN_PATTERN = re.compile(r"<plan>(.*?)</plan>", re.DOTALL)
TOOL_PATTERN = re.compile(r'<tool\s+name="([a-zA-Z0-9_]+)">(.*?)</tool>', re.DOTALL)
TAG_OPEN_PATTERN = re.compile(r"<(emotion|motion|thinking|plan|tool)\b")
RESIDUAL_CONTROL_TAG_PATTERN = re.compile(
    r"<emotion\b[^>]*>.*?</emotion>|<motion>.*?</motion>|<thinking>.*?</thinking>|<plan>.*?</plan>|<tool\b[^>]*>.*?</tool>|</?(?:emotion|motion|thinking|plan|tool|arg)\b[^>]*>",
    re.DOTALL,
)
ENGLISH_STAGE_DIRECTION_PATTERN = re.compile(
    r"\s*\((?=[^()\n]{3,180}\))(?=[^()\n]*[A-Za-z])[^()\n]*\)\s*"
)


def strip_residual_control_tags(text: str) -> str:
    return RESIDUAL_CONTROL_TAG_PATTERN.sub("", text)


def strip_stage_directions(text: str) -> str:
    cleaned = ENGLISH_STAGE_DIRECTION_PATTERN.sub(" ", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n[ \t]+", "\n", cleaned)
    return cleaned.strip()


def _incomplete_stage_direction_start(text: str) -> Optional[int]:
    start = text.rfind("(")
    if start == -1:
        return None
    if ")" in text[start:]:
        return None
    candidate = text[start + 1 :]
    if "\n" in candidate or len(candidate) > 180:
        return None
    if not re.search(r"[A-Za-z]", candidate):
        return None
    return start


class StreamParser:
    def __init__(self) -> None:
        self.buffer = ""

    def feed(self, chunk: str) -> List[ControlPacket]:
        self.buffer += chunk
        return self._drain(flush=False)

    def flush(self) -> List[ControlPacket]:
        return self._drain(flush=True)

    def _drain(self, *, flush: bool) -> List[ControlPacket]:
        packets: List[ControlPacket] = []

        while self.buffer:
            match = self._find_earliest_match()
            if match is None:
                open_tag = TAG_OPEN_PATTERN.search(self.buffer)
                if open_tag and not flush:
                    prefix = self.buffer[: open_tag.start()]
                    if prefix:
                        packets.append(self._text_packet(prefix))
                        self.buffer = self.buffer[open_tag.start() :]
                    break

                incomplete_stage_start = _incomplete_stage_direction_start(self.buffer)
                if incomplete_stage_start is not None and not flush:
                    prefix = self.buffer[:incomplete_stage_start]
                    if prefix:
                        packets.append(self._text_packet(prefix))
                    self.buffer = self.buffer[incomplete_stage_start:]
                    break

                text = self.buffer
                self.buffer = ""
                if text:
                    packets.append(self._text_packet(text))
                break

            start, end, packet = match
            prefix = self.buffer[:start]
            if prefix:
                packets.append(self._text_packet(prefix))
            packets.append(packet)
            self.buffer = self.buffer[end:]

        return [packet for packet in packets if self._packet_has_visible_content(packet)]

    def _find_earliest_match(self) -> Optional[Tuple[int, int, ControlPacket]]:
        candidates: List[Tuple[int, int, ControlPacket]] = []

        for pattern_name, pattern in (
            ("emotion", EMOTION_PATTERN),
            ("motion", MOTION_PATTERN),
            ("thinking", THINKING_PATTERN),
            ("plan", PLAN_PATTERN),
            ("tool", TOOL_PATTERN),
        ):
            match = pattern.search(self.buffer)
            if match is None:
                continue
            if pattern_name == "emotion":
                intensity = float(match.group(1) or 1.0)
                payload = EmotionPayload(emotion_type=match.group(2), intensity=intensity)
                packet = ControlPacket(
                    event_type="emotion_trigger",
                    payload=payload,
                    timestamp=time.time(),
                )
            elif pattern_name == "motion":
                payload = MotionPayload(motion_type=match.group(1))
                packet = ControlPacket(
                    event_type="motion_trigger",
                    payload=payload,
                    timestamp=time.time(),
                )
            elif pattern_name == "thinking":
                packet = ControlPacket(
                    event_type="thinking_summary",
                    payload=match.group(1).strip(),
                    timestamp=time.time(),
                )
            elif pattern_name == "plan":
                packet = ControlPacket(
                    event_type="plan_summary",
                    payload=match.group(1).strip(),
                    timestamp=time.time(),
                )
            else:
                packet = ControlPacket(
                    event_type="tool_pending",
                    payload=self._parse_tool_payload(match.group(0)),
                    timestamp=time.time(),
                )
            candidates.append((match.start(), match.end(), packet))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0]

    def _parse_tool_payload(self, xml_text: str) -> Dict[str, Union[Dict[str, str], str]]:
        root = ET.fromstring(xml_text)
        args: Dict[str, str] = {}
        for child in root.findall("arg"):
            name = child.attrib.get("name")
            if name:
                args[name] = child.text or ""
        return {"tool_name": root.attrib.get("name", ""), "args": args}

    def _text_packet(self, text: str) -> ControlPacket:
        cleaned = self._clean_visible_text(text)
        return ControlPacket(
            event_type="text_chunk",
            payload=cleaned,
            timestamp=time.time(),
        )

    def _packet_has_visible_content(self, packet: ControlPacket) -> bool:
        if isinstance(packet.payload, str):
            return bool(packet.payload.strip())
        return True

    def _clean_visible_text(self, text: str) -> str:
        return strip_stage_directions(strip_residual_control_tags(text))
