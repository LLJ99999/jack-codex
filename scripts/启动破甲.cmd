@echo off
chcp 65001 >nul
setlocal
if not defined CODEX_HOME set "CODEX_HOME=%USERPROFILE%\.codex"
set "HERE=%~dp0"
if exist "%HERE%jack-purge-proxy.mjs" (
  set "PROXY=%HERE%jack-purge-proxy.mjs"
) else if exist "%HERE%resources\scripts\jack-purge-proxy.mjs" (
  set "PROXY=%HERE%resources\scripts\jack-purge-proxy.mjs"
) else if exist "%CODEX_HOME%\.jack-codex\jack-purge-proxy.mjs" (
  set "PROXY=%CODEX_HOME%\.jack-codex\jack-purge-proxy.mjs"
) else (
  echo 找不到 jack-purge-proxy.mjs
  pause
  exit /b 1
)
if "%JACK_PURGE_UPSTREAM%"=="" if exist "%CODEX_HOME%\.jack-codex\purge-upstream.txt" (
  set /p JACK_PURGE_UPSTREAM=<"%CODEX_HOME%\.jack-codex\purge-upstream.txt"
)
if "%JACK_PURGE_UPSTREAM%"=="" (
  echo 没有上游。先点应用里的「安装」（会从现有 base_url 写入 purge-upstream.txt）
  echo 或手动：
  echo   set JACK_PURGE_UPSTREAM=https://YOUR_RELAY_ORIGIN
  pause
  exit /b 1
)
set "JACK_PURGE_LISTEN=127.0.0.1:8787"
set "JACK_PURGE_PERSONA=%CODEX_HOME%\managed-prompts\jack-codex-v1.md"
set "JACK_PURGE_LOG=1"
echo 代理: %JACK_PURGE_LISTEN%  -^>  %JACK_PURGE_UPSTREAM%
echo 判定: http://127.0.0.1:8787/health
echo 完全退出 Codex 再开。新会话先发「破甲」。
node "%PROXY%"
pause
