@echo off
cd /d C:\python\kis_digital_ra\contract-timeline
git add .
if "%~1"=="" (
    git commit -m "update"
) else (
    git commit -m "%~1"
)
git push