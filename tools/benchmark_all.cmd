@echo off
REM ============================================================
REM benchmark_all.cmd — 成员B: 批量实验集成 (B-2)
REM 对数据集/下所有 100 个公开实例运行 scheduler，
REM 用 validator 验证并输出 CSV 结果。
REM
REM 用法：
REM   tools\benchmark_all.cmd [scheduler.exe路径] [数据集路径] [输出CSV路径]
REM
REM 默认值：
REM   调度器: build\Release\scheduler.exe
REM   数据集: ..\数据集\
REM   输出:   experiments\results\v1_benchmark.csv
REM
REM 不依赖 C 的 Python 工具，纯 cmd 批处理
REM ============================================================

setlocal enabledelayedexpansion

set SCHED=%1
if "%SCHED%"=="" set SCHED=build\Release\scheduler.exe

set DATASET=%2
if "%DATASET%"=="" set DATASET=..\数据集\

set OUT_CSV=%3
if "%OUT_CSV%"=="" set OUT_CSV=experiments\results\v1_benchmark.csv

set VAL=build\Release\validator.exe

echo ============================================
echo Benchmark All 100 Instances
echo ============================================
echo Scheduler: %SCHED%
echo Dataset:   %DATASET%
echo Output:    %OUT_CSV%
echo.

if not exist %SCHED% (
    echo ERROR: scheduler not found at %SCHED%
    exit /b 1
)
if not exist %VAL% (
    echo ERROR: validator not found at %VAL%
    exit /b 1
)

:: Write CSV header
echo instance,valid,errors,E_wait,E_memory,E_finish,runtime_ms> %OUT_CSV%

set TOTAL=0
set PASS=0
set FAIL=0
set ALL_VALID=0

:: Loop through 100 instances
for /l %%i in (1,1,100) do (
    set /a TOTAL+=1
    
    :: Build filename with leading zeros
    set FNAME=case%%i
    if %%i lss 100 set FNAME=case0%%i
    if %%i lss 10 set FNAME=case00%%i
    
    set INFILE=%DATASET%\!FNAME!.in
    set TMP_SCHED=build\tmp_sched_%%i.txt
    set TMP_COMB=build\tmp_comb_%%i.txt
    set TMP_VAL=build\tmp_val_%%i.txt
    
    :: Run scheduler
    %SCHED% < "!INFILE!" > "!TMP_SCHED!" 2>nul
    
    :: Combine instance + schedule for validator
    copy /B "!INFILE!" + "!TMP_SCHED!" "!TMP_COMB!" >nul
    
    :: Run validator with quiet JSON output
    %VAL% --quiet < "!TMP_COMB!" > "!TMP_VAL!" 2>nul
    
    :: Parse JSON output to CSV
    set /p VAL_LINE=<"!TMP_VAL!"
    
    :: Extract fields using simple string replacement tricks
    set LINE=!VAL_LINE!
    set LINE=!LINE:{"valid":=!
    set LINE=!LINE:,",=";=!
    
    :: Parse valid field
    for /f "tokens=1 delims=," %%a in ("!LINE!") do set IS_VALID=%%a
    
    :: Count errors
    set ERR_COUNT=0
    echo !LINE! | findstr /C:"\"errors\":0" >nul
    if !errorlevel! equ 0 (
        set ERR_COUNT=0
    ) else (
        :: Extract error count
        for /f "tokens=2 delims=:" %%e in ("!LINE!") do (
            for /f "tokens=1 delims=," %%f in ("%%e") do set ERR_COUNT=%%f
        )
    )
    
    :: Extract metrics
    set E_WAIT=0
    set E_MEM=0
    set E_FIN=0
    if "!IS_VALID!"=="true" (
        :: Extract E_wait
        for /f "tokens=4 delims=,:" %%a in ("!LINE!") do set E_WAIT=%%a
        for /f "tokens=6 delims=,:" %%a in ("!LINE!") do set E_MEM=%%a
        for /f "tokens=8 delims=,}" %%a in ("!LINE!") do set E_FIN=%%a
    )
    
    :: Check if valid
    if "!IS_VALID!"=="true" (
        set /a PASS+=1
        set /a ALL_VALID+=1
        echo [PASS] !FNAME!  E_wait=!E_WAIT!  E_memory=!E_MEM!  E_finish=!E_FIN!
    ) else (
        set /a FAIL+=1
        echo [FAIL] !FNAME!  errors=!ERR_COUNT!
    )
    
    :: Write CSV row
    echo !FNAME!,!IS_VALID!,!ERR_COUNT!,!E_WAIT!,!E_MEM!,!E_FIN!,0>> %OUT_CSV%
    
    :: Cleanup temp files
    del "!TMP_SCHED!" "!TMP_COMB!" "!TMP_VAL!" >nul 2>&1
)

echo.
echo ============================================
echo Results saved to %OUT_CSV%
echo Total:  %TOTAL%
echo Valid:  %PASS%
echo Invalid: %FAIL%
echo ============================================
echo.

endlocal
