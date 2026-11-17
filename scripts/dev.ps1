param(
    [ValidateSet('kur', 'sunucu', 'test', 'lint', 'paket')]
    [string]$Islem = 'sunucu'
)
$ErrorActionPreference = 'Stop'
$Kok = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $Kok
$Adlar = @('TAHTA_VERI_DIZINI', 'TAHTA_HTTP_MAKINE', 'TAHTA_HTTPS_MAKINE', 'TAHTA_HTTP_PORT', 'TAHTA_HTTPS_PORT')
$Eski = @{}
foreach ($Ad in $Adlar) { $Eski[$Ad] = [Environment]::GetEnvironmentVariable($Ad, 'Process') }
try {
    $Python = Join-Path $Kok '.venv\Scripts\python.exe'
    if ($Islem -eq 'kur') {
        $Uv = Get-Command uv -ErrorAction SilentlyContinue
        if ($Uv) { $UvYolu = $Uv.Source }
        else {
            # Bu bilgisayardaki ilk hazırlıkta indirilen taşınabilir araç.
            $UvYolu = Join-Path $Kok '..\..\work\tools\uv\uv.exe'
            if (-not (Test-Path -LiteralPath $UvYolu)) { throw 'uv bulunamadı. uv kurup kur komutunu yeniden çalıştırın.' }
        }
        & $UvYolu sync --locked
        if ($LASTEXITCODE -ne 0) { throw 'Bağımlılık kurulumu başarısız.' }
    } else {
        if (-not (Test-Path -LiteralPath $Python)) { throw 'Önce scripts\dev.ps1 kur komutunu çalıştırın.' }
        $env:TAHTA_VERI_DIZINI = Join-Path $Kok 'work\dev-veri'
        $env:TAHTA_HTTP_MAKINE = '127.0.0.1'
        $env:TAHTA_HTTPS_MAKINE = '127.0.0.1'
        $env:TAHTA_HTTP_PORT = '8797'
        $env:TAHTA_HTTPS_PORT = '8798'
        switch ($Islem) {
            'sunucu' { & $Python -m tahta_sunucu }
            'test' { & $Python -m pytest -q }
            'lint' { & $Python -m ruff check . }
            'paket' {
                New-Item -ItemType Directory -Force (Join-Path $Kok 'dist') | Out-Null
                & $Python -m tahta_sunucu paket (Join-Path $Kok 'dist\tahta-ajan.deb')
            }
        }
        if ($LASTEXITCODE -ne 0) { throw "$Islem başarısız (çıkış kodu $LASTEXITCODE)." }
    }
} finally {
    foreach ($Ad in $Adlar) { [Environment]::SetEnvironmentVariable($Ad, $Eski[$Ad], 'Process') }
    Pop-Location
}
