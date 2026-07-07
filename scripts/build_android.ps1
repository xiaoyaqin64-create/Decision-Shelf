param([switch]$Debug)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $env:ANDROID_SDK_ROOT -and -not $env:ANDROID_HOME) {
    throw "Android SDK not found. Install Android Studio and set ANDROID_SDK_ROOT."
}
$javaOutput = (& java -version 2>&1 | Out-String)
if ($javaOutput -notmatch 'version "17[\.]') {
    throw "JDK 17 is required. Current Java: $javaOutput"
}
if (-not (Get-Command gradle -ErrorAction SilentlyContinue)) {
    throw "Gradle is not installed. Install Gradle 8.x or build with GitHub Actions."
}

Push-Location frontend
npm.cmd ci
npm.cmd run test
npm.cmd run build
Pop-Location

if ($Debug) {
    gradle -p android :app:assembleDebug
    $source = "android\app\build\outputs\apk\debug\app-debug.apk"
    $target = "release\Decision-Shelf-android-debug.apk"
} else {
    foreach ($name in 'ANDROID_KEYSTORE_PATH','ANDROID_KEY_ALIAS','ANDROID_STORE_PASSWORD','ANDROID_KEY_PASSWORD') {
        if (-not [Environment]::GetEnvironmentVariable($name)) { throw "Missing signing variable: $name" }
    }
    gradle -p android :app:assembleRelease
    $source = "android\app\build\outputs\apk\release\app-release.apk"
    $target = "release\Decision-Shelf-android-arm64.apk"
}
New-Item -ItemType Directory -Force -Path release | Out-Null
Copy-Item -LiteralPath $source -Destination $target -Force
Write-Host "Created $target"
