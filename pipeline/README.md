# pipeline/

데이터 빌드 파이프라인. 매일 17시 로컬 PC에서 실행되어 `../data/` 아래 JSON을 생성하고 git push.

## Python 환경

```
C:\python\python3_12_TA\.venv\Scripts\python.exe
```

이 가상환경에 `requirements.txt`를 설치:

```powershell
C:\python\python3_12_TA\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 모듈

| 파일 | 역할 |
|---|---|
| `config.py` | **키/경로 평문 하드코딩 (git 제외)** |
| `config.py.example` | 템플릿 (git 추적) |
| `koscom_client.py` | KOSCOM check API 래퍼 (gongsi_basic/gongsi_body) |
| `gemini_client.py` | Gemini cascade (3.1-flash-lite → 2.5-flash-lite) + Pydantic |
| `brief_loader.py` | UNC kr_brief CSV → `../data/briefs_by_stock/{code}.json` 머지 |
| `stock_info_loader.py` | UNC stock_check CSV → `../data/stock_info.json` |
| `archive.py` | 1년 지난 brief 연도별 zip |
| `build_data.py` | **메인 진입점** |
| `run_daily.bat` | Windows 작업 스케줄러용 |

## config.py 항목

| 변수 | 설명 | 예시 |
|---|---|---|
| `KOSCOM_CUST_ID`  | KOSCOM cust_id | `SC04703003` |
| `KOSCOM_AUTH_KEY` | KOSCOM auth_key | |
| `GEMINI_API_KEY`  | Gemini API 키 | |
| `REPO_ROOT`       | 레포 루트 절대경로 (Path) | `C:\python\kis_digital_ra\contract-timeline` |
| `BRIEF_DIR`       | UNC kr_brief 폴더 | `\\197.197.26.121\계량분석\...\DATA` |
| `STOCK_CHECK_DIR` | UNC stock_check 폴더 | `\\197.197.26.121\계량분석\...\check` |
| `DATA_START_DATE` | 누적 시작일 | `2026-06-01` |
| `BRIEF_ARCHIVE_DAYS` | brief 아카이브 임계 | `365` |
| `DRY_RUN`         | True면 파일/git push 안 함 | `False` |

## 셋업

```powershell
cd C:\python\kis_digital_ra\contract-timeline\pipeline

# 1. config.py 생성
copy config.py.example config.py
notepad config.py     # 실제 값 입력

# 2. 의존성 설치
C:\python\python3_12_TA\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 사용법

```powershell
set PY=C:\python\python3_12_TA\.venv\Scripts\python.exe

%PY% build_data.py                              # 오늘
%PY% build_data.py --date 2026-06-16            # 특정 날짜
%PY% build_data.py --backfill 2026-06-01 2026-06-17  # 기간
%PY% build_data.py --skip-brief --skip-stock-info     # 일부 스킵
```

## 실행 흐름 (build_data.py)

1. `../data/contracts.json` 로드 (없으면 빈 리스트)
2. KOSCOM `gongsi_basic` → `판매ㆍ공급` 필터
3. 신규 공시(`id` 중복 아님)만:
   - `gongsi_body` 본문 fetch
   - 당일 stock_check에서 현재가/시가총액 머지
   - Gemini로 중요도/요약/계약상대/금액/매출비중 추출
4. `../data/contracts.json` 최신순 저장
5. 최신 stock_check → `../data/stock_info.json` 덮어쓰기
6. UNC brief CSV들 → `../data/briefs_by_stock/{code}.json` 머지
7. `../data/meta.json` 갱신
8. 1년 지난 brief → `../data/briefs_archive/{YYYY}.zip` 이동

## Gemini cascade

- 1순위: `gemini-3.1-flash-lite`
- 폴백: `gemini-2.5-flash-lite` (429/RESOURCE_EXHAUSTED 시)
- 모델당 최대 3회 재시도
- 둘 다 실패: `ai_status: "failed"` 마킹, 다음날 재실행으로 재처리 가능

## Windows 작업 스케줄러

- 트리거: 매일 17:00
- 프로그램: `C:\python\kis_digital_ra\contract-timeline\pipeline\run_daily.bat`
- 시작 위치: `C:\python\kis_digital_ra\contract-timeline\pipeline`

`run_daily.bat` 내부에 Python 절대경로(`C:\python\python3_12_TA\.venv\Scripts\python.exe`) 박혀있음.

## 트러블슈팅

### `Failed to fetch` (브라우저)
HTML 더블클릭 → `file://` 보안 차단. `python -m http.server` 사용.

### KOSCOM 401/403
`config.py`의 `KOSCOM_CUST_ID` / `KOSCOM_AUTH_KEY` 확인.

### `ModuleNotFoundError: No module named 'google'` 등
의존성이 설치 안 됨:
```powershell
C:\python\python3_12_TA\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### git push 실패
- 인증: GitHub PAT 또는 SSH 키 사전 설정
- 충돌: `git pull --rebase` 후 재시도

### Python 경로가 다른 PC로 옮길 때
`run_daily.bat`의 `PYTHON_EXE` 변수만 수정.

## 보안

- `config.py`는 `.gitignore`에서 차단됨
- 푸시 전 `git status`로 `pipeline/config.py`가 staged에 없는지 반드시 확인
- 키 노출 의심 시 즉시 회전
