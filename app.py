"""
경기 마음온길 (Gyeonggi Maeum-on-Gil) — Streamlit 통합 (app.py)

[변경 요약 — 이번 차수]
  - select 와 interview 사이에 'intake' 단계 추가.
      └ 거주 지역(경기도 시·군)을 받고, 그 목적("주변 정신건강 자원을
        찾기 위해서만 사용")을 명시. 데이터 최소화 — 이름·식별정보는
        받지 않으며, 연령대만 선택(선택사항)으로 둔다.
  - 받은 region/age_group 을 summarize 후 sheet_data 에 주입해
    find_resources() 의 지역 매칭과 사전정리 시트에 함께 반영.

[이전 차수 유지]
  - 위기/음주 감지 시 '하드 종료' 대신 안전 자원 안내 + "계속/그만" 선택.
  - safety.py 는 A안(키워드 단독) 버전이 배포되어 있어야 한다.

핵심 흐름:
  ① 이용자 유형 선택 (당사자 / 가족)
  ② [신규] intake — 거주 지역(+연령대) 입력
  ③ 사용자 메시지 입력
  ④ [안전 우선] detect_safety() — 위기·음주 감지가 인터뷰보다 먼저
       └ 차단 시: blocked 단계(인터뷰 호출 안 함)
  ⑤ run_interview_turn() — 다음 질문 or 완료 신호
  ⑥ 완료 시: summarize_to_sheet() → find_resources() → 다운로드

실행: streamlit run app.py
필요: pip install streamlit openai python-docx
"""
import streamlit as st
from openai import OpenAI

from prompts import (
    CRISIS_CONTACT_LINE,
    CRISIS_REDIRECT_MESSAGE,
    INTOXICATION_REDIRECT_MESSAGE,
)
from safety import detect_safety
from conversation import run_interview_turn, summarize_to_sheet
from sheet_builder import build_sheet_docx
from resources import find_resources, load_resources_from_files


st.set_page_config(page_title="경기 마음온길", page_icon="🤝", layout="centered")

# 모델 설정
CHAT_MODEL = "gpt-4o-mini"
SAFETY_MODEL = "gpt-4o-mini"
MAX_TURNS = 30  # API 비용 보호

# 안전 자원 번호 (2026년 기준)
SAFETY_LINES_MD = (
    "- **자살예방 상담전화 109** — 24시간, 비밀 보장\n"
    "- **정신건강 상담전화 1577-0199**\n"
    "- **긴급한 위급 상황 119**"
)

# 거주 지역 옵션 — 경기도 31개 시·군 (자원 매칭용)
GYEONGGI_REGIONS = [
    "수원시", "고양시", "용인시", "성남시", "부천시", "화성시", "안산시",
    "남양주시", "안양시", "평택시", "시흥시", "파주시", "의정부시", "김포시",
    "광주시", "광명시", "군포시", "하남시", "오산시", "양주시", "이천시",
    "구리시", "안성시", "포천시", "의왕시", "여주시", "동두천시", "과천시",
    "가평군", "양평군", "연천군",
]
REGION_PLACEHOLDER = "— 지역을 선택해 주세요 —"
REGION_OTHER = "경기도 외 / 잘 모르겠어요"

AGE_GROUPS = [
    "선택 안 함", "10대", "20대", "30대", "40대", "50대", "60대", "70대 이상",
]


# ---------------------------------------------------------------------------
# 세션 상태 초기화
# ---------------------------------------------------------------------------
def init_state():
    ss = st.session_state
    ss.setdefault("user_type", None)        # 'self' | 'family'
    ss.setdefault("region", None)           # 거주 시·군
    ss.setdefault("age_group", None)        # 연령대 (선택)
    ss.setdefault("history", [])            # 대화 기록 (system 제외)
    ss.setdefault("phase", "select")        # select | intake | interview | blocked | ended | summarize | done
    ss.setdefault("block_kind", None)       # 'crisis' | 'intoxication'
    ss.setdefault("sheet_data", None)
    ss.setdefault("resource_match", None)
    ss.setdefault("turn_count", 0)


def _resolve_api_key() -> str:
    """Streamlit secrets 에서 API 키를 가져온다."""
    try:
        return (st.secrets.get("OPENAI_API_KEY", "") or "").strip()
    except (FileNotFoundError, AttributeError):
        return ""


