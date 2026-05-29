"""
경기 마음온길 — 경기데이터드림 데이터 변환 스크립트

경기데이터드림에서 직접 다운로드한 4종 JSON 파일을, 우리 프로그램이
쓰는 형식으로 변환해 data/ 폴더에 저장한다.

[사용법]
  1) 경기데이터드림에서 4개 JSON 파일을 받는다.
  2) 받은 파일을 이 스크립트와 같은 폴더의 raw/ 안에 넣는다.
       raw/정신건강복지센터현황.json
       raw/자살예방센터현황.json
       raw/중독관리통합지원센터현황.json
       raw/정신재활시설현황.json
  3) 터미널에서 이 스크립트를 실행한다.
       python3 convert_gg_data.py
  4) data/ 폴더에 4개의 변환된 파일이 생긴다.
       data/resources_mhwc.json
       data/resources_spc.json
       data/resources_arc.json
       data/resources_pr.json
  5) 이 파일들이 있으면 app.py 는 샘플 대신 이 데이터를 자동으로 쓴다.

데이터 출처: 경기데이터드림 (https://data.gg.go.kr)
"""
import json
import os
import sys

# ── 입출력 경로 ────────────────────────────────────────────
RAW_DIR = "raw"      # 받은 원본 JSON 폴더
OUT_DIR = "data"     # 변환된 결과 폴더

# ── 4종 데이터셋의 컬럼 매핑 ───────────────────────────────
# 데이터셋마다 컬럼명이 조금씩 다르므로 일괄 매핑 테이블을 둔다.
DATASETS = {
    "mhwc": {  # 정신건강복지센터
        "input_file": "정신건강복지센터현황.json",
        "output_file": "resources_mhwc.json",
        "label": "정신건강복지센터",
        "name_keys": ["center_nm"],
        "phone_keys": ["telno"],
        "region_keys": ["sigun_nm"],
        "address_keys": ["refine_road_nm_addr", "refine_lotno_addr"],
        "note_keys": [],
    },
    "spc": {  # 자살예방센터
        "input_file": "자살예방센터현황.json",
        "output_file": "resources_spc.json",
        "label": "자살예방센터",
        "name_keys": ["sucde_prevnt_center_nm", "center_nm"],
        "phone_keys": ["telno"],
        "region_keys": ["sigun_nm"],
        "address_keys": ["refine_road_nm_addr", "refine_lotno_addr"],
        "note_keys": ["consign_inst_nm"],  # 위탁기관을 비고로
    },
    "arc": {  # 중독관리통합지원센터
        "input_file": "중독관리통합지원센터현황.json",
        "output_file": "resources_arc.json",
        "label": "중독관리통합지원센터",
        "name_keys": ["center_nm"],
        "phone_keys": ["telno"],
        "region_keys": ["sigun_nm"],
        "address_keys": ["refine_road_nm_addr", "refine_lotno_addr"],
        "note_keys": [],
    },
    "pr": {  # 정신재활시설
        "input_file": "정신재활시설현황.json",
        "output_file": "resources_pr.json",
        "label": "정신재활시설",
        "name_keys": ["inst_nm", "center_nm"],
        "phone_keys": ["rprs_telno", "telno"],
        "region_keys": ["sigun_nm"],
        "address_keys": ["refine_road_nm_addr", "refine_lotno_addr"],
        "note_keys": ["faclt_div_nm"],  # 시설 구분(주간재활시설 등)을 비고로
    },
}


def _pick(row: dict, keys: list) -> str:
    """주어진 키 후보들을 순서대로 시도해 값이 있는 첫 결과를 반환."""
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def convert_one(category_code: str, spec: dict) -> int:
    """한 데이터셋을 변환해 결과 파일로 저장. 변환된 레코드 수 반환."""
    in_path = os.path.join(RAW_DIR, spec["input_file"])
    out_path = os.path.join(OUT_DIR, spec["output_file"])

    if not os.path.exists(in_path):
        print(f"  ⚠ {spec['label']}: 원본 파일을 못 찾았습니다 — {in_path}")
        return 0

    with open(in_path, encoding="utf-8") as f:
        rows = json.load(f)

    converted = []
    for row in rows:
        name = _pick(row, spec["name_keys"])
        phone = _pick(row, spec["phone_keys"])
        region = _pick(row, spec["region_keys"])
        address = _pick(row, spec["address_keys"])
        note = _pick(row, spec["note_keys"])

        # 필수 항목이 없으면 건너뜀
        if not name or not region:
            continue

        converted.append({
            "name": name,
            "region": region,
            "address": address,
            "phone": phone,
            "note": note,
        })

    # 시·군 가나다 + 기관명 순으로 정렬 (안내 일관성)
    converted.sort(key=lambda x: (x["region"], x["name"]))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(converted, f, ensure_ascii=False, indent=2)

    print(f"  ✓ {spec['label']}: {len(rows)}건 → {len(converted)}건 변환")
    print(f"     저장: {out_path}")
    return len(converted)


def main():
    print("=" * 60)
    print("  경기 마음온길 — 경기데이터드림 데이터 변환")
    print("=" * 60)

    if not os.path.isdir(RAW_DIR):
        print(f"\n오류: '{RAW_DIR}/' 폴더가 없습니다.")
        print(f"  → 경기데이터드림에서 받은 4개 JSON 을 '{RAW_DIR}/' 안에 넣어 주세요.")
        sys.exit(1)

    total = 0
    for code, spec in DATASETS.items():
        total += convert_one(code, spec)

    print("-" * 60)
    print(f"총 {total}건의 기관 정보를 변환했습니다.")
    print(f"이제 app.py 를 실행하면 '{OUT_DIR}/' 의 데이터가 자동으로 쓰입니다.")


if __name__ == "__main__":
    main()
