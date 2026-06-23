@echo off
setlocal enabledelayedexpansion

set DATASET=C:\Users\lenovo\Desktop\课程设计相关材料\数据集
set SCHED=build\Release\scheduler.exe
set VAL=build\Release\validator.exe
set PASS_COUNT=0
set FAIL_COUNT=0
set TOTAL=0

for /l %%i in (1,1,10) do (
    set /a TOTAL+=1
    set FILE_NAME=case%%i
    if %%i lss 100 set FILE_NAME=case0%%i
    if %%i lss 10 set FILE_NAME=case00%%i
    
    %SCHED% < "%DATASET%\!FILE_NAME!.in" > build\temp_sched.txt
    
    copy /B "%DATASET%\!FILE_NAME!.in" + build\temp_sched.txt build\temp_comb.txt >nul
    
    %VAL% --quiet < build\temp_comb.txt > build\temp_val.txt
    set /p VAL_LINE=<build\temp_val.txt
    
    echo !VAL_LINE! | findstr "true" >nul
    if !errorlevel! equ 0 (
        set /a PASS_COUNT+=1
        echo [PASS] !FILE_NAME! - !VAL_LINE!
    ) else (
        set /a FAIL_COUNT+=1
        echo [FAIL] !FILE_NAME! - !VAL_LINE!
    )
)

echo.
echo ===== Summary: %PASS_COUNT% / %TOTAL% passed, %FAIL_COUNT% failed =====
endlocal