def get_client() -> OpenAI:
    """secrets 키로 OpenAI 클라이언트 생성."""
    return OpenAI(api_key=_resolve_api_key())


def _api_key_ok() -> bool:
    """API 키가 유효한 형식인지 확인."""
    key = _resolve_api_key()
    return key.startswith("sk-") and len(key) > 20


def _require_api_key() -> bool:
    """API 키 미설정 시 안내 메시지 표시 (운영자 환경 점검용)."""
    if _api_key_ok():
        return True
    st.error(
        "운영자 API Key 가 설정되어 있지 않습니다. "
        "Streamlit Cloud → Settings → Secrets 에서 `OPENAI_API_KEY` 를 등록해 주세요."
    )
    return False


# ---------------------------------------------------------------------------
# 사이드바
# ---------------------------------------------------------------------------
def render_sidebar():
    with st.sidebar:
        st.title("🤝 경기 마음온길")
        st.caption("정신건강 자원 안내·사전정리 AI 챗봇")
        st.divider()
        st.text_input("작성자 이니셜 (선택)", key="author_initial",
                      placeholder="예: ㅇㅅㅎ")
        st.divider()
        # 현재 진행 상태 표시
        ut = st.session_state.get("user_type")
        if ut == "self":
            st.caption("👤 현재: 당사자 본인 진행 중")
        elif ut == "family":
            st.caption("👪 현재: 가족·보호자 진행 중")
        if st.session_state.get("region"):
            st.caption(f"📍 지역: {st.session_state.region}")
        st.caption(f"대화 사용: {st.session_state.turn_count}/{MAX_TURNS}회")
        if st.button("🔄 처음부터 다시"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


# ---------------------------------------------------------------------------
# 단계 1: 이용자 유형 선택
# ---------------------------------------------------------------------------
def render_select():
    st.title("경기마음온길에 오신 것을 환영합니다")
    st.write(
        "마음이 힘들 때, 어디에 도움을 청해야 할지 막막하셨나요? "
        "편하게 이야기해 주시면, 가까운 정신건강 기관을 안내해 드리고 "
        "상담 시 가져갈 수 있는 사전정리 시트를 함께 만들어 드립니다."
    )
    st.info(
        "경기 마음온길은 의료 진단·치료를 하지 않습니다. "
        "지금 매우 힘드시다면 " + CRISIS_CONTACT_LINE + " 로 연락해 주세요."
    )
    st.subheader("어떤 분이 이용하시나요?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🙋 제 마음의 어려움을 정리하고 싶어요\n(당사자 본인)",
                     use_container_width=True):
            st.session_state.user_type = "self"
            st.session_state.phase = "intake"
            st.rerun()
    with col2:
        if st.button("👪 가족의 어려움을 도와주고 싶어요\n(가족·보호자)",
                     use_container_width=True):
            st.session_state.user_type = "family"
            st.session_state.phase = "intake"
            st.rerun()


# ---------------------------------------------------------------------------
# 단계 1b: intake — 거주 지역(+연령대) 입력
# ---------------------------------------------------------------------------
def render_intake():
    ss = st.session_state
    st.title("거의 다 됐어요")
    st.write(
        "혹시 사시는 곳이 어디인가요? "
        "주변의 정신건강 자원을 찾기 위해서만 사용되며, 따로 저장되지 않습니다."
    )

    region = st.selectbox(
        "거주 지역 (시·군)",
        options=[REGION_PLACEHOLDER] + GYEONGGI_REGIONS + [REGION_OTHER],
        index=0,
    )

    age_group = st.selectbox(
        "연령대 (선택사항) — 연령대별 기관 안내에만 참고됩니다",
        options=AGE_GROUPS,
        index=0,
    )

    st.caption(
        "이름·연락처 등 개인을 식별할 수 있는 정보는 묻지 않습니다. "
        "입력하신 내용은 자원 안내와 사전정리 시트 작성에만 쓰입니다."
    )

    can_start = region != REGION_PLACEHOLDER
    if st.button("이야기 시작하기", type="primary", disabled=not can_start,
                 use_container_width=True):
        if region == REGION_PLACEHOLDER:
            ss.region = None
        else:
            # REGION_OTHER 도 라벨 그대로 보존해 매칭 단계에서 참고
            ss.region = region
        ss.age_group = None if age_group == "선택 안 함" else age_group
        ss.phase = "interview"
        st.rerun()

    if not can_start:
        st.caption("지역을 선택하시면 시작 버튼이 활성화됩니다.")


# ---------------------------------------------------------------------------
# 단계 2: 인터뷰 진행
# ---------------------------------------------------------------------------
def render_interview():
    ss = st.session_state
    st.title("이야기를 들려주세요")

    # 지난 대화 표시
    for msg in ss.history:
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.write(msg["content"])

    # 첫 진입 시 도우미가 먼저 말 걸기
    if not ss.history:
        opener = (
            "안녕하세요. 편하게 이야기 나눠요. "
            "요즘 어떤 점이 가장 힘드신가요? 떠오르는 대로 말씀해 주셔도 괜찮아요."
        )
        ss.history.append({"role": "assistant", "content": opener})
        st.rerun()

    # 사용자 입력
    user_input = st.chat_input("여기에 편하게 적어 주세요…")
    if not user_input:
        return

    # API 키 체크
    if not _require_api_key():
        return

    if ss.turn_count >= MAX_TURNS:
        st.warning("대화 한도에 도달했습니다. 사이드바에서 다시 시작해 주세요.")
        return

    ss.history.append({"role": "user", "content": user_input})
    ss.turn_count += 1
    client = get_client()

    # ===== 안전 우선: 인터뷰 LLM 호출 '전에' 감지 =====
    safety = detect_safety(client, user_input, model=SAFETY_MODEL)
    if safety.is_blocked:
        ss.phase = "blocked"
        ss.block_kind = "crisis" if safety.crisis else "intoxication"
        st.rerun()
        return

    # ===== 안전 통과 → 인터뷰 한 턴 진행 =====
    try:
        with st.spinner("듣고 있어요…"):
            turn = run_interview_turn(client, ss.user_type, ss.history,
                                      model=CHAT_MODEL)
    except Exception as e:
        st.error(
            "이야기를 처리하는 중에 문제가 생겼어요. "
            "잠시 후 다시 시도해 주시거나, 사이드바에서 API Key 를 확인해 주세요.\n\n"
            f"_세부 사유: {type(e).__name__}_"
        )
        ss.turn_count -= 1
        ss.history.pop()
        return
    ss.history.append({"role": "assistant",
                       "content": turn["assistant_message"]})

    if turn["is_complete"]:
        ss.phase = "summarize"
    st.rerun()


# ---------------------------------------------------------------------------
# 단계 3: 안전 분기 — 종료가 아니라 '선택'을 제공
# ---------------------------------------------------------------------------
def render_blocked():
    ss = st.session_state
    is_crisis = ss.block_kind == "crisis"

    st.title("이야기를 들려주세요")

    for msg in ss.history:
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.write(msg["content"])

    with st.chat_message("assistant"):
        if is_crisis:
            st.warning("잠깐만요. 지금 많이 힘드신 것 같아요.")
            st.write(CRISIS_REDIRECT_MESSAGE)
        else:
            st.warning("지금은 잠시 쉬어가도 좋아요.")
            st.write(INTOXICATION_REDIRECT_MESSAGE)

        st.markdown(SAFETY_LINES_MD)
        st.divider()
        st.write("전화가 어렵다면, 여기서 저와 이야기를 더 이어가도 괜찮습니다.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("계속 이야기할게요", use_container_width=True,
                         type="primary", key="blocked_continue"):
                ss.history.append({
                    "role": "assistant",
                    "content": ("이야기를 이어가 주셔서 고마워요. "
                                "편하게 계속 말씀해 주세요."),
                })
                ss.block_kind = None
                ss.phase = "interview"
                st.rerun()
        with col2:
            if st.button("지금은 그만할게요", use_container_width=True,
                         key="blocked_stop"):
                ss.block_kind = None
                ss.phase = "ended"
                st.rerun()


# ---------------------------------------------------------------------------
# 단계 3b: 사용자가 직접 멈추기를 선택했을 때의 마무리 화면
# ---------------------------------------------------------------------------
def render_ended():
    st.title("언제든 다시 찾아와 주세요")
    st.write(
        "오늘 이야기 나눠 주셔서 고마워요. 마음이 힘들 땐 혼자 견디지 "
        "않으셔도 됩니다. 아래 번호는 24시간 함께합니다."
    )
    st.markdown(SAFETY_LINES_MD)
    st.divider()
    if st.button("처음으로 돌아가기"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()


# ---------------------------------------------------------------------------
# 단계 4: 시트 정리 + 자원 매칭
# ---------------------------------------------------------------------------
def render_summarize():
    ss = st.session_state
    if not _require_api_key():
        return
    client = get_client()

    if ss.sheet_data is None:
        try:
            with st.spinner("이야기해 주신 내용을 시트로 정리하고 있어요…"):
                ss.sheet_data = summarize_to_sheet(
                    client, ss.user_type, ss.history, model=CHAT_MODEL)
        except Exception as e:
            st.error(
                "시트로 정리하는 중에 문제가 생겼어요. 잠시 후 다시 시도해 주세요.\n\n"
                f"_세부 사유: {type(e).__name__}_"
            )
            if st.button("🔁 다시 시도"):
                st.rerun()
            return

        # intake 에서 받은 지역·연령대를 시트에 주입
        # → find_resources() 의 지역 매칭과 사전정리 시트에 함께 반영된다.
        if ss.get("region"):
            ss.sheet_data["거주지역"] = ss.region
        if ss.get("age_group"):
            ss.sheet_data["연령대"] = ss.age_group

    if ss.resource_match is None:
        try:
            with st.spinner("가까운 정신건강 기관을 찾고 있어요…"):
                resources = load_resources_from_files("data") or None
                ss.resource_match = find_resources(
                    client, ss.sheet_data,
                    resources=resources, model=CHAT_MODEL)
        except Exception as e:
            st.warning(
                f"기관 안내를 가져오지 못했어요({type(e).__name__}). "
                "사전정리 시트만 먼저 안내해 드릴게요."
            )
    ss.phase = "done"
    st.rerun()


# ---------------------------------------------------------------------------
# 단계 5: 완료 — 자원 안내 + 시트 다운로드
# ---------------------------------------------------------------------------
def render_done():
    ss = st.session_state
    st.title("준비가 끝났어요")

    if ss.resource_match is not None:
        st.markdown(ss.resource_match.to_user_text())
        st.divider()
    else:
        st.info(
            "기관 안내를 받아오지 못했어요. 가까운 정신건강복지센터·자살예방센터 "
            "정보는 " + CRISIS_CONTACT_LINE + " 로 문의해 주세요."
        )
        st.divider()

    st.subheader("📄 사전정리 시트")
    st.write(
        "아래에서 시트를 내려받아, 정신건강 기관에 방문하거나 전화하실 때 "
        "참고 자료로 활용하실 수 있습니다."
    )

    with st.expander("시트 내용 미리보기"):
        for key, value in ss.sheet_data.items():
            st.markdown(f"**{key}**: {value or '_(이야기 나누지 않음)_'}")

    docx_buffer = build_sheet_docx(
        ss.sheet_data, ss.user_type,
        author_initial=ss.get("author_initial", ""))
    st.download_button(
        "📄 사전정리 시트 내려받기 (.docx)",
        data=docx_buffer,
        file_name="정신건강_상담_사전정리_시트.docx",
        mime=("application/vnd.openxmlformats-officedocument"
              ".wordprocessingml.document"),
        type="primary",
    )
    st.info(
        "이 시트는 의료문서가 아닌 자기보고형 보조 문서입니다. "
        "위기 시에는 " + CRISIS_CONTACT_LINE + " 로 연락해 주세요."
    )


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def main():
    init_state()
    render_sidebar()

    phase = st.session_state.phase
    if phase == "select":
        render_select()
    elif phase == "intake":
        render_intake()
    elif phase == "interview":
        render_interview()
    elif phase == "blocked":
        render_blocked()
    elif phase == "ended":
        render_ended()
    elif phase == "summarize":
        render_summarize()
    elif phase == "done":
        render_done()

    st.divider()
    st.caption(
        "⚠️ 경기 마음온길은 의료 진단·치료 도구가 아닙니다.  ·  "
        + CRISIS_CONTACT_LINE
        + "  ·  개발: 우소현(정신간호학 박사)"
    )


if __name__ == "__main__":
    main()
