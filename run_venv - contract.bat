@echo off
call C:\python\python3_12_TA\.venv\Scripts\activate.bat
cd C:\python\kis_digital_ra\contract-timeline\pipeline
python build_data.py --backfill 2026-04-30 2026-04-30
pause