"""
경기 마음온길 (Gyeonggi Maeum-on-Gil) — 안전 분기 로직 모듈

위기 신호·음주 상태 감지를 담당한다. 이 모듈의 핵심 설계 원칙:

  1) 안전 감지는 인터뷰보다 '우선'한다.
     - 사용자가 메시지를 보낼 때마다, 인터뷰 LLM을 호출하기 '전에'
       먼저 detect_safety()를 실행한다.
     - crisis 또는 intoxication 이 잡히면 인터뷰 LLM 호출을 건너뛰고
       즉시 안내 메시지로 전환한다.
     - 단 사용자가 괜찮다 인터뷰를 더 하고 싶다고 하면 다음 메시지로 넘어간다.

  2) 이중 안전망 (defense in depth).
     - LLM 기반 분류기 1차. LLM 호출 실패·오류 시에도 안전이 무너지지
       않도록, 키워드 기반 2차 검사를 둔다.
     - 둘 중 하나라도 crisis 를 보고하면 crisis 로 처리한다 (OR 결합).
     - '의심되면 위기로 본다'는 응대 매뉴얼 원칙을 코드로 구현.

  3) 위기 우선순위.
     - crisis 와 intoxication 이 동시에 잡히면 crisis 안내를 우선한다.

근거: 국립정신건강센터 「정신건강위기상담전화 응대 매뉴얼」
      - 자·타해 위험성 평가 시 음주 상태 여부를 우선 확인
      - 위기 사정이 모호할 때는 고위험으로 간주하여 개입
"""
import json
from dataclasses import dataclass

from prompts import SAFETY_DETECT_PROMPT


# ---------------------------------------------------------------------------
# 키워드 기반 2차 안전망
# LLM 분류기가 실패하거나 위기를 놓쳤을 때를 대비한 보수적 백업.
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
    "술 마시", "술마시", "술 먹", "술먹", "취했", "취해",
    "음주 중", "음주중", "한 잔 했", "한잔했", "술기운",
    "소주", "맥주", "막걸리",
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
# ---------------------------------------------------------------------------
def _llm_classify(client, user_message: str, model: str) -> dict | None:
    """
    SAFETY_DETECT_PROMPT 로 한 개 메시지를 분류한다.
    실패하면 None 을 반환한다 (호출부에서 키워드 백업으로 폴백).
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
        # 네트워크 오류, JSON 파싱 실패 등 — 안전 백업으로 폴백
        return None


# ---------------------------------------------------------------------------
# 공개 함수: 안전 감지 (인터뷰 LLM 호출 전에 반드시 먼저 실행)
# ---------------------------------------------------------------------------
def detect_safety(client, user_message: str,
                  model: str = "gpt-4o-mini") -> SafetyResult:
    """
    사용자 메시지 1건에 대해 위기·음주 여부를 판정한다.

    LLM 분류 결과와 키워드 스캔 결과를 OR 로 결합한다.
    어느 한쪽이라도 위험을 보고하면 위험으로 간주한다.

    Parameters
    ----------
    client : OpenAI
        openai 라이브러리의 클라이언트 인스턴스
    user_message : str
        방금 사용자가 입력한 메시지
    model : str
        분류용 모델 (저비용 모델 권장)

    Returns
    -------
    SafetyResult
    """
    kw = _keyword_scan(user_message)
    llm = _llm_classify(client, user_message, model)

    if llm is None:
        # LLM 실패 — 키워드 결과만으로 보수적으로 판정
        return SafetyResult(
            crisis=kw["crisis"],
            intoxication=kw["intoxication"],
            reason="안전 분류기 응답 실패 — 키워드 기반 백업 판정 적용",
            source="keyword-fallback",
        )

    # OR 결합: 둘 중 하나라도 True 면 True
    crisis = llm["crisis"] or kw["crisis"]
    intox = llm["intoxication"] or kw["intoxication"]

    # source 표기
    if crisis or intox:
        llm_hit = llm["crisis"] or llm["intoxication"]
        kw_hit = kw["crisis"] or kw["intoxication"]
        if llm_hit and kw_hit:
            source = "llm+keyword"
        elif llm_hit:
            source = "llm"
        else:
            source = "keyword"
    else:
        source = "llm"

    reason = llm["reason"] or "키워드 스캔에서 신호 감지"
    return SafetyResult(crisis=crisis, intoxication=intox,
                        reason=reason, source=source)
