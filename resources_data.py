"""
경기 마음온길 — 자원 데이터 (샘플)

이 파일은 시연·개발용 샘플 데이터를 담는다.
운영 배포 시에는 경기데이터드림 4종 데이터셋(아래 URL)을 정기 수집하여
data/resources_*.json 으로 갱신하고, resources.load_resources() 가
그 파일들을 우선적으로 읽도록 한다.

데이터 출처 (경기데이터드림 / 경기도):
  - 정신건강복지센터 현황
    https://data.gg.go.kr/portal/data/service/selectServicePage.do
        ?infId=DR5A9PI77Q1831V975Q1889283&infSeq=1
  - 자살예방센터 현황
    https://data.gg.go.kr/portal/data/service/selectServicePage.do
        ?infId=4FGW2M1NM233Q9962116563284&infSeq=1
  - 중독관리통합지원센터 현황
    https://data.gg.go.kr/portal/data/service/selectServicePage.do
        ?infId=VP6N5SJ9BHMEQ9RTWGAY15043133&infSeq=1
  - 정신재활시설 현황
    https://data.gg.go.kr/portal/data/service/selectServicePage.do
        ?infId=D7M7S6RGBGIU3724UNH6628628&infSeq=1

※ 본 샘플의 기관 정보는 실제 운영 정보와 다를 수 있다.
   배포 전 위 데이터셋에서 최신본을 받아 갱신하라.

자원 범주 코드:
  mhwc  - 정신건강복지센터 (Mental Health Welfare Center)
  spc   - 자살예방센터 (Suicide Prevention Center)
  arc   - 중독관리통합지원센터 (Addiction Recovery Center)
  pr    - 정신재활시설 (Psychiatric Rehabilitation)
"""

# 4종 데이터 통합 레코드. 각 레코드는 다음 키를 가진다:
#   category: 자원 범주 코드 (mhwc/spc/arc/pr)
#   name:     기관명
#   region:   시군명 (정규화된 형태, 예: '수원시', '성남시 분당구')
#   address:  도로명 주소
#   phone:    대표 전화번호
#   note:     선택. 운영시간·특이사항 등
SAMPLE_RESOURCES = [
    # ── 정신건강복지센터 (mhwc) ────────────────────────────────
    {"category": "mhwc", "name": "경기도정신건강복지센터(광역)",
     "region": "수원시 영통구",
     "address": "경기도 수원시 영통구 광교로 17",
     "phone": "031-212-0435",
     "note": "광역 — 시·군 센터를 찾지 못할 때 안내"},
    {"category": "mhwc", "name": "수원시정신건강복지센터",
     "region": "수원시",
     "address": "경기도 수원시 장안구 수성로 245번길 1",
     "phone": "031-247-0888",
     "note": ""},
    {"category": "mhwc", "name": "성남시정신건강복지센터",
     "region": "성남시",
     "address": "경기도 성남시 수정구 수정남로 87",
     "phone": "031-754-3220",
     "note": ""},
    {"category": "mhwc", "name": "고양시정신건강복지센터",
     "region": "고양시",
     "address": "경기도 고양시 덕양구 화중로 104번길 50",
     "phone": "031-968-2333",
     "note": ""},
    {"category": "mhwc", "name": "용인시정신건강복지센터",
     "region": "용인시",
     "address": "경기도 용인시 처인구 중부대로 1199",
     "phone": "031-286-0949",
     "note": ""},
    {"category": "mhwc", "name": "부천시정신건강복지센터",
     "region": "부천시",
     "address": "경기도 부천시 원미구 길주로 210",
     "phone": "032-654-4024",
     "note": ""},
    {"category": "mhwc", "name": "안산시정신건강복지센터",
     "region": "안산시",
     "address": "경기도 안산시 단원구 화랑로 387",
     "phone": "031-411-7573",
     "note": ""},

    # ── 자살예방센터 (spc) ──────────────────────────────────────
    {"category": "spc", "name": "경기도자살예방센터(광역)",
     "region": "수원시 영통구",
     "address": "경기도 수원시 영통구 광교로 17",
     "phone": "031-212-0437",
     "note": "광역 — 24시간 상담 1577-0199"},
    {"category": "spc", "name": "수원시자살예방센터",
     "region": "수원시",
     "address": "경기도 수원시 장안구 수성로 245번길 1",
     "phone": "031-247-3279",
     "note": ""},
    {"category": "spc", "name": "성남시자살예방센터",
     "region": "성남시",
     "address": "경기도 성남시 수정구 수정남로 87",
     "phone": "031-754-3220",
     "note": ""},
    {"category": "spc", "name": "고양시자살예방센터",
     "region": "고양시",
     "address": "경기도 고양시 덕양구 화중로 104번길 50",
     "phone": "031-927-3299",
     "note": ""},

    # ── 중독관리통합지원센터 (arc) ──────────────────────────────
    {"category": "arc", "name": "수원시중독관리통합지원센터",
     "region": "수원시",
     "address": "경기도 수원시 팔달구 정조로 825",
     "phone": "031-256-9478",
     "note": "알코올·도박·약물 등 중독 문제"},
    {"category": "arc", "name": "성남시중독관리통합지원센터",
     "region": "성남시",
     "address": "경기도 성남시 중원구 산성대로 282",
     "phone": "031-751-2768",
     "note": ""},
    {"category": "arc", "name": "안산시중독관리통합지원센터",
     "region": "안산시",
     "address": "경기도 안산시 단원구 화랑로 387",
     "phone": "031-411-8445",
     "note": ""},
    {"category": "arc", "name": "부천시중독관리통합지원센터",
     "region": "부천시",
     "address": "경기도 부천시 원미구 부일로 365",
     "phone": "032-655-8275",
     "note": ""},

    # ── 정신재활시설 (pr) — 회복 단계·일상 복귀 지원 ──────────
    {"category": "pr", "name": "수원시정신재활시설 \u2018희망터\u2019",
     "region": "수원시",
     "address": "경기도 수원시 권선구 권선로 733",
     "phone": "031-228-7600",
     "note": "주간 재활 프로그램"},
    {"category": "pr", "name": "성남시정신재활시설 \u2018새빛\u2019",
     "region": "성남시",
     "address": "경기도 성남시 분당구 야탑로 165",
     "phone": "031-707-3000",
     "note": "주거·취업 지원"},
    {"category": "pr", "name": "고양시정신재활시설 \u2018봄날\u2019",
     "region": "고양시",
     "address": "경기도 고양시 일산동구 중앙로 1234",
     "phone": "031-908-3300",
     "note": ""},
]


# 자원 범주별 한글 표기와 설명 (사용자에게 보여줄 텍스트)
CATEGORY_INFO = {
    "mhwc": {
        "label": "정신건강복지센터",
        "for": "우울·불안·수면 문제 등 정서적 어려움 전반의 상담·사례관리",
    },
    "spc": {
        "label": "자살예방센터",
        "for": "자살 생각·자해 위기 상담 및 24시간 전화 지원",
    },
    "arc": {
        "label": "중독관리통합지원센터",
        "for": "음주·도박·약물 등 중독 문제 상담·회복 지원",
    },
    "pr": {
        "label": "정신재활시설",
        "for": "치료 이후 회복·일상 복귀를 위한 재활·주거·취업 지원",
    },
}
