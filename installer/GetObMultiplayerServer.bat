@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO_URL=https://github.com/theturrell/ObMultiplayerServer.git"
set "TARGET_DIR=%USERPROFILE%\Documents\ObMultiplayerServer"
set "GIT_EXE="

call :find_git
if defined GIT_EXE goto clone_repo

echo Git was not found. Attempting to install Git with winget...
where winget >nul 2>nul
if errorlevel 1 (
    echo.
    echo winget is not available on this PC.
    echo Please install Git manually from https://git-scm.com/download/win and run this file again.
    pause
    exit /b 1
)

winget install --id Git.Git --exact --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo.
    echo Git installation failed.
    echo Please install Git manually from https://git-scm.com/download/win and run this file again.
    pause
    exit /b 1
)

call :find_git
if not defined GIT_EXE (
    echo.
    echo Git appears to be installed, but it could not be found in PATH yet.
    echo Try closing this window and running this file again.
    pause
    exit /b 1
)

:clone_repo
echo Using Git at: %GIT_EXE%
echo Target folder: %TARGET_DIR%
echo.

if exist "%TARGET_DIR%\.git" goto update_repo
if exist "%TARGET_DIR%" goto target_exists

echo Cloning the repo into Documents...
"%GIT_EXE%" clone "%REPO_URL%" "%TARGET_DIR%"
if errorlevel 1 goto clone_failed
goto done

:update_repo
echo Existing repo found. Pulling latest changes...
"%GIT_EXE%" -C "%TARGET_DIR%" pull --ff-only
if errorlevel 1 goto update_failed
goto done

:target_exists
echo The target folder already exists but is not a Git repo:
echo %TARGET_DIR%
echo.
echo Rename or remove that folder, then run this file again.
pause
exit /b 1

:clone_failed
echo.
echo Clone failed.
echo If GitHub asked for sign-in, make sure you can access the repo in a browser first.
pause
exit /b 1

:update_failed
echo.
echo Update failed.
echo If the repo has local changes, resolve them or remove the folder and run this file again.
pause
exit /b 1

:done
echo.
echo Finished.
echo Repo is ready at:
echo %TARGET_DIR%
pause
exit /b 0

:find_git
for %%G in (git.exe) do (
    where %%G >nul 2>nul
    if not errorlevel 1 (
        for /f "delims=" %%P in ('where %%G') do (
            set "GIT_EXE=%%P"
            goto :eof
        )
    )
)

if exist "%ProgramFiles%\Git\cmd\git.exe" (
    set "GIT_EXE=%ProgramFiles%\Git\cmd\git.exe"
    goto :eof
)

if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" (
    set "GIT_EXE=%ProgramFiles(x86)%\Git\cmd\git.exe"
    goto :eof
)

goto :eof
