param(
    [string]$KeystorePath = "$HOME\.decision-shelf-signing\decision-shelf-release.jks",
    [string]$Alias = "decision-shelf"
)

$ErrorActionPreference = "Stop"
if (Test-Path -LiteralPath $KeystorePath) {
    throw "Keystore already exists: $KeystorePath"
}
$keytool = Get-Command keytool -ErrorAction Stop
$directory = Split-Path -Parent $KeystorePath
New-Item -ItemType Directory -Force -Path $directory | Out-Null

$securePassword = Read-Host "Create a strong keystore password" -AsSecureString
$confirmation = Read-Host "Repeat the password" -AsSecureString
$pointerA = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$pointerB = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($confirmation)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointerA)
    $repeated = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointerB)
    if ([string]::IsNullOrWhiteSpace($password) -or $password.Length -lt 12) {
        throw "Password must contain at least 12 characters."
    }
    if ($password -ne $repeated) { throw "Passwords do not match." }
    & $keytool.Source -genkeypair -v -keystore $KeystorePath -alias $Alias `
        -keyalg RSA -keysize 4096 -validity 10000 `
        -storepass $password -keypass $password `
        -dname "CN=Decision Shelf, OU=Personal Release, O=Decision Shelf, C=CN"
    if ($LASTEXITCODE -ne 0) { throw "keytool failed." }
} finally {
    if ($pointerA -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointerA) }
    if ($pointerB -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointerB) }
    $password = $null
    $repeated = $null
}

Write-Host "Created fixed release keystore: $KeystorePath"
Write-Host "Back up this file and its password separately. Never commit either one."
Write-Host "GitHub secrets: ANDROID_KEYSTORE_BASE64, ANDROID_KEY_ALIAS, ANDROID_STORE_PASSWORD, ANDROID_KEY_PASSWORD"
