"""
경기 마음온길 (Gyeonggi Maeum-on-Gil) — 대화 엔진 모듈
 
ChatGPT API 를 호출하는 두 가지 핵심 기능을 제공한다.
 
  run_interview_turn()  : 인터뷰 한 턴을 진행하고 다음 질문(또는 완료 신호)을 받는다.
  summarize_to_sheet()  : 누적된 대화 전체를 사전정리 시트(dict)로 정리한다.
 
[변경 — 이번 차수]
  - run_interview_turn(..., known_region=None) 추가.
    intake 에서 받은 거주 시·군을 전달하면 인터뷰 LLM 이 거주지를
    다시 묻지 않는다(build_interview_system_prompt 로 위임).
  - summarize_to_sheet(..., known_region=None) 추가.
    정리 시 거주 지역을 시스템 컨텍스트로 함께 넘겨, basic_info 에
    지역이 누락되지 않도록 한다.
 
설계 원칙:
  - 안전 감지는 이 모듈 밖(호출부)에서 '먼저' 수행한다.
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
                       model: str = "gpt-4o-mini",
                       known_region: str | None = None) -> dict:
    """
    인터뷰 한 턴을 진행한다.
 
    Parameters
    ----------
    client : OpenAI
    user_type : str
        'self'(당사자) 또는 'family'(가족)
    history : list[dict]
        지금까지의 대화 (system 제외)
    model : str
    known_region : str | None
        intake 에서 이미 받은 거주 시·군. 주어지면 인터뷰 LLM 이
        거주지를 다시 묻지 않는다.
 
    Returns
    -------
    dict
        {"assistant_message": str, "is_complete": bool}
    """
    system_prompt = build_interview_system_prompt(user_type, known_region)
    messages = [{"role": "system", "content": system_prompt}] + history
 
    resp = client.chat.completions.create(
        model=model,
        temperature=0.5,
        max_tokens=400,
        messages=messages,
    )
    content = resp.choices[0].message.content.strip()
 
    is_complete = COMPLETION_TOKEN in content
    if is_complete:
        content = content.replace(COMPLETION_TOKEN, "").strip()
 
    return {"assistant_message": content, "is_complete": is_complete}
 
 
# ---------------------------------------------------------------------------
# 대화 전체 → 사전정리 시트(dict)
# ---------------------------------------------------------------------------
def summarize_to_sheet(client, user_type: str, history: list,
                       model: str = "gpt-4o-mini",
                       known_region: str | None = None) -> dict:
    """
    누적 대화를 사전정리 시트 항목별 dict 로 정리한다.
 
    known_region 이 주어지면 거주 지역을 시스템 컨텍스트로 함께 넘겨
    basic_info 에 지역이 빠지지 않도록 한다.
 
    Raises
    ------
    ValueError
        모델 응답을 JSON 으로 파싱할 수 없을 때
    """
    system_prompt = build_sheet_summary_prompt(user_type)
    if known_region:
        system_prompt += (
            f"\n\n[대화 시작 전 확인된 정보]\n"
            f"거주 지역: {known_region}. basic_info 항목에 이 지역을 반드시 포함하세요."
        )
 
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
        temperature=0,
        max_tokens=1200,
        messages=messages,
    )
    raw = resp.choices[0].message.content.strip()
 
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
 
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"시트 정리 응답을 JSON 으로 읽지 못했습니다: {e}")
 
    result = {}
    for item in _items_for_user_type(user_type):
        result[item["id"]] = str(data.get(item["id"], "")).strip()
    return result
