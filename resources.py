"""
경기 마음온길 — 자원 매칭 모듈

사전정리 시트(dict)를 입력으로 받아, 경기데이터드림 4종 데이터에서
이용자에게 적합한 기관을 추천한다.

매칭 흐름:
  ① 호소 분류 (classify_concern)
     - 시트의 main_concern + treatment_history + desired_help 텍스트를
       LLM 으로 분류해 자원 범주의 1순위·2순위를 정한다.
     - 4개 범주: mhwc(정신건강복지센터) / spc(자살예방센터) /
                 arc(중독관리통합지원센터) / pr(정신재활시설)
     - LLM 실패 시 키워드 규칙으로 폴백한다.

  ② 시·군 추출 (extract_region)
     - 시트의 basic_info 에서 거주 시·군을 정규화해 뽑는다.
       예: "수원시 영통구" / "수원시" / "영통구" → "수원시" 로 통일

  ③ 매칭 (find_resources)
     - 범주별로 같은 시·군의 기관을 우선 안내한다.
     - 같은 시·군에 없으면 광역(경기도) 자원을 폴백으로 제시한다.
     - 1순위 범주만 안내하지 않고, 2순위 범주도 함께 안내한다
       (한 사람이 여러 어려움을 겹쳐 갖는 경우가 흔하므로).

설계 원칙:
  - LLM 이 범주를 '단정'하지 않고 '후보 1·2순위'로 둔다.
  - 시·군이 식별되지 않으면 광역 자원을 안내하고, 1577-0199 안내를 덧붙인다.
  - 결과에는 항상 데이터 출처(경기데이터드림)와 정확성 면책을 함께 담아 반환한다.

근거: 사업계획서 2-2 RAG 기반 공공데이터 응답, 3-1 활용 경기도 공공데이터
"""
import json
import re
from dataclasses import dataclass, field

from resources_data import SAMPLE_RESOURCES, CATEGORY_INFO


# ---------------------------------------------------------------------------
# 시·군 정규화
# ---------------------------------------------------------------------------
# 경기도 31개 시·군 (자치구는 시 단위로 통합)
_GG_CITIES = [
    "수원시", "성남시", "고양시", "용인시", "부천시", "안산시", "안양시",
    "남양주시", "화성시", "평택시", "의정부시", "시흥시", "파주시",
    "김포시", "광명시", "광주시", "군포시", "오산시", "이천시", "양주시",
    "안성시", "구리시", "포천시", "의왕시", "하남시", "여주시", "동두천시",
    "과천시", "양평군", "가평군", "연천군",
]
# 자치구 → 상위 시 매핑 (자치구만 적힌 경우 대비)
_DISTRICT_TO_CITY = {
    # 수원시
    "장안구": "수원시", "권선구": "수원시", "팔달구": "수원시", "영통구": "수원시",
    # 성남시
    "수정구": "성남시", "중원구": "성남시", "분당구": "성남시",
    # 고양시
    "덕양구": "고양시", "일산동구": "고양시", "일산서구": "고양시",
    # 용인시
    "처인구": "용인시", "기흥구": "용인시", "수지구": "용인시",
    # 부천시 (구 폐지됐으나 잔존 표기 가능)
    "원미구": "부천시", "소사구": "부천시", "오정구": "부천시",
    # 안산시
    "단원구": "안산시", "상록구": "안산시",
    # 안양시
    "만안구": "안양시", "동안구": "안양시",
}


def extract_region(basic_info_text: str) -> str | None:
    """
    basic_info 문자열에서 경기도 시·군을 추출해 정규화된 형태로 반환한다.
    찾지 못하면 None.

    예시:
      "ㅎㅁ, 30대, 수원시 영통구"   → "수원시"
      "ㄱㅎ, 20대, 분당구 정자동"   → "성남시"
      "익명, 40대, 서울 강남"        → None  (경기도 아님)
    """
    if not basic_info_text:
        return None
    text = basic_info_text.replace(",", " ")
    # 1) 시 명칭 직접 매칭 (긴 것부터)
    for city in sorted(_GG_CITIES, key=len, reverse=True):
        if city in text:
            return city
    # 2) 자치구만 적혔으면 상위 시로 변환
    for district, city in _DISTRICT_TO_CITY.items():
        if district in text:
            return city
    return None


