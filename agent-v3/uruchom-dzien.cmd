@echo off
REM Lokalna kontrola prototypu V3. Zawsze fixture, bez sieci i bez publikacji.

cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set AGENT_V3_MODE=fixture
set AGENT_V3_KILL_SWITCH=1
set AGENT_V3_DRY_RUN=1

".venv\Scripts\python.exe" -u "agent-v3\tests\test_prototype_safety.py"
