param(
    [string]$ProfileDir = (Join-Path $env:LOCALAPPDATA "CNINFOChromeProfile")
)

$chromeCandidates = @(
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
    (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
)
$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) {
    throw "Google Chrome was not found. Install Chrome before running this script."
}

$resolvedProfile = [System.IO.Path]::GetFullPath($ProfileDir)
New-Item -ItemType Directory -Path $resolvedProfile -Force | Out-Null
$arguments = @(
    "--remote-debugging-port=9222",
    "--remote-debugging-address=127.0.0.1",
    "--user-data-dir=$resolvedProfile",
    "https://pis.cninfo.com.cn/ics/index.html#/industryChain/A02n019/lsx019/A02n019/%E5%A4%AA%E9%98%B3%E8%83%BDEVA%E8%83%B6%E8%86%9C"
)
Start-Process -FilePath $chrome -ArgumentList $arguments -WindowStyle Normal
