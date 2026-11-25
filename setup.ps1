<#
.SYNOPSIS
  Sets up HX Edit Unbound on this PC, once. Safe to run again: it skips what is already done.

.DESCRIPTION
  Checks Windows (64-bit), the official HX Edit 3.82, Python 3.10+ (64-bit) and Git; puts the converter
  (andreidevs/helix-lt-nam, a fixed commit) next to this folder; makes the Python environment (.venv) with the
  packages the editor needs; offers the sharper gear pictures; asks once for your TONE3000 Publishable Key.
  HX Edit itself is never copied or changed here: each launch makes its own copy from your install.

.PARAMETER Art
  yes / no: download the art pack without asking. Default: ask.
.PARAMETER ArtTag
  The release the art pack comes from. Default: gear-art-2026-11-22.
.PARAMETER Key
  Your TONE3000 Publishable Key (starts with t3k_pub_), saved without asking. "skip" leaves it out. Default: ask.

.EXAMPLE
  .\setup.ps1
.EXAMPLE
  .\setup.ps1 -Art no -Key skip
#>
[CmdletBinding()]
param(
  [ValidateSet('ask', 'yes', 'no')][string]$Art = 'ask',
  [string]$ArtTag = 'gear-art-2026-11-22',
  [string]$Key = ''
)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$HxEditHash = 'f7faac4996164f9039c9ae3ca8d85cd135c5bceae8a511c8921a1244046cab66'   # HX Edit 3.82 (src\nam_catalog.py)
$ConverterRepo = 'https://github.com/andreidevs/helix-lt-nam.git'
$ConverterCommit = 'c94834768546393420692794fdbb27c9cc31d718'
$Packages = @('frida==17.5.2', 'msgpack==1.2.4', 'numpy', 'sounddevice==0.5.6', 'soundfile==0.14.0')
$ArtRepo = 'https://github.com/Suddl3/hx-edit-unbound'
$ArtPacks = @('helix-gear-art', 'nam-gear-art', 'focus-backgrounds')
$ArtFolders = @('helix-gear-art\full', 'nam-gear-art\full', 'focus-backgrounds\sources')
$SettingsFolder = Join-Path $env:LOCALAPPDATA 'HX Edit NAM'
$KeyFile = Join-Path $SettingsFolder 'tone3000-publishable-key'

function Say([string]$text) { Write-Host $text }
function Done([string]$text) { Write-Host "  OK  $text" -ForegroundColor Green }
function Skip([string]$text) { Write-Host "  --  $text" -ForegroundColor DarkGray }
function Stop-Setup([string]$text) {
  Write-Host ''
  Write-Host $text -ForegroundColor Yellow
  Write-Host 'Nothing else was changed. Run .\setup.ps1 again once that is done.'
  exit 1
}
function Ask-YesNo([string]$question) {
  $answer = Read-Host "$question [y/N]"
  return $answer -match '^(y|yes)$'
}

Say 'Setting up HX Edit Unbound'
Say ''

# 1. Windows, 64-bit
if (-not [Environment]::Is64BitOperatingSystem) {
  Stop-Setup 'HX Edit Unbound needs 64-bit Windows 10 or 11.'
}
Done 'Windows is 64-bit'

# 2. The official HX Edit 3.82, in its default folder (or HX_EDIT_SOURCE_DIRECTORY)
$ProgramFiles86 = ${env:ProgramFiles(x86)}
if (-not $ProgramFiles86) { $ProgramFiles86 = 'C:\Program Files (x86)' }
$HxEditFolder = Join-Path $ProgramFiles86 'Line6\HX Edit'
if ($env:HX_EDIT_SOURCE_DIRECTORY) { $HxEditFolder = $env:HX_EDIT_SOURCE_DIRECTORY }
$HxEditExe = Join-Path $HxEditFolder 'HX Edit.exe'
if (-not (Test-Path -LiteralPath $HxEditExe)) {
  Stop-Setup ("HX Edit was not found in $HxEditFolder. Install the official Line 6 HX Edit 3.82 " +
              '(line6.com/software) in its default folder, then run setup again.')
}
$found = (Get-FileHash -Algorithm SHA256 -LiteralPath $HxEditExe).Hash.ToLowerInvariant()
if ($found -ne $HxEditHash) {
  Stop-Setup ("The HX Edit in $HxEditFolder is not version 3.82. HX Edit Unbound works only with HX Edit 3.82: " +
              'install that version from line6.com/software, then run setup again.')
}
Done "HX Edit 3.82 found in $HxEditFolder"

# 3. Python 3.10 or newer, 64-bit, through the Python launcher "py"
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
  Stop-Setup ('Python was not found. Install Python 3.10 or newer (64-bit) from https://www.python.org/downloads/windows/ ' +
              '(keep "py launcher" ticked), then run setup again.')
}
$pyInfo = & py -3 -c "import struct, sys; print('%d.%d %d' % (sys.version_info[0], sys.version_info[1], struct.calcsize('P') * 8))" 2>$null
if ($LASTEXITCODE -ne 0 -or -not $pyInfo) {
  Stop-Setup 'Python 3 did not start. Install Python 3.10 or newer (64-bit) from https://www.python.org/downloads/windows/.'
}
$version, $bits = ($pyInfo | Select-Object -Last 1).Trim().Split(' ')
$major, $minor = $version.Split('.') | ForEach-Object { [int]$_ }
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10) -or $bits -ne '64') {
  Stop-Setup ("Python $version ($bits-bit) is too old or not 64-bit. Install Python 3.10 or newer (64-bit) from " +
              'https://www.python.org/downloads/windows/, then run setup again.')
}
Done "Python $version (64-bit)"

