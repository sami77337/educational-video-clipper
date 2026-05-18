param(
    [string]$TargetPath = "",
    [string]$WorkingDirectory = "",
    [string]$IconPath = ""
)

$ErrorActionPreference = "Stop"

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutName = "المقص البسيط.lnk"
$shortcutPath = Join-Path $desktop $shortcutName

if ([string]::IsNullOrWhiteSpace($TargetPath)) {
    $scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    $builtExe = Join-Path $scriptRoot "dist\AlmiqsAlBaseet\AlmiqsAlBaseet.exe"
    if (Test-Path $builtExe) {
        $TargetPath = $builtExe
        $WorkingDirectory = Split-Path -Parent $builtExe
    } else {
        $TargetPath = Join-Path $scriptRoot "run_app.bat"
        $WorkingDirectory = $scriptRoot
    }
}

if (!(Test-Path $TargetPath)) {
    throw "Target file does not exist: $TargetPath"
}

if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) {
    $WorkingDirectory = Split-Path -Parent $TargetPath
}

if ([string]::IsNullOrWhiteSpace($IconPath) -or !(Test-Path $IconPath)) {
    $scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    $candidateIcon = Join-Path $scriptRoot "assets\icon.ico"
    if (Test-Path $candidateIcon) {
        $IconPath = $candidateIcon
    } else {
        $IconPath = $TargetPath
    }
}

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $TargetPath
$shortcut.WorkingDirectory = $WorkingDirectory
$shortcut.IconLocation = $IconPath
$shortcut.Description = "المقص البسيط"
$shortcut.Save()

Write-Host "Created desktop shortcut:" $shortcutPath
