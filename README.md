<img width="1055" height="1491" alt="경기마음온길" src="https://github.com/user-attachments/assets/0242e28f-eb3a-4bcd-a5e4-77f5a50b45a0" />
# 경기 마음온길 (Gyeonggi Maeum-on-Gil)

> **정신건강 자원 안내·사전정리 AI 챗봇**
> 모호하게 흘려보낸 마음의 신호를, 가까운 도움과 한 장의 정리로 잇습니다.

[![Streamlit](https://img.shields.io/badge/Streamlit-Cloud-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/cloud)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

---

## 무엇을 하는 서비스인가

정신적 어려움을 겪는 도민(당사자)과 가족이 자신의 상태를 **편한 일상어로 이야기하면**, AI 가 두 가지 결과물을 동시에 제공합니다.

1. **자원 안내** — 호소 내용·거주 시·군을 파악하여 경기데이터드림이 개방한 정신건강 4종 데이터(정신건강복지센터·자살예방센터·중독관리통합지원센터·정신재활시설)에서 가장 가까운 공적 자원을 안내합니다.
2. **사전정리 시트** — 대화 내용을 표준 양식으로 정리한 Word(.docx) 파일을 자동 생성합니다. 이용자가 센터 방문·상담 전화 시 지참하여 접수상담을 보조하는 자기보고형 문서로 활용할 수 있습니다.

방문 **전(前)** 도움(자원 매칭)과 방문 **후(後)** 도움(사전정리 시트)을 한 흐름에서 제공하여, 도움요청의 심리적 문턱을 낮추는 것을 목표로 합니다.

---

## 활용 공공데이터 (경기데이터드림)

| 데이터셋 | 출처 |
|---|---|
| 정신 건강 복지센터 현황 | [경기데이터드림](https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=DR5A9PI77Q1831V975Q1889283&infSeq=1) |
| 자살 예방센터 현황 | [경기데이터드림](https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=4FGW2M1NM233Q9962116563284&infSeq=1) |
| 중독관리통합지원센터 현황 | [경기데이터드림](https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=VP6N5SJ9BHMEQ9RTWGAY15043133&infSeq=1) |
| 정신재활시설 현황 | [경기데이터드림](https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=D7M7S6RGBGIU3724UNH6628628&infSeq=1) |

---

## 안전·윤리 설계

본 서비스는 정신건강 도메인의 특수성을 반영한 안전 설계를 갖춥니다.

- **위기 우선 분기.** 대화 중 자살·자해 관련 표현이 감지되면 시트 생성 흐름이 즉시 중단되고 위기상담 안내(정신건강위기상담전화 1577-0199 등)로 전환됩니다. LLM 기반 분류기와 키워드 기반 백업의 이중 안전망을 둡니다.
- **음주 상태 분기.** 응대 매뉴얼의 위험성 평가 우선 확인 사항을 반영하여, 이용자가 음주 상태로 보이면 시트 생성을 진행하지 않고 술이 깬 뒤 다시 이용하도록 안내합니다.
- **위험도 비(非)등급화.** AI 는 위험을 점수화·등급화하지 않습니다. 시트의 안전 관련 항목에는 이용자가 보고한 내용만 사실 그대로 담고, 판단란은 전문가 작성용으로 비워 둡니다.
- **저작권 척도 미사용.** SBQ-R·CAGE 등 저작권이 있는 선별 척도의 문항은 시트에 포함하지 않습니다.

### 근거 자료

사전정리 시트의 9개 항목 체계와 안전 분기는 다음 국가 공공 자료를 근거로 설계되었습니다.

- 보건복지부, 「정신건강사업안내」 (등록·초기면접 항목 체계)
- 국립정신건강센터, 「정신건강위기상담전화(1577-0199) 응대 매뉴얼」 (문제 개념화·파악 주요사항·음주 상태 우선 확인)
- 국립정신건강센터, 「정신과적 위기상황에서의 위험평가 안내」

위 자료는 공공누리 4유형 조건의 자료이며, 본 프로젝트는 자료를 변형·재배포하지 않고 설계 근거 및 출처 표시 용도로만 인용합니다.

---

## 기술 스택

- **Frontend·App** — Streamlit (반응형 웹)
- **AI Engine** — OpenAI GPT API (`gpt-4o-mini`) — 인터뷰 진행·시트 정리·자원 분류
- **Data** — 경기데이터드림 4종 — 시·군 색인 매칭
- **문서 생성** — python-docx — 사전정리 시트 .docx 자동 생성

---

## 사용 방법

### 로컬 실행

```bash
git clone https://github.com/<your-username>/maeum-on-gil.git
cd maeum-on-gil
pip install -r requirements.txt
streamlit run app.py
```

브라우저가 열리면 사이드바에 OpenAI API Key 를 입력하고 시작하시면 됩니다.

### Streamlit Community Cloud 배포

이 저장소는 Streamlit Community Cloud 에서 추가 설정 없이 그대로 배포 가능합니다. `requirements.txt` 가 패키지를 자동 설치합니다.

#### 운영자 API Key 설정 (시연·심사용)

현재 공모전에 출품하는 제품이므로 운영자가 사전에 키를 등록하여 이용자가 키 입력 없이 바로 체험할 수 있도록 되어 있습니다. API 비용은 추후 협의 예정입니다.

### 자원 데이터 갱신

경기데이터드림에서 최신 4종 JSON 을 받아 `raw/` 폴더에 넣은 뒤 다음 명령을 실행하면 `data/` 폴더가 갱신됩니다.

```bash
python convert_gg_data.py
```

---

## 프로젝트 구조

```
maeum-on-gil/
├── app.py                    # Streamlit 메인
├── prompts.py                # LLM 시스템 프롬프트 (인터뷰·시트 정리·안전 감지)
├── safety.py                 # 위기·음주 감지 (이중 안전망)
├── conversation.py           # 인터뷰 진행·시트 정리 API 래퍼
├── sheet_builder.py          # 사전정리 시트 .docx 생성
├── resources.py              # 호소-범주 분류·시·군 매칭
├── resources_data.py         # 시연용 샘플 데이터
├── convert_gg_data.py        # 경기데이터드림 JSON 변환기
├── data/                     # 변환된 자원 데이터 (4종)
├── requirements.txt
└── README.md
```

---

## 면책 고지

본 서비스는 **의료 진단·치료를 제공하지 않으며, 전문적 상담·치료를 대체하지 않습니다.** 사전정리 시트는 공식 의료문서가 아닌 자기보고형 보조 문서입니다. 위기 상황에서는 정신건강위기상담전화 **1577-0199**, 자살예방상담전화 **109** 로 연락해 주세요.

---

## 라이선스

본 프로젝트는 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 라이선스로 공개됩니다. 비영리 목적의 활용·수정·재배포가 가능하며, 동일한 라이선스로 공유하셔야 합니다.

---

## 개발

**우소현** · 정신간호학 박사 / 정신건강간호사 1급
정신과 폐쇄병동 임상 8년 · 한국연구재단 박사후 국내연수과제 「동료지원가 핵심 역량 체계 수립과 평가도구 개발」 수행 중