# ---------------------------------------------------------------------------
# 호소 → 범주 분류 (LLM 1차)
# ---------------------------------------------------------------------------
CLASSIFY_PROMPT = """당신은 '경기 마음온길' 서비스의 자원 분류기입니다.
이용자가 작성한 사전정리 시트의 호소 내용을 읽고, 어떤 정신건강 자원이
가장 적합한지 1·2순위로 분류하세요.

[범주]
  mhwc — 정신건강복지센터 : 우울·불안·수면 문제 등 정서적 어려움 전반
  spc  — 자살예방센터       : 자살 생각·자해 위기
  arc  — 중독관리통합지원센터 : 음주·도박·약물 등 중독
  pr   — 정신재활시설       : 치료 이후 회복·일상 복귀 단계

[원칙]
- 1순위는 호소의 핵심에 가장 직접 대응하는 범주입니다.
- 2순위는 함께 안내하면 도움이 될 가능성이 있는 범주입니다.
  필요 없으면 2순위는 null 로 둡니다.
- 자·타해 신호가 조금이라도 비치면 spc 를 반드시 후보에 포함하세요.
- 진단명을 부여하지 마세요. 분류만 하세요.

[출력 — JSON 한 줄만]
{"primary": "mhwc|spc|arc|pr", "secondary": "mhwc|spc|arc|pr|null", "reason": "한 줄 근거"}
"""


# 폴백용 키워드 규칙 — LLM 실패 시 사용
_KW_RULES = [
    # (검사 키워드 리스트, 1순위 범주)
    (["자살", "죽고 싶", "죽고싶", "자해", "유서", "끝내고 싶"], "spc"),
    (["술", "음주", "알코올", "도박", "약물", "중독"], "arc"),
    (["퇴원", "재활", "복귀", "취업", "주간", "사회복귀"], "pr"),
]

def _keyword_classify(text: str) -> dict:
    """LLM 폴백 — 보수적으로 mhwc 를 기본값으로."""
    t = (text or "").replace(" ", "")
    hits = []
    for kws, cat in _KW_RULES:
        if any(kw.replace(" ", "") in t for kw in kws):
            hits.append(cat)
    if not hits:
        return {"primary": "mhwc", "secondary": None,
                "reason": "키워드 폴백 — 일반 정서 상담 범주로 안내"}
    primary = hits[0]
    secondary = hits[1] if len(hits) > 1 else (
        "mhwc" if primary != "mhwc" else None)
    return {"primary": primary, "secondary": secondary,
            "reason": "키워드 폴백"}


