param(
    [Parameter(Mandatory=$false)]
    [string]$RepoUrl
)

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " CANONICAL ID MAPPING - GITHUB PUSH HELPER" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 1. Locate Git executable
$gitPath = (Get-Command git -ErrorAction SilentlyContinue).Source

if (-not $gitPath) {
    $commonPaths = @(
        "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\git.exe",
        "C:\Program Files\Git\cmd\git.exe",
        "C:\Program Files\Git\bin\git.exe",
        "C:\Program Files (x86)\Git\cmd\git.exe"
    )
    foreach ($p in $commonPaths) {
        if (Test-Path $p) {
            $gitPath = $p
            break
        }
    }
}

if (-not $gitPath) {
    Write-Host "`n[!] Git is not installed or not in your PATH." -ForegroundColor Yellow
    Write-Host "To install Git on Windows, open PowerShell as Administrator and run:" -ForegroundColor White
    Write-Host "    winget install Git.Git" -ForegroundColor Green
    Write-Host "Or download it from: https://git-scm.com/download/win" -ForegroundColor White
    Write-Host "`nAfter installing Git, restart your terminal and re-run this script." -ForegroundColor White
    exit 1
}

Write-Host "[OK] Located Git at: $gitPath" -ForegroundColor Green

# 2. Get repository URL if not provided
if (-not $RepoUrl) {
    Write-Host "`nPlease enter your public GitHub repository URL (e.g. https://github.com/username/canonical_id_mapping.git):" -ForegroundColor Yellow
    $RepoUrl = Read-Host "Repository URL"
}

if (-not $RepoUrl) {
    Write-Host "[ERROR] Repository URL cannot be empty." -ForegroundColor Red
    exit 1
}

# 3. Initialize, commit, and push
Write-Host "`nInitializing Git repository..." -ForegroundColor Cyan
& $gitPath init

Write-Host "Staging files..." -ForegroundColor Cyan
& $gitPath add .

Write-Host "Creating initial commit..." -ForegroundColor Cyan
& $gitPath commit -m "feat: complete production-grade canonical ID mapping solution with conflict detection and SCD2 history"

Write-Host "Setting default branch to main..." -ForegroundColor Cyan
& $gitPath branch -M main

Write-Host "Configuring remote origin: $RepoUrl..." -ForegroundColor Cyan
& $gitPath remote remove origin 2>$null
& $gitPath remote add origin $RepoUrl

Write-Host "`nPushing to GitHub..." -ForegroundColor Cyan
& $gitPath push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=================================================================" -ForegroundColor Green
    Write-Host " [SUCCESS] Code successfully pushed to $RepoUrl!" -ForegroundColor Green
    Write-Host "=================================================================" -ForegroundColor Green
} else {
    Write-Host "`n[!] Push failed. Please verify that your repository exists and that you have write access." -ForegroundColor Red
}

