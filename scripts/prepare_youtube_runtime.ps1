param(
    [Parameter(Mandatory = $true)]
    [string]$DestinationDir
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$downloadUrl = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
$destination = [System.IO.Path]::GetFullPath($DestinationDir)
$tempRoot = Join-Path $env:TEMP ("almiqs-deno-" + [guid]::NewGuid().ToString("N"))
$zipPath = Join-Path $tempRoot "deno.zip"
$extractDir = Join-Path $tempRoot "extract"
$targetPath = Join-Path $destination "deno.exe"

try {
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $extractDir | Out-Null

    Write-Host "Downloading current Deno runtime for YouTube extraction..."
    Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath -UseBasicParsing
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force

    $sourcePath = Join-Path $extractDir "deno.exe"
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "Deno archive did not contain deno.exe"
    }

    Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force
    $versionLine = & $targetPath --version | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) {
        throw "Downloaded deno.exe failed to execute"
    }

    Write-Host ("Prepared YouTube JavaScript runtime: " + $versionLine)
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
