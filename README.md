# Contract Timeline

한국주식 공급계약 타임라인 대시보드.

KOSCOM check API의 '단일판매·공급계약' 공시를 수집하고, Gemini로 중요도/요약을 생성한 뒤 GitHub Pages로 정적 서빙합니다.

- **데이터 수집/빌드**: 로컬 PC, 매일 17시 (Windows 작업 스케줄러)
- **호스팅**: GitHub Pages (이 레포 루트)
- **소속**: 자산관리전략부 디지털리서치팀

## 구조

```
contract-timeline/                ← 레포 루트 (GitHub Pages 서빙)
├── index.html                    ← 메인: 공급계약 테이블 + 종목 검색
├── stock.html                    ← 개별 종목: 정보 + 타임라인
├── assets/{style.css, app.js}
├── data/                         ← 파이프라인이 생성, git 추적
│   ├── contracts.json
│   ├── stock_info.json
│   ├── meta.json
│   ├── briefs_by_stock/{code}.json
│   └── briefs_archive/{YYYY}.zip
├── pipeline/                     ← 데이터 빌드 코드
│   ├── config.py                 ← (git 제외) 키/경로 하드코딩
│   ├── config.py.example         ← 템플릿
│   ├── build_data.py             ← 메인 진입점
│   ├── koscom_client.py
│   ├── gemini_client.py
│   ├── brief_loader.py
│   ├── stock_info_loader.py
│   ├── archive.py
│   ├── run_daily.bat             ← Windows 스케줄러용
│   ├── requirements.txt
│   └── README.md                 ← 파이프라인 상세
├── .gitignore
└── README.md
```

## 첫 셋업 (1회만)

### 1) GitHub 레포 생성 + 클론

```powershell
# 조직 계정에 contract-timeline 레포 생성 후
cd C:\python\kis_digital_ra
git clone https://github.com/{org}/contract-timeline.git
cd contract-timeline
```

### 2) 이 패키지의 내용을 레포 루트에 복사

### 3) `pipeline/config.py` 만들기

```powershell
cd pipeline
copy config.py.example config.py
notepad config.py
```

`config.py`에 실제 값 입력:
- `KOSCOM_CUST_ID`, `KOSCOM_AUTH_KEY`
- `GEMINI_API_KEY`
- `REPO_ROOT`, `BRIEF_DIR`, `STOCK_CHECK_DIR`

⚠️ `config.py`는 `.gitignore`로 차단되어 git에 안 올라갑니다.

### 4) 의존성 설치

송이님이 쓰시는 가상환경(`C:\python\python3_12_TA\.venv`)이 이미 있다면:

```powershell
C:\python\python3_12_TA\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

새로 만들 거면:

```powershell
python -m venv C:\python\python3_12_TA\.venv
C:\python\python3_12_TA\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 5) 초기 백필

```powershell
cd C:\python\kis_digital_ra\contract-timeline\pipeline
C:\python\python3_12_TA\.venv\Scripts\python.exe build_data.py --backfill 2026-06-01 2026-06-17
```

### 6) 초기 커밋 + push

```powershell
cd C:\python\kis_digital_ra\contract-timeline
git add .
git commit -m "init: dashboard + initial backfill"
git push
```

⚠️ `git status`로 `pipeline/config.py`가 추적 목록에 안 들어가는지 반드시 확인.

### 7) GitHub Pages 활성화

- 레포 → Settings → Pages
- Source: `Deploy from a branch`
- Branch: `main` / `/ (root)`
- Save → 1~2분 후 `https://{org}.github.io/contract-timeline/` 접속

### 8) Windows 작업 스케줄러 등록

- 트리거: 매일 17:00
- 동작: 프로그램 시작
  - 프로그램: `C:\python\kis_digital_ra\contract-timeline\pipeline\run_daily.bat`
  - 시작 위치: `C:\python\kis_digital_ra\contract-timeline\pipeline`

## 일상 사용

자동: 매일 17:00 `run_daily.bat`이 자동 갱신 + 푸시.

수동 실행:

```powershell
cd C:\python\kis_digital_ra\contract-timeline\pipeline

# 오늘 데이터
C:\python\python3_12_TA\.venv\Scripts\python.exe build_data.py

# 특정 날짜
C:\python\python3_12_TA\.venv\Scripts\python.exe build_data.py --date 2026-06-16

# 기간 백필
C:\python\python3_12_TA\.venv\Scripts\python.exe build_data.py --backfill 2026-06-01 2026-06-17
```

로컬 미리보기:

```powershell
cd C:\python\kis_digital_ra\contract-timeline
C:\python\python3_12_TA\.venv\Scripts\python.exe -m http.server 8000
# 브라우저: http://localhost:8000
```

> ⚠️ `index.html` 더블클릭하면 `file://` 보안 차단으로 `Failed to fetch` 발생. 반드시 위처럼 HTTP 서버로 확인.

## 데이터 스키마

### `data/contracts.json`
공급계약 1건당 dict, 최신순.
```json
{
  "id":            "20260617-300N00068205",
  "date":          "2026-06-17",
  "time":          "18:07:28",
  "code":          "005960",
  "name":          "동부건설",
  "title":         "동부건설(주) (정정)단일판매ㆍ공급계약체결",
  "is_amendment":  true,
  "ncode":         "300N00068205",
  "mtvcd":         "300",
  "url":           "https://kind.krx.co.kr/disclosureSimpleSearch.do?...",
  "price_at_disclosure":      3215,
  "market_cap_at_disclosure": 1234567890,
  "counterparty":  "현대건설",
  "amount":        50000000000,
  "revenue_ratio": 12.34,
  "period_start":  "2026-07-01",
  "period_end":    "2028-06-30",
  "ai_importance": 4,
  "ai_summary":    "동부건설이 현대건설과 500억 규모 공급계약을 체결...",
  "ai_status":     "ok"
}
```

### `data/stock_info.json`
종목별 dict 배열. 매일 stock_check 최신본으로 덮어쓰기.

### `data/briefs_by_stock/{code}.json`
종목별 brief 시계열, 날짜 내림차순.

### `data/meta.json`
빌드 메타 (마지막 업데이트 시각, 카운트).

## 보안

- API 키는 `pipeline/config.py`에만. **절대 git 커밋 금지** (`.gitignore` 차단).
- 키 노출 시 즉시 회전.
