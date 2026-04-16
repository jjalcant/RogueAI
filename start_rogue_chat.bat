@echo off
cd /d C:\RogueAI

if exist .venv\Scripts\activate (
    call .venv\Scripts\activate
)

echo start_rogue_chat.bat is kept for compatibility.
echo Use start_rogue.bat as the official launcher.
call start_rogue.bat
