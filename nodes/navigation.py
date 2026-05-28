from __future__ import annotations

from copy import deepcopy
from typing import Any


HOME_LABEL = "처음으로"
PREVIOUS_LABEL = "이전단계"
HOME_ALIASES = {"처음으로", "처음부터", "처음", "메인", "홈"}
HOME_REQUESTS = {"처음으로", "처음", "메인", "홈"}
PREVIOUS_REQUESTS = {"이전단계", "이전 단계", "뒤로", "이전"}

MAIN_MENU_REPLIES = [
    ("📝 자기소개서 작성", "자기소개서 작성"),
    ("💼 일자리 검색", "일자리 검색"),
    ("🎓 교육 추천", "교육 추천"),
]


def is_home_request(text: str) -> bool:
    return text.strip() in HOME_REQUESTS


def is_previous_request(text: str) -> bool:
    return text.strip() in PREVIOUS_REQUESTS


def main_menu_response(text: str) -> dict[str, Any]:
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}],
            "quickReplies": [
                {"action": "message", "label": label, "messageText": message_text}
                for label, message_text in MAIN_MENU_REPLIES
            ],
        },
    }


def _is_main_menu_response(response: dict[str, Any]) -> bool:
    template = response.get("template") or {}
    quick_replies = template.get("quickReplies") or []
    if len(quick_replies) != len(MAIN_MENU_REPLIES):
        return False
    expected = {message_text for _, message_text in MAIN_MENU_REPLIES}
    actual = {reply.get("messageText") for reply in quick_replies}
    return actual == expected


def _reply_text(reply: dict[str, Any]) -> str:
    return str(reply.get("messageText") or reply.get("label") or "").strip()


def _dedupe_navigation_replies(
    quick_replies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    has_home = False

    for reply in quick_replies:
        text = _reply_text(reply)
        if text in HOME_ALIASES:
            if has_home:
                continue
            has_home = True
            seen.add("home")
        elif text in seen:
            continue
        else:
            seen.add(text)
        cleaned.append(reply)

    return cleaned


def add_navigation_buttons(response: dict[str, Any] | None) -> dict[str, Any] | None:
    if not response or not isinstance(response, dict):
        return response
    if _is_main_menu_response(response):
        return response

    result = deepcopy(response)
    template = result.setdefault("template", {})
    quick_replies = template.setdefault("quickReplies", [])
    quick_replies = _dedupe_navigation_replies(quick_replies)
    template["quickReplies"] = quick_replies
    existing = {_reply_text(reply) for reply in quick_replies}
    has_home = any(text in HOME_ALIASES for text in existing)

    if not has_home:
        quick_replies.append(
            {"action": "message", "label": HOME_LABEL, "messageText": HOME_LABEL}
        )

    if PREVIOUS_LABEL not in existing:
        quick_replies.append(
            {"action": "message", "label": PREVIOUS_LABEL, "messageText": PREVIOUS_LABEL}
        )

    return result
