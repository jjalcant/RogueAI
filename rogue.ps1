param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$args
)

cd C:\RogueAI

if (Test-Path ".venv\Scripts\Activate.ps1") {
    .\.venv\Scripts\Activate.ps1
}

python brain.py @args