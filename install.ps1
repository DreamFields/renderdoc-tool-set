[CmdletBinding()]
param(
    [string]$RepoOwner = "DreamFields",
    [string]$RepoName = "renderdoc-tool-set",
    [string]$Ref = "master",
    [switch]$SkipExtension,
    [switch]$SkipMcpToolInstall,
    [switch]$KeepTemp
)

$ErrorActionPreference = "Stop"

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Write-Step {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "[install] $Message" -ForegroundColor Cyan
}

if (-not (Test-Command -Name "python")) {
    throw "python command not found. Please install Python 3.10+ first: https://www.python.org/downloads/"
}

if (-not (Test-Command -Name "uv")) {
    throw "uv command not found. Please install uv first: https://docs.astral.sh/uv/getting-started/installation/"
}

$tempRoot = Join-Path $env:TEMP "customrenderdocmcp_installer"
$sessionDir = Join-Path $tempRoot ([Guid]::NewGuid().ToString("N"))
$zipPath = Join-Path $sessionDir "source.zip"
$extractDir = Join-Path $sessionDir "src"

$zipUrl = "https://codeload.github.com/$RepoOwner/$RepoName/zip/refs/heads/$Ref"

Write-Step "Preparing temporary directory: $sessionDir"
New-Item -ItemType Directory -Path $sessionDir -Force | Out-Null
New-Item -ItemType Directory -Path $extractDir -Force | Out-Null

Write-Step "Downloading source archive from $zipUrl"
Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath

Write-Step "Extracting archive"
Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

$projectDir = Get-ChildItem -Path $extractDir -Directory | Select-Object -First 1
if (-not $projectDir) {
    throw "Cannot find extracted project directory."
}

$projectPath = $projectDir.FullName
Write-Step "Project extracted to: $projectPath"

if (-not $SkipExtension) {
    Write-Step "Installing RenderDoc extension (sync mode)"
    & python (Join-Path $projectPath "scripts/install_extension.py") sync
    if ($LASTEXITCODE -ne 0) {
        throw "Extension installation failed with exit code $LASTEXITCODE"
    }
}

if (-not $SkipMcpToolInstall) {
    Write-Step "Installing MCP server command into uv tool environment"
    & uv tool install $projectPath --force
    if ($LASTEXITCODE -ne 0) {
        throw "uv tool install failed with exit code $LASTEXITCODE"
    }

    Write-Step "Refreshing shell command shims"
    & uv tool update-shell
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "uv tool update-shell exited with code $LASTEXITCODE. You may need to restart your shell manually."
    }
}

Write-Host ""
Write-Host "Installation finished." -ForegroundColor Green
Write-Host "You can now run: renderdoc_toolset" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1) Restart RenderDoc"
Write-Host "2) Enable extension: Tools > Manage Extensions > RenderDoc renderdoc_toolset_bridge"
Write-Host "3) Configure MCP client command to: renderdoc_toolset"

if (-not $KeepTemp) {
    Write-Step "Cleaning temporary files"
    Remove-Item -Path $sessionDir -Recurse -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "Temp files kept at: $sessionDir" -ForegroundColor DarkYellow
}
