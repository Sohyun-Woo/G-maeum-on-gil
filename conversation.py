"""
경기 마음온길 (Gyeonggi Maeum-on-Gil) — 대화 엔진 모듈

ChatGPT API 를 호출하는 두 가지 핵심 기능을 제공한다.

  run_interview_turn()  : 인터뷰 한 턴을 진행하고 다음 질문(또는 완료 신호)을 받는다.
  summarize_to_sheet()  : 누적된 대화 전체를 사전정리 시트(dict)로 정리한다.

사용 순서 (전체 흐름):

  사용자 입력
      │
      ▼
  detect_safety()  ──(crisis/intoxication)──▶  안내 메시지로 전환, 인터뷰 중단
      │ continue
      ▼
  run_interview_turn()
      │
      ├─ 완료 토큰 없음 ──▶ 다음 질문을 사용자에게 표시, 대화 계속
      │
      └─ 완료 토큰 감지 ──▶ summarize_to_sheet() ──▶ docx 생성 (sheet_builder)

설계 원칙:
  - 안전 감지는 이 모듈 밖(호출부)에서 '먼저' 수행한다. 이 모듈은
    안전이 확인된 메시지만 받는다고 가정한다.
  - 시트 정리는 JSON 출력을 강제하고, 파싱 실패 시 예외를 던진다.
"""
import json

from prompts import (
    build_interview_system_prompt,
    build_sheet_summary_prompt,
    COMPLETION_TOKEN,
    _items_for_user_type,
)


# ---------------------------------------------------------------------------
# 인터뷰 한 턴 진행
# ---------------------------------------------------------------------------
def run_interview_turn(client, user_type: str, history: list,
                       model: str = "gpt-4o-mini") -> dict:
    """
    인터뷰 한 턴을 진행한다.

    Parameters
    ----------
    client : OpenAI
        openai 클라이언트
    user_type : str
        'self'(당사자) 또는 'family'(가족)
    history : list[dict]
        지금까지의 대화. 각 원소는 {"role": "user"/"assistant", "content": str}.
        system 메시지는 포함하지 않는다 (이 함수가 매번 앞에 붙인다).
    model : str
        대화용 모델

    Returns
    -------
    dict
        {
          "assistant_message": str,   # 사용자에게 보여줄 응답(완료 토큰 제거됨)
          "is_complete": bool,        # 9개 항목 수집 완료 여부
        }
    """
    system_prompt = build_interview_system_prompt(user_type)
    messages = [{"role": "system", "content": system_prompt}] + history

    resp = client.chat.completions.create(
        model=model,
        temperature=0.5,
        max_tokens=400,
        messages=messages,
    )
    content = resp.choices[0].message.content.strip()

    # 완료 토큰 감지 및 제거
    is_complete = COMPLETION_TOKEN in content
    if is_complete:
        content = content.replace(COMPLETION_TOKEN, "").strip()

    return {"assistant_message": content, "is_complete": is_complete}


# ---------------------------------------------------------------------------
# 대화 전체 → 사전정리 시트(dict)
# ---------------------------------------------------------------------------
def summarize_to_sheet(client, user_type: str, history: list,
                       model: str = "gpt-4o-mini") -> dict:
    """
    누적 대화를 사전정리 시트 항목별 dict 로 정리한다.

    Parameters
    ----------
    client : OpenAI
    user_type : str
        'self' 또는 'family'
    history : list[dict]
        인터뷰 전체 대화 기록 (system 제외)
    model : str

    Returns
    -------
    dict
        SHEET_ITEMS 의 id 를 키로 갖는 정리 결과.
        예: {"basic_info": "...", "main_concern": "...", ...}

    Raises
    ------
    ValueError
        모델 응답을 JSON 으로 파싱할 수 없을 때
    """
    system_prompt = build_sheet_summary_prompt(user_type)

    # 대화 전체를 하나의 입력 텍스트로 합쳐 전달
    transcript_lines = []
    for msg in history:
        speaker = "이용자" if msg["role"] == "user" else "도우미"
        transcript_lines.append(f"{speaker}: {msg['content']}")
    transcript = "\n".join(transcript_lines)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "다음은 정리할 대화입니다.\n\n" + transcript},
    ]

    resp = client.chat.completions.create(
        model=model,
        temperature=0,  # 정리는 결정적으로
        max_tokens=1200,
        messages=messages,
    )
    raw = resp.choices[0].message.content.strip()

    # 코드블록 방어
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"시트 정리 응답을 JSON 으로 읽지 못했습니다: {e}")

    # 누락 키는 빈 문자열로 보정 (스키마 안정성)
    result = {}
    for item in _items_for_user_type(user_type):
        result[item["id"]] = str(data.get(item["id"], "")).strip()
    return result
