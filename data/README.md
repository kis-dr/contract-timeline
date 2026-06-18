# data/

이 폴더의 모든 JSON은 **`pipeline/build_data.py`가 자동 생성**합니다. 직접 편집 금지.

## 파일 구조

```
data/
├── contracts.json              공급계약 통합 (최신순)
├── stock_info.json             종목 정보 (검색 + 종목화면용)
├── meta.json                   빌드 메타 (마지막 업데이트 시각)
├── briefs_by_stock/
│   └── {code}.json             종목별 brief 시계열
└── briefs_archive/
    └── {YYYY}.zip              1년 이상 지난 brief 압축본
```

## 초기화 방법

```powershell
cd pipeline
python build_data.py --backfill 2026-06-01 <어제>
```

## 스키마 상세

레포 루트 `README.md`의 "데이터 스키마" 절 참조.
