@echo off
REM Sovereign Terminal — Backup Script (Windows)
REM Backs up databases and configuration state.
REM Usage: backup.bat
REM Runs from project root.

setlocal enabledelayedexpansion
set DATE_STR=%DATE:~10,4%%DATE:~4,2%%DATE:~7,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%
set DATE_STR=%DATE_STR: =0%
set BACKUP_DIR=backups\%DATE_STR%

echo Starting backup to %BACKUP_DIR%...
if not exist backups mkdir backups
if not exist %BACKUP_DIR% mkdir %BACKUP_DIR%

REM ── Databases ─────────────────────────────────────────────────────────────
echo Backing up databases...

copy /Y "stocks.db" "%BACKUP_DIR%\stocks.db"
if errorlevel 1 (
    echo WARNING: stocks.db not found or copy failed
)

copy /Y "portfolio_history.db" "%BACKUP_DIR%\portfolio_history.db"
if errorlevel 1 (
    echo WARNING: portfolio_history.db not found or copy failed
)

copy /Y "sovereign_v12.db" "%BACKUP_DIR%\sovereign_v12.db" 2>nul
copy /Y "data_cache.db"    "%BACKUP_DIR%\data_cache.db"    2>nul
copy /Y "test_stocks.db"   "%BACKUP_DIR%\test_stocks.db"   2>nul

REM ── Configuration & State ─────────────────────────────────────────────────
echo Backing up configuration...

if exist .env (
    copy /Y ".env" "%BACKUP_DIR%\.env"
)
if exist data\universe_flags.json (
    copy /Y "data\universe_flags.json" "%BACKUP_DIR%\universe_flags.json"
)

REM ── ML Models ─────────────────────────────────────────────────────────────
if exist runtime\models (
    xcopy /E /I /Y "runtime\models" "%BACKUP_DIR%\models"
    echo Models backed up.
)

REM ── Verify backup integrity ───────────────────────────────────────────────
if exist "%BACKUP_DIR%\stocks.db" (
    if exist "%BACKUP_DIR%\portfolio_history.db" (
        echo Backup complete: %BACKUP_DIR%
        exit /b 0
    )
)

echo ERROR: Backup verification failed — core DB files missing.
exit /b 1
