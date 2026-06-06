# claude-prompt-lint installer (Windows / PowerShell).
# Pure-Python plugin, zero pip dependencies. This checks Python and self-tests.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "claude-prompt-lint - install check"
Write-Host "  repo: $Root"

$Py = $null
foreach ($cand in @("python", "python3", "py")) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd) { $Py = $cmd.Source; break }
}
if (-not $Py) {
    Write-Error "  No python on PATH. Install Python 3.8+ and re-run."
    exit 1
}
Write-Host "  python: $(& $Py --version)"

Write-Host "  running self-check (a weak prompt should be flagged)..."
$payload = '{"prompt":"can you please just go ahead and fix it and make this better for me"}'
$out = $payload | & $Py "$Root\hooks\dispatcher.py" --event UserPromptSubmit
if ($out) {
    Write-Host "  gate produced feedback. Self-check passed."
} else {
    Write-Host "  WARNING: gate produced no output for a weak prompt. Check config\cpl.config.json."
}

Write-Host ""
Write-Host "Next: register the plugin in Claude Code (see README -> Install)."
Write-Host "Lint your prompt before you spend the token."
