"""
경기 마음온길 (Gyeonggi Maeum-on-Gil) — Streamlit 통합 (app.py)

[변경 요약]
  - 위기/음주 감지 시 '하드 종료'하던 render_blocked() 를
    안전 자원 안내 + "계속 이야기할지 / 지금은 그만할지" 선택형으로 교체.
  - "계속 이야기할게요" → 인터뷰(interview) 단계로 복귀, 대화 지속.
  - "지금은 그만할게요" → ended 단계로 부드럽게 마무리(번호 재안내).
  - 안전 자원 번호를 2026년 기준으로 명시(109 / 1577-0199 / 119).
    ※ prompts.py 의 CRISIS_CONTACT_LINE 도 109 기준인지 확인 권장.

전제: safety.py 는 A안(키워드 단독) 버전이 배포되어 있어야 한다.
      그래야 "우울해요/도와줄 사람 없어요" 같은 정서 호소가 통과한다.

핵심 흐름:
  ① 이용자 유형 선택 (당사자 / 가족)
  ② 사용자 메시지 입력
  ③ [안전 우선] detect_safety() — 위기·음주 감지가 인터뷰보다 먼저
       └ 차단 시: blocked 단계로 전환(인터뷰 호출 안 함)
  ④ run_interview_turn() — 다음 질문 or 완료 신호
  ⑤ 완료 시: summarize_to_sheet() → build_sheet_docx() → 다운로드 버튼

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

# 안전 자원 번호 (2026년 기준) — blocked/ended 화면에서 공통 사용
SAFETY_LINES_MD = (
    "- **자살예방 상담전화 109** — 24시간, 비밀 보장\n"
    "- **정신건강 상담전화 1577-0199**\n"
    "- **긴급한 위급 상황 119**"
)


# ---------------------------------------------------------------------------
# 세션 상태 초기화
# ---------------------------------------------------------------------------
def init_state():
    ss = st.session_state
    ss.setdefault("user_type", None)        # 'self' | 'family'
    ss.setdefault("history", [])            # 대화 기록 (system 제외)
    ss.setdefault("phase", "select")        # select | interview | blocked | ended | summarize | done
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
            st.session_state.phase = "interview"
            st.rerun()
    with col2:
        if st.button("👪 가족의 어려움을 도와주고 싶어요\n(가족·보호자)",
                     use_container_width=True):
            st.session_state.user_type = "family"
            st.session_state.phase = "interview"
            st.rerun()


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
    # safety.py 가 A안(키워드 단독)일 때, _CRISIS_KEYWORDS /
    # _INTOXICATION_KEYWORDS 에 명시된 표현에서만 차단된다.
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
        # 마지막 사용자 메시지는 그대로 두되 카운터 되돌림 — 재시도 가능
        ss.turn_count -= 1
        ss.history.pop()  # 방금 추가된 사용자 메시지 제거
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
    """
    위기/음주 신호가 잡혔을 때의 화면.

    설계 의도: 힘든 이야기를 꺼내던 중 갑자기 잘리고 종료 문구만 뜨는
    경험은 오히려 위해가 될 수 있다. 따라서
      (1) 안전 자원(상담전화)을 안내하고,
      (2) "그래도 대화를 이어갈지 / 지금은 멈출지"를 사용자가 직접
          선택하도록 한다(자율성 존중).
    """
    ss = st.session_state
    is_crisis = ss.block_kind == "crisis"

    st.title("이야기를 들려주세요")

    # 갑자기 잘린 느낌을 줄이기 위해 지금까지의 대화 맥락을 그대로 보여준다
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
                # 방금 사용자가 한 말(차단되어 응답받지 못한 메시지)에
                # 부드럽게 응답하며 인터뷰로 복귀
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

    if ss.resource_match is None:
        try:
            with st.spinner("가까운 정신건강 기관을 찾고 있어요…"):
                # 배포 시 갱신된 데이터가 있으면 그것을 쓰고, 없으면 샘플 사용
                resources = load_resources_from_files("data") or None
                ss.resource_match = find_resources(
                    client, ss.sheet_data,
                    resources=resources, model=CHAT_MODEL)
        except Exception as e:
            # 자원 매칭 실패해도 시트는 살아 있으므로 done 으로 진행
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

    # 5-1) 자원 안내 (방문 '전' 도움)
    if ss.resource_match is not None:
        st.markdown(ss.resource_match.to_user_text())
        st.divider()
    else:
        st.info(
            "기관 안내를 받아오지 못했어요. 가까운 정신건강복지센터·자살예방센터 "
            "정보는 " + CRISIS_CONTACT_LINE + " 로 문의해 주세요."
        )
        st.divider()

    # 5-2) 사전정리 시트 다운로드 (방문 '후' 도움)
    st.subheader("📄 사전정리 시트")
    st.write(
        "아래에서 시트를 내려받아, 정신건강 기관에 방문하거나 전화하실 때 "
        "참고 자료로 활용하실 수 있습니다."
    )

    # 미리보기
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

    # 푸터 — 위기 자원 상시 노출
    st.divider()
    st.caption(
        "⚠️ 경기 마음온길은 의료 진단·치료 도구가 아닙니다.  ·  "
        + CRISIS_CONTACT_LINE
        + "  ·  개발: 우소현(정신간호학 박사)"
    )


if __name__ == "__main__":
    main()
