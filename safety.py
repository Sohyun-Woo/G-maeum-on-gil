"""
경기 마음온길 (Gyeonggi Maeum-on-Gil) — 안전 분기 로직 모듈

위기 신호·음주 상태 감지를 담당한다. 이 모듈의 핵심 설계 원칙:

  1) 안전 감지는 인터뷰보다 '우선'한다.
     - 사용자가 메시지를 보낼 때마다, 인터뷰 LLM을 호출하기 '전에'
       먼저 detect_safety()를 실행한다.
     - crisis 또는 intoxication 이 잡히면 인터뷰 LLM 호출을 건너뛰고
       즉시 안내 메시지로 전환한다.
     - 단 사용자가 괜찮다 인터뷰를 더 하고 싶다고 하면 다음 메시지로 넘어간다.

  2) [변경] 키워드 단독 판정 (A안).
     - 기존에는 LLM 분류기(1차)와 키워드 스캔(2차)을 OR 결합했으나,
       LLM 분류기가 우울감 등 정서 호소까지 광범위하게 crisis 로 분류하여
       정상적 인터뷰가 조기 중단되는 문제가 있었다.
     - 이를 해소하기 위해 판정 경로를 _CRISIS_KEYWORDS /
       _INTOXICATION_KEYWORDS 에 명시된 표현의 부분일치로만 한정한다.
     - LLM 분류 경로(_llm_classify, SAFETY_DETECT_PROMPT)는 호출부
       시그니처 호환을 위해 코드상 남겨두되, 판정에는 사용하지 않는다.

  3) 위기 우선순위.
     - crisis 와 intoxication 이 동시에 잡히면 crisis 안내를 우선한다.

근거: 국립정신건강센터 「정신건강위기상담전화 응대 매뉴얼」
      - 자·타해 위험성 평가 시 음주 상태 여부를 우선 확인
      - 위기 사정이 모호할 때는 고위험으로 간주하여 개입

주의(설계 한계): 키워드 단독 판정은 우회·완곡 표현의 재현율(recall)이
      낮다. 직접적 자·타해 표현은 _CRISIS_KEYWORDS 에 유지하고, 현장
      적용 단계에서는 이 한계를 문서에 명시해야 한다.
"""
import json
from dataclasses import dataclass

from prompts import SAFETY_DETECT_PROMPT


# ---------------------------------------------------------------------------
# 키워드 기반 안전망 (A안에서는 이것이 단독 판정 근거)
# 정밀도(precision)보다 재현율(recall)을 우선한다 — 놓치는 것이 더 위험.
#
# 자모 축약형(ㅈㅅ=자살, ㅈㅎ=자해 등)은 SNS·청소년 환경에서 검열 회피용으로
# 흔히 쓰인다. 다만 "ㅈㅅ"(죄송), "ㅈㅎ"(정확/자취 등) 같은 일상 약어와
# 충돌하므로 단독 자모가 아니라 '자모 + 동사 결합' 형태로만 잡는다.
# ---------------------------------------------------------------------------
_CRISIS_KEYWORDS = [
    # ── 직접 표현 ───────────────────────────────
    "죽고 싶", "죽고싶", "자살", "목숨", "목 매", "목매",
    "목숨을 끊", "사라지고 싶", "사라지고싶", "없어지고 싶",
    "끝내고 싶", "끝내버리", "끝내버릴", "살기 싫", "살기싫",
    "자해", "손목", "유서", "번개탄", "투신", "뛰어내리",
    "다 끝내", "이번 생", "죽어야",
]

_INTOXICATION_KEYWORDS = [
    "한잔했", "한잔걸쳐",
    "음주중", "술기운", "취했어", "취한상태", "만취",
]


def _keyword_scan(text: str) -> dict:
    """텍스트에서 위기·음주 키워드를 스캔한다 (LLM 비의존, 항상 동작)."""
    t = (text or "").replace(" ", "")
    crisis = any(kw.replace(" ", "") in t for kw in _CRISIS_KEYWORDS)
    intox = any(kw.replace(" ", "") in t for kw in _INTOXICATION_KEYWORDS)
    return {"crisis": crisis, "intoxication": intox}


# ---------------------------------------------------------------------------
# 감지 결과 자료구조
# ---------------------------------------------------------------------------
@dataclass
class SafetyResult:
    crisis: bool
    intoxication: bool
    reason: str
    source: str  # 'llm', 'keyword', 'llm+keyword', 'keyword-fallback'

    @property
    def is_blocked(self) -> bool:
        """인터뷰·시트 생성을 중단해야 하는 상태인가."""
        return self.crisis or self.intoxication

    @property
    def action(self) -> str:
        """전환 분기 이름. crisis 가 intoxication 보다 우선."""
        if self.crisis:
            return "crisis_redirect"
        if self.intoxication:
            return "intoxication_redirect"
        return "continue"


# ---------------------------------------------------------------------------
# LLM 분류기 호출
# [A안] 판정 경로에서는 사용하지 않는다. 호출부 호환·향후 B안 복원을 위해 보존.
# ---------------------------------------------------------------------------
def _llm_classify(client, user_message: str, model: str) -> dict | None:
    """
    SAFETY_DETECT_PROMPT 로 한 개 메시지를 분류한다.
    실패하면 None 을 반환한다.

    NOTE: 현재 detect_safety() 는 이 함수를 호출하지 않는다 (A안: 키워드 단독).
    """
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,  # 분류는 결정적으로
            max_tokens=200,
            messages=[
                {"role": "system", "content": SAFETY_DETECT_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        # 모델이 코드블록을 붙였을 경우 제거
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        return {
            "crisis": bool(data.get("crisis", False)),
            "intoxication": bool(data.get("intoxication", False)),
            "reason": str(data.get("reason", "")),
        }
    except Exception:
        # 네트워크 오류, JSON 파싱 실패 등
        return None


# ---------------------------------------------------------------------------
# 공개 함수: 안전 감지 (인터뷰 LLM 호출 전에 반드시 먼저 실행)
# [A안] 키워드 단독 판정. _CRISIS_KEYWORDS / _INTOXICATION_KEYWORDS 에
#       명시된 표현의 부분일치에서만 전환이 일어난다.
# ---------------------------------------------------------------------------
def detect_safety(client, user_message: str,
                  model: str = "gpt-4o-mini") -> SafetyResult:
    """
    사용자 메시지 1건에 대해 위기·음주 여부를 판정한다.

    A안: 키워드 단독 판정. LLM 분류기를 호출하지 않으므로, 리스트에
    명시되지 않은 정서 호소("우울해요" 등)는 통과하여 인터뷰가 계속된다.

    client, model 인자는 호출부 시그니처 호환을 위해 받기만 하고 쓰지 않는다.

    Parameters
    ----------
    client : OpenAI
        (미사용) openai 라이브러리의 클라이언트 인스턴스
    user_message : str
        방금 사용자가 입력한 메시지
    model : str
        (미사용) 분류용 모델

    Returns
    -------
    SafetyResult
    """
    kw = _keyword_scan(user_message)
    return SafetyResult(
        crisis=kw["crisis"],
        intoxication=kw["intoxication"],
        reason="키워드 기반 단독 판정",
        source="keyword",
    )
