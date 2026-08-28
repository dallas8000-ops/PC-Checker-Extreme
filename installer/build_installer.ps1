<#
.SYNOPSIS
    Build the PC Checker Extreme Windows installer.

.DESCRIPTION
    This script prepares everything Inno Setup needs, then compiles the installer.
    It must be run from a machine that has internet access.

    Prerequisites (install once):
      - Inno Setup 6  ->  https://jrsoftware.org/isdl.php
      - Python 3.x on PATH (only for collectstatic; NOT bundled into the installer)

    The installer it produces has NO system requirements on the end-user machine:
    Python 3.12 and all packages are bundled inside the installer itself.

.EXAMPLE
    cd "C:\Software Projects\PC Checker Extreme"
    .\installer\build_installer.ps1
#>

[CmdletBinding()]
param(
    # Python version to embed (must match an available Windows embed zip on python.org)
    [string]$PythonVersion = '3.12.8',

    # Version string written into the installer (override for releases)
    [string]$AppVersion = '1.0.0'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectRoot  = (Resolve-Path "$PSScriptRoot\..").Path
$InstallerDir = $PSScriptRoot
$BuildDir     = Join-Path $InstallerDir 'build'
$EmbedDir     = Join-Path $BuildDir 'python'
$DistDir      = Join-Path $InstallerDir 'dist'

function Write-Step([string]$msg) {
    Write-Host "`n  $msg" -ForegroundColor Cyan
}
function Write-OK([string]$msg) {
    Write-Host "  OK  $msg" -ForegroundColor Green
}
function Write-Fail([string]$msg) {
    Write-Host "`n  ERROR: $msg" -ForegroundColor Red
    exit 1
}

Write-Host "`n╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   PC Checker Extreme - Installer Build       ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝`n" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 0. Locate Inno Setup compiler early so we fail fast if it's missing
# ---------------------------------------------------------------------------
Write-Step 'Locating Inno Setup compiler (ISCC.exe)...'
$IsccCandidates = @(
    'iscc',
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)
$Iscc = $null
foreach ($c in $IsccCandidates) {
    if (Get-Command $c -ErrorAction SilentlyContinue) { $Iscc = $c; break }
    if (Test-Path $c -ErrorAction SilentlyContinue)   { $Iscc = $c; break }
}
if (-not $Iscc) {
    Write-Fail @'
Inno Setup 6 not found.
Download and install it from https://jrsoftware.org/isdl.php, then re-run this script.
'@
}
Write-OK "Found: $Iscc"

# ---------------------------------------------------------------------------
# 1. Clean / create build dir
# ---------------------------------------------------------------------------
Write-Step 'Preparing build directory...'
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
New-Item -ItemType Directory -Path $EmbedDir | Out-Null
New-Item -ItemType Directory -Path $DistDir  -ErrorAction SilentlyContinue | Out-Null
Write-OK $BuildDir

# ---------------------------------------------------------------------------
# 2. Download Python embeddable zip
# ---------------------------------------------------------------------------
Write-Step "Downloading Python $PythonVersion embeddable (x64)..."
$ZipUrl  = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$ZipPath = Join-Path $BuildDir 'python-embed.zip'
Invoke-WebRequest $ZipUrl -OutFile $ZipPath -UseBasicParsing
Write-OK "Downloaded $('{0:N1} MB' -f ((Get-Item $ZipPath).Length / 1MB))"

# ---------------------------------------------------------------------------
# 3. Extract and configure the embeddable Python
# ---------------------------------------------------------------------------
Write-Step 'Extracting and configuring embedded Python...'
Expand-Archive $ZipPath -DestinationPath $EmbedDir -Force

# Enable site-packages so pip-installed libraries are importable
$PthFile = Get-ChildItem $EmbedDir -Filter 'python*._pth' | Select-Object -First 1
if (-not $PthFile) { Write-Fail "Could not find ._pth file inside the Python embeddable zip." }
$PthContent = Get-Content $PthFile.FullName -Raw
if ($PthContent -notmatch 'import site\b') {
    $PthContent = $PthContent -replace '#import site', 'import site'
    Set-Content $PthFile.FullName $PthContent -Encoding ASCII
}
Write-OK "site-packages enabled in $($PthFile.Name)"

# ---------------------------------------------------------------------------
# 4. Bootstrap pip inside the embeddable Python
# ---------------------------------------------------------------------------
Write-Step 'Bootstrapping pip...'
$GetPipPath = Join-Path $BuildDir 'get-pip.py'
Invoke-WebRequest 'https://bootstrap.pypa.io/get-pip.py' -OutFile $GetPipPath -UseBasicParsing
$EmbedPython = Join-Path $EmbedDir 'python.exe'
& $EmbedPython $GetPipPath --no-warn-script-location --quiet
if ($LASTEXITCODE -ne 0) { Write-Fail 'pip bootstrap failed.' }
Write-OK 'pip installed'

# ---------------------------------------------------------------------------
# 5. Install application requirements into the embeddable Python
# ---------------------------------------------------------------------------
Write-Step 'Installing application packages (this takes a few minutes)...'
$ReqFile = Join-Path $ProjectRoot 'requirements.txt'
& $EmbedPython -m pip install `
    -r $ReqFile `
    --no-warn-script-location `
    --quiet
if ($LASTEXITCODE -ne 0) { Write-Fail 'pip install failed. Check your internet connection or requirements.txt.' }
Write-OK 'All packages installed'

# ---------------------------------------------------------------------------
# 6. Collect static files into staticfiles/
# ---------------------------------------------------------------------------
Write-Step 'Collecting static files...'
Push-Location $ProjectRoot
try {
    & $EmbedPython manage.py collectstatic --noinput --clear --quiet
    if ($LASTEXITCODE -ne 0) { Write-Fail 'collectstatic failed.' }
} finally {
    Pop-Location
}
Write-OK 'Static files collected'

# ---------------------------------------------------------------------------
# 7. Build pre-migrated, pre-seeded database
#    Run on the build machine so the customer never needs to run migrate.
#    Temporarily moves the dev db aside so Django creates a clean slate.
# ---------------------------------------------------------------------------
Write-Step 'Building pre-seeded database...'
$DevDb    = Join-Path $ProjectRoot 'db.sqlite3'
$BuildDb  = Join-Path $BuildDir    'db.sqlite3'
$BackupDb = Join-Path $BuildDir    'db_dev_backup.sqlite3'

if (Test-Path $DevDb) { Move-Item $DevDb $BackupDb -Force }
try {
    Push-Location $ProjectRoot
    try {
        & $EmbedPython manage.py migrate --run-syncdb
        if ($LASTEXITCODE -ne 0) { Write-Fail 'migrate failed during database build.' }

        & $EmbedPython manage.py seed_driver_sources --segment all
        if ($LASTEXITCODE -ne 0) { Write-Fail 'seed_driver_sources failed during database build.' }
    } finally {
        Pop-Location
    }

    if (-not (Test-Path $DevDb)) { Write-Fail 'migrate did not produce db.sqlite3 at expected path.' }
    Copy-Item $DevDb $BuildDb -Force
    Write-OK "Pre-seeded database ready ($('{0:N0} KB' -f ((Get-Item $BuildDb).Length / 1KB)))"
} finally {
    # Always restore the dev database whether the build succeeded or failed.
    Remove-Item $DevDb -ErrorAction SilentlyContinue
    if (Test-Path $BackupDb) { Move-Item $BackupDb $DevDb -Force }
}

# ---------------------------------------------------------------------------
# 8. Verify icon.ico exists  (developer must supply this)
# ---------------------------------------------------------------------------
Write-Step 'Checking for app icon...'
$IconPath = Join-Path $InstallerDir 'icon.ico'
if (-not (Test-Path $IconPath)) {
    Write-Host @'

  WARNING: installer\icon.ico not found.
  The installer will use a generic script icon for shortcuts.
  To use a custom icon, place a 256x256 (or multi-size) .ico file at:
      installer\icon.ico
  You can convert a PNG online at https://convertico.com/

'@ -ForegroundColor Yellow

    # Create a placeholder so Inno Setup does not error on the missing file.
    # Replace this with your real icon before shipping.
    $PythonIco = Join-Path $EmbedDir 'python.exe'
    # Copy the embedded python.exe as a stand-in - Inno Setup will extract its icon.
    # (Inno Setup accepts an .exe as IconFilename source and extracts resource index 0.)
    Copy-Item $PythonIco $IconPath -ErrorAction SilentlyContinue
    Write-Host '  Placeholder icon created from python.exe. Replace before release.' -ForegroundColor Yellow
} else {
    Write-OK 'icon.ico found'
}

# ---------------------------------------------------------------------------
# 9. Compile the Inno Setup installer
# ---------------------------------------------------------------------------
Write-Step 'Compiling installer with Inno Setup...'
$IssFile = Join-Path $InstallerDir 'PCCheckerExtreme.iss'

# Patch the AppVersion in the .iss at compile time via /D define
& $Iscc $IssFile "/DAppVersion=$AppVersion" "/Q"
if ($LASTEXITCODE -ne 0) { Write-Fail 'Inno Setup compilation failed. Check the output above for details.' }

$SetupExe = Join-Path $DistDir 'PCCheckerExtreme-Setup.exe'
Write-Host "`n╔══════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   BUILD COMPLETE                             ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host "`n  Installer : $SetupExe" -ForegroundColor Green
Write-Host "  Size      : $('{0:N1} MB' -f ((Get-Item $SetupExe).Length / 1MB))`n" -ForegroundColor Green
