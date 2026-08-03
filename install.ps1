[CmdletBinding()]
param(
    [switch]$SerpApiOnly
)

$ErrorActionPreference = "Stop"
$SkillDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Python {
    $candidates = @(
        @{ Command = "py"; Args = @("-3") },
        @{ Command = "python"; Args = @() },
        @{ Command = "python3"; Args = @() }
    )
    foreach ($candidate in $candidates) {
        if (Get-Command $candidate.Command -ErrorAction SilentlyContinue) {
            try {
                $version = & $candidate.Command @($candidate.Args) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
                if ($LASTEXITCODE -eq 0) {
                    $parts = $version.Trim().Split('.')
                    if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10)) {
                        return $candidate
                    }
                }
            } catch {}
        }
    }
    throw "Python 3.10 or newer was not found."
}

$Python = Find-Python
$PythonArgs = [string[]]$Python.Args
$Packages = @("requests>=2.31,<3", "Pillow>=10,<13")
if (-not $SerpApiOnly) { $Packages += "ddgs>=9.9,<10" }

Write-Host "Using existing Python installation. No virtual environment will be created."
Write-Host "pip will reuse compatible packages and install only missing/outdated ones into your user profile."
& $Python.Command @PythonArgs -m pip install --user --disable-pip-version-check --no-cache-dir @Packages
if ($LASTEXITCODE -ne 0) { throw "Package installation failed." }

& $Python.Command @PythonArgs (Join-Path $SkillDir "scripts\skill.py") check
if ($LASTEXITCODE -ne 0) {
    if ($SerpApiOnly) {
        Write-Warning "SerpApi-only mode requires SERPAPI_API_KEY or SERPAPI_KEY to be configured."
    } else {
        throw "Dependency check failed."
    }
}
Write-Host "Website Image Finder 0.2.0 is ready. Restart Codex if it is already open."