def classify_concern(client, sheet_data: dict,
                     model: str = "gpt-4o-mini") -> dict:
    """
    시트의 호소 관련 항목을 합쳐 LLM 으로 1·2순위 범주를 분류한다.
    반환: {"primary": str, "secondary": str|None, "reason": str, "source": str}
    """
    blob = "\n".join([
        f"주요 호소: {sheet_data.get('main_concern', '')}",
        f"발생 시기·경과: {sheet_data.get('onset_course', '')}",
        f"치료·상담 경험: {sheet_data.get('treatment_history', '')}",
        f"희망 도움: {sheet_data.get('desired_help', '')}",
        f"안전 메모: {sheet_data.get('safety_note', '')}",
    ]).strip()

    try:
        resp = client.chat.completions.create(
            model=model, temperature=0, max_tokens=150,
            messages=[
                {"role": "system", "content": CLASSIFY_PROMPT},
                {"role": "user", "content": blob},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        primary = data.get("primary")
        secondary = data.get("secondary")
        if secondary in (None, "null", "", "None"):
            secondary = None
        if primary not in CATEGORY_INFO:
            raise ValueError(f"unknown primary: {primary}")
        if secondary is not None and secondary not in CATEGORY_INFO:
            secondary = None
        return {"primary": primary, "secondary": secondary,
                "reason": str(data.get("reason", "")), "source": "llm"}
    except Exception:
        result = _keyword_classify(blob)
        result["source"] = "keyword-fallback"
        return result


# ---------------------------------------------------------------------------
# 매칭 결과 자료구조
# ---------------------------------------------------------------------------
@dataclass
class ResourceMatch:
    region: str | None              # 인식된 시·군 (None 이면 미식별)
    primary_category: str           # 1순위 범주 코드
    secondary_category: str | None  # 2순위 범주 코드
    classification_reason: str
    classification_source: str
    primary_resources: list = field(default_factory=list)
    secondary_resources: list = field(default_factory=list)
    is_fallback: bool = False       # 시·군 미식별로 광역 폴백 사용했는지

    def to_user_text(self) -> str:
        """사용자에게 보여줄 안내 텍스트(마크다운)로 정리."""
        lines = []
        if self.region:
            lines.append(f"### 📍 안내 — **{self.region}** 거주 기준")
        else:
            lines.append("### 📍 안내 — 거주 시·군을 확인하지 못해 광역 자원으로 안내합니다")
        lines.append("")
        # 1순위
        pinfo = CATEGORY_INFO[self.primary_category]
        lines.append(f"#### 1) {pinfo['label']}")
        lines.append(f"_{pinfo['for']}_")
        lines.extend(_format_resource_lines(self.primary_resources))
        # 2순위
        if self.secondary_category and self.secondary_resources:
            sinfo = CATEGORY_INFO[self.secondary_category]
            lines.append("")
            lines.append(f"#### 2) {sinfo['label']} (함께 고려해 보세요)")
            lines.append(f"_{sinfo['for']}_")
            lines.extend(_format_resource_lines(self.secondary_resources))
        # 출처·면책
        lines.append("")
        lines.append("---")
        lines.append(
            "> 출처: 경기데이터드림 — 정신건강복지센터·자살예방센터·"
            "중독관리통합지원센터·정신재활시설 현황. "
            "기관 정보(전화·운영시간 등)는 변경될 수 있으므로 방문·전화 전 "
            "확인해 주세요."
        )
        return "\n".join(lines)


def _format_resource_lines(items: list) -> list:
    """기관 리스트를 마크다운 라인으로 변환."""
    if not items:
        return ["- _안내 가능한 기관을 찾지 못했습니다. 광역 1577-0199 로 문의해 주세요._"]
    out = []
    for it in items:
        out.append(f"- **{it['name']}**")
        out.append(f"   · 주소: {it['address']}")
        out.append(f"   · 전화: {it['phone']}")
        if it.get("note"):
            out.append(f"   · 비고: {it['note']}")
    return out


# ---------------------------------------------------------------------------
# 핵심 매칭 함수
# ---------------------------------------------------------------------------
def find_resources(client, sheet_data: dict,
                   resources: list = None,
                   model: str = "gpt-4o-mini",
                   max_per_category: int = 2) -> ResourceMatch:
    """
    시트 dict 를 받아 적합한 자원을 매칭한다.

    Parameters
    ----------
    client : OpenAI
    sheet_data : dict
        summarize_to_sheet() 의 결과
    resources : list
        자원 레코드 리스트. None 이면 SAMPLE_RESOURCES 사용.
        운영 환경에서는 load_resources_from_files() 로 갱신된 데이터를 전달.
    model : str
        분류용 모델
    max_per_category : int
        범주당 최대 안내 기관 수

    Returns
    -------
    ResourceMatch
    """
    if resources is None:
        resources = SAMPLE_RESOURCES

    # 1) 호소 분류
    cls = classify_concern(client, sheet_data, model=model)
    primary = cls["primary"]
    secondary = cls["secondary"]

    # 2) 시·군 추출
    region = extract_region(sheet_data.get("basic_info", ""))

    # 3) 매칭
    primary_list, used_fb_p = _match_category(resources, primary, region,
                                              max_per_category)
    secondary_list = []
    used_fb_s = False
    if secondary:
        secondary_list, used_fb_s = _match_category(
            resources, secondary, region, max_per_category)

    return ResourceMatch(
        region=region,
        primary_category=primary,
        secondary_category=secondary,
        classification_reason=cls["reason"],
        classification_source=cls["source"],
        primary_resources=primary_list,
        secondary_resources=secondary_list,
        is_fallback=(used_fb_p or used_fb_s or region is None),
    )


def _match_category(resources: list, category: str,
                    region: str | None, k: int) -> tuple[list, bool]:
    """
    같은 시·군의 해당 범주 기관을 최대 k 개 반환.
    같은 시·군에 없으면 광역(시·군이 광역 거점인 자원) 폴백.

    같은 시·군에 여러 기관이 있을 때는 일반 성인 대상 센터를 우선한다.
    (노인·아동청소년 등 특수 대상 센터는 후순위)
    """
    same_region = [r for r in resources
                   if r["category"] == category
                   and region is not None
                   and _region_matches(r["region"], region)]
    if same_region:
        same_region.sort(key=_priority_key)
        return same_region[:k], False

    # 폴백: 광역(이름에 '광역' 또는 '경기도' 포함된) 자원
    wide = [r for r in resources
            if r["category"] == category
            and ("광역" in r["name"] or "경기도" in r["name"])]
    if wide:
        return wide[:k], True

    # 그래도 없으면 같은 범주의 아무 자원
    any_cat = [r for r in resources if r["category"] == category]
    any_cat.sort(key=_priority_key)
    return any_cat[:k], True


def _priority_key(resource: dict) -> tuple:
    """
    같은 시·군 내 기관 정렬용 우선순위 키.
    낮은 값이 앞에 온다.

    일반 성인 대상이 1순위, 특수 대상 센터(노인·아동청소년·소아청소년)는
    뒤로 보낸다. 이용자 대다수가 성인이고, 호소 내용에서 특수 대상이
    명시되지 않은 한 일반 센터를 우선 노출하는 것이 적절하다.
    """
    name = resource.get("name", "")
    # 0순위: 일반(분화 없거나 '성인' 명시) / 1순위: 그 외(노인·아동청소년 등)
    if any(kw in name for kw in ("노인", "아동청소년", "소아청소년", "아동")):
        tier = 2
    elif "성인" in name:
        tier = 0  # 명시적 성인 센터 최우선
    else:
        tier = 1  # 분화 없는 일반 센터
    return (tier, name)


def _region_matches(resource_region: str, query_region: str) -> bool:
    """
    자원 레코드의 region 과 사용자 region 이 같은 시·군인지 비교.
    "수원시 영통구" 같은 형태도 "수원시" 로 정규화해 비교.
    """
    def root_city(s: str) -> str:
        for city in _GG_CITIES:
            if city in s:
                return city
        return s.strip()
    return root_city(resource_region) == root_city(query_region)


# ---------------------------------------------------------------------------
# 운영 환경용: 갱신된 데이터 파일 로드
# ---------------------------------------------------------------------------
def load_resources_from_files(data_dir: str = "data") -> list:
    """
    배포 환경에서 갱신된 4종 JSON 파일을 읽어 통합 레코드 리스트로 반환.
    파일이 없으면 빈 리스트.

    기대 파일:
      data/resources_mhwc.json
      data/resources_spc.json
      data/resources_arc.json
      data/resources_pr.json

    각 파일은 [{"name":..., "region":..., "address":..., "phone":..., "note":...}, ...]
    형태의 리스트여야 하며, 함수가 category 키를 자동으로 부여한다.
    """
    import os
    out = []
    for cat in ["mhwc", "spc", "arc", "pr"]:
        path = os.path.join(data_dir, f"resources_{cat}.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)
            for r in rows:
                r["category"] = cat
                out.append(r)
        except Exception:
            # 손상 파일은 건너뜀
            continue
    return out
