[CmdletBinding()]
param([switch]$SerpApiOnly)

$ErrorActionPreference = "Stop"
$SkillDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = $null

foreach ($candidate in @(
    @{ Command = "py"; Args = @("-3") },
    @{ Command = "python"; Args = @() },
    @{ Command = "python3"; Args = @() }
)) {
    if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) { continue }
    try {
        $version = & $candidate.Command @($candidate.Args) -c "import sys; print(sys.version_info >= (3,10))"
        if ($LASTEXITCODE -eq 0 -and $version.Trim() -eq "True") {
            $Python = $candidate
            break
        }
    } catch {}
}

if ($null -eq $Python) { throw "Python 3.10+ is required; install Python before using this skill." }
if ($SerpApiOnly) {
    Write-Warning "The SerpApiOnly installer switch is deprecated. Google Images now requires an explicit --provider serpapi flag at search time."
}
& $Python.Command @($Python.Args) (Join-Path $SkillDir "scripts\skill.py") setup
if ($LASTEXITCODE -ne 0) { throw "Website Image Finder isolated setup failed." }
Write-Host "Website Image Finder 0.4.0 is ready. No paid image search is enabled by default."
