@echo off
setlocal EnableDelayedExpansion

echo Xool Asset Cleaner
echo ==================
echo.
echo This script will delete all clothing assets from your assets folders.
echo.
echo CAUTION: This will permanently delete all clothing files!
echo.
set /p confirm=Type 'YES' to continue or press Enter to cancel: 
if /i not "%confirm%"=="YES" (
    echo.
    echo Operation cancelled.
    goto :end
)

echo.
echo Cleaning up assets folders...
echo.

rem Check and clean shirts directory
if exist "src\assets\shirts" (
    set count=0
    for %%F in ("src\assets\shirts\*.*") do set /a count+=1
    echo Deleting %count% files from shirts folder...
    del /q "src\assets\shirts\*.*" 2>nul
    echo Shirts folder cleared.
) else (
    echo Creating shirts directory...
    mkdir "src\assets\shirts" 2>nul
)

rem Check and clean pants directory
if exist "src\assets\pants" (
    set count=0
    for %%F in ("src\assets\pants\*.*") do set /a count+=1
    echo Deleting %count% files from pants folder...
    del /q "src\assets\pants\*.*" 2>nul
    echo Pants folder cleared.
) else (
    echo Creating pants directory...
    mkdir "src\assets\pants" 2>nul
)

rem Check and clean temp directories
if not exist "src\assets\temp" mkdir "src\assets\temp" 2>nul
if not exist "src\assets\temp\shirts" mkdir "src\assets\temp\shirts" 2>nul
if not exist "src\assets\temp\pants" mkdir "src\assets\temp\pants" 2>nul

set count=0
for %%F in ("src\assets\temp\shirts\*.*") do set /a count+=1
echo Deleting %count% files from temp shirts folder...
del /q "src\assets\temp\shirts\*.*" 2>nul

set count=0
for %%F in ("src\assets\temp\pants\*.*") do set /a count+=1
echo Deleting %count% files from temp pants folder...
del /q "src\assets\temp\pants\*.*" 2>nul
echo Temporary folders cleared.

rem Ensure template directory exists
if not exist "src\assets\template" mkdir "src\assets\template" 2>nul

echo.
echo Asset cleanup complete!
echo.
echo NOTE: Template files were preserved.
echo.

:end
pause 