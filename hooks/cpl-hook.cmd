@echo off
REM Portable launcher for the cpl dispatcher (Windows cmd.exe).
REM Finds a working Python interpreter, forwards all args + stdin to the
REM dispatcher. Fail-open: if none is found, exit 0 with no output so the
REM user's prompt is never blocked by a missing dependency.
setlocal

where python >nul 2>nul && (
  python "%~dp0dispatcher.py" %*
  exit /b %ERRORLEVEL%
)
where python3 >nul 2>nul && (
  python3 "%~dp0dispatcher.py" %*
  exit /b %ERRORLEVEL%
)
where py >nul 2>nul && (
  py "%~dp0dispatcher.py" %*
  exit /b %ERRORLEVEL%
)

REM No Python found — fail open.
exit /b 0