# 4. Git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Stop-Setup 'Git was not found. Install Git from https://git-scm.com/download/win, then run setup again.'
}
Done 'Git found'

# 5. The converter: andreidevs/helix-lt-nam next to this folder, at the commit this editor is made for
$Converter = Join-Path (Split-Path -Parent $Here) 'helix-lt-nam'
if (Test-Path -LiteralPath (Join-Path $Converter '.git')) {
  $at = (& git -C $Converter rev-parse HEAD 2>$null)
  if ($at -eq $ConverterCommit) { Skip "The converter is already there ($Converter, commit $($at.Substring(0, 7)))" }
  else {
    Skip ("The converter is already there ($Converter) on commit $at; left as it is. " +
          "This editor is made for commit $($ConverterCommit.Substring(0, 7)).")
  }
} elseif (Test-Path -LiteralPath $Converter) {
  Stop-Setup "There is a folder $Converter that is not a Git checkout. Move it away, then run setup again."
} else {
  Say "  ..  Getting the converter (helix-lt-nam) into $Converter"
  & git clone --quiet $ConverterRepo $Converter
  if ($LASTEXITCODE -ne 0) { Stop-Setup 'Getting helix-lt-nam from GitHub failed. Check the internet connection.' }
  & git -C $Converter -c advice.detachedHead=false checkout --quiet $ConverterCommit
  if ($LASTEXITCODE -ne 0) { Stop-Setup "helix-lt-nam has no commit $ConverterCommit." }
  Done "The converter is in $Converter (commit $($ConverterCommit.Substring(0, 7)))"
}

# 6. The Python environment (.venv) and its packages
$Venv = Join-Path $Here '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython)) {
  Say '  ..  Making the Python environment (.venv)'
  & py -3 -m venv $Venv
  if ($LASTEXITCODE -ne 0) { Stop-Setup 'Python could not make the environment in .venv.' }
}
& $VenvPython -c "import frida, msgpack, numpy, sounddevice, soundfile; assert frida.__version__ == '17.5.2'" 2>$null
if ($LASTEXITCODE -eq 0) { Skip 'The Python packages are already installed' }
else {
  Say '  ..  Installing the Python packages (a minute or two)'
  & $VenvPython -m pip install --quiet --disable-pip-version-check @Packages
  if ($LASTEXITCODE -ne 0) { Stop-Setup 'Installing the Python packages failed. Check the internet connection.' }
  Done 'Python packages installed'
}

# 7. The art pack (optional: without it the Workbench uses the smaller pictures that come with the editor)
$ArtRoot = Join-Path $Here 'art'
$haveArt = $true
foreach ($folder in $ArtFolders) { if (-not (Test-Path -LiteralPath (Join-Path $ArtRoot $folder))) { $haveArt = $false } }
if ($haveArt) { Skip 'The art pack is already there' }
else {
  $want = $Art -eq 'yes'
  if ($Art -eq 'ask') { $want = Ask-YesNo 'Download the sharper gear pictures and scenes (about 210 MB)?' }
  if ($want) {
    New-Item -ItemType Directory -Force -Path $ArtRoot | Out-Null
    $previous = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'
    try {
      foreach ($pack in $ArtPacks) {
        $zip = Join-Path $env:TEMP "$pack.zip"
        Say "  ..  Downloading $pack"
        Invoke-WebRequest -UseBasicParsing "$ArtRepo/releases/download/$ArtTag/$pack.zip" -OutFile $zip
        Expand-Archive -LiteralPath $zip -DestinationPath $ArtRoot -Force
        Remove-Item -LiteralPath $zip -Force
      }
    } catch {
      Stop-Setup "The art pack could not be downloaded ($($_.Exception.Message)). The editor works without it."
    } finally { $ProgressPreference = $previous }
    Done "Art pack ($ArtTag) in $ArtRoot"
  } else { Skip 'No art pack (run setup again to get it later)' }
}

# 8. The TONE3000 Publishable Key, saved once (T3K_PUBLISHABLE_KEY still wins when it is set)
function Test-PublishableKey([string]$value) { return $value -match '^t3k_pub_\S+$' }
if ($Key -eq 'skip') { Skip 'TONE3000 key left out' }
elseif ($Key) {
  if (-not (Test-PublishableKey $Key)) { Stop-Setup 'That is not a TONE3000 Publishable Key: it starts with t3k_pub_. Never use a Secret Key.' }
  New-Item -ItemType Directory -Force -Path $SettingsFolder | Out-Null
  [IO.File]::WriteAllText($KeyFile, $Key, (New-Object Text.UTF8Encoding $false))
  Done 'TONE3000 key saved'
} elseif (Test-Path -LiteralPath $KeyFile) { Skip 'A TONE3000 key is already saved' }
else {
  Say ''
  Say 'TONE3000 (optional): to browse and preview tones from TONE3000, paste your own Publishable Key.'
  Say 'It is on tone3000.com under Settings > API Keys and starts with t3k_pub_. Never paste a Secret Key.'
  while ($true) {
    $entered = (Read-Host 'Publishable Key (press Enter to skip)').Trim()
    if (-not $entered) { Skip 'TONE3000 key left out (run setup again to add it)'; break }
    if (Test-PublishableKey $entered) {
      New-Item -ItemType Directory -Force -Path $SettingsFolder | Out-Null
      [IO.File]::WriteAllText($KeyFile, $entered, (New-Object Text.UTF8Encoding $false))
      Done 'TONE3000 key saved'
      break
    }
    Say 'That is not a Publishable Key (it starts with t3k_pub_). Try again, or press Enter to skip.'
  }
}

Say ''
Say 'Setup is done. Start HX Edit Unbound with:  .\start.ps1'
