import httpx
import config

_SECTION_LABELS = ["성장과정", "지원동기", "직무 경험 및 강점", "입사 후 포부"]
_SEND_URL = "https://kapi.kakao.com/v1/api/talk/friends/message/default/send"


async def _send_one(plus_friend_key: str, text: str) -> None:
    headers = {
        "Authorization": f"KakaoAK {config.KAKAO_REST_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "receiver_uuids": [plus_friend_key],
        "template_object": {
            "object_type": "text",
            "text": text,
            "link": {},
        },
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(_SEND_URL, headers=headers, json=body, timeout=10.0)
        if resp.status_code != 200:
            raise RuntimeError(f"카카오 API 오류 {resp.status_code}: {resp.text}")


async def send_resume_sections(plus_friend_key: str, sections: list[str]) -> None:
    """자소서 항목을 2개 말풍선으로 묶어 카카오 채널 메시지로 푸시."""
    total = len(_SECTION_LABELS)

    # 말풍선 1: 성장과정 + 지원동기
    bubble1 = "\n\n".join(
        f"📌 {i + 1}/{total} {_SECTION_LABELS[i]}\n{sections[i]}"
        for i in range(2)
    )
    # 말풍선 2: 직무 경험 및 강점 + 입사 후 포부
    bubble2 = "\n\n".join(
        f"📌 {i + 1}/{total} {_SECTION_LABELS[i]}\n{sections[i]}"
        for i in range(2, 4)
    )

    await _send_one(plus_friend_key, bubble1)
    await _send_one(plus_friend_key, bubble2)
