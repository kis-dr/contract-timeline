@echo off
REM ============================================================
REM run_daily.bat  (pipeline/ 안에 위치)
REM
REM Windows 작업 스케줄러에서 매일 17:00 호출.
REM
REM 동작:
REM   1. pipeline/ 로 이동
REM   2. 지정된 Python 실행
REM   3. 레포 루트로 이동해 git add/commit/push
REM ============================================================
setlocal
chcp 65001 > nul

REM ----------------------------------------
REM 사용할 Python 절대경로
REM ----------------------------------------
set PYTHON_EXE=C:\python\python3_12_TA\.venv\Scripts\python.exe

REM ----------------------------------------
REM 디렉토리 기준점
REM   %~dp0     = 이 .bat 파일이 있는 폴더 (= pipeline\)
REM   REPO_ROOT = 한 단계 위 (= 레포 루트)
REM ----------------------------------------
set PIPELINE_DIR=%~dp0
set PIPELINE_DIR=%PIPELINE_DIR:~0,-1%
for %%I in ("%PIPELINE_DIR%\..") do set REPO_ROOT=%%~fI

cd /d "%PIPELINE_DIR%"

REM ----------------------------------------
REM 로그
REM ----------------------------------------
if not exist logs mkdir logs
set LOGFILE=logs\run_%date:~0,4%-%date:~5,2%-%date:~8,2%.log

echo. >> "%LOGFILE%"
echo ============================================================ >> "%LOGFILE%"
echo [%date% %time%] 데일리 빌드 시작 >> "%LOGFILE%"
echo PYTHON_EXE   = %PYTHON_EXE% >> "%LOGFILE%"
echo PIPELINE_DIR = %PIPELINE_DIR% >> "%LOGFILE%"
echo REPO_ROOT    = %REPO_ROOT% >> "%LOGFILE%"
echo ============================================================ >> "%LOGFILE%"

REM ----------------------------------------
REM Python 존재 확인
REM ----------------------------------------
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python 실행파일 없음: %PYTHON_EXE% >> "%LOGFILE%"
    goto END
)

REM ----------------------------------------
REM 데이터 빌드
REM ----------------------------------------
"%PYTHON_EXE%" build_data.py >> "%LOGFILE%" 2>&1
set BUILD_RC=%ERRORLEVEL%
if not "%BUILD_RC%"=="0" (
    echo [ERROR] build_data.py 실패 (exit %BUILD_RC%) >> "%LOGFILE%"
    goto END
)

REM ----------------------------------------
REM git push (레포 루트에서)
REM ----------------------------------------
cd /d "%REPO_ROOT%"
echo [INFO] git 작업 시작 (cwd=%CD%) >> "%LOGFILE%"

git add data/ >> "%LOGFILE%" 2>&1

git diff --cached --quiet
if "%ERRORLEVEL%"=="0" (
    echo [INFO] 변경사항 없음 - 커밋 스킵 >> "%LOGFILE%"
    goto END
)

git commit -m "data: daily update %date%" >> "%LOGFILE%" 2>&1
git push >> "%LOGFILE%" 2>&1
if not "%ERRORLEVEL%"=="0" (
    echo [ERROR] git push 실패 >> "%LOGFILE%"
    goto END
)

echo [%date% %time%] 완료 >> "%LOGFILE%"

:END
endlocal
