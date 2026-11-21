# Tahta Kontrol - Windows kurulum paketi
#   testler -> PyInstaller -> duman testi (paketlenmiş sunucu açılıyor ve ajan paketi veriyor mu) -> Inno Setup
# Kullanım (depo kökünden):
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
# Çıktı: dist\cikti\tahta-kontrol-<sürüm>-windows-kurulum.exe
# Windows PowerShell 5.1 ile çalışır (&&, ternary yok).

$ErrorActionPreference = 'Stop'
$Kok = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $Kok
$Surum = (Get-Content (Join-Path $Kok 'VERSION') -Raw).Trim()
$Dist = Join-Path $Kok 'dist'
$Build = Join-Path $Kok 'build'
$PyInstaller = 'pyinstaller==6.11.1'

function Adim([string]$Metin) { Write-Host "== $Metin" }
function Calistir([string]$Ad, [scriptblock]$Is) {
    $onceki = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Is
    $kod = $LASTEXITCODE
    $ErrorActionPreference = $onceki
    if ($kod -ne 0) { throw "$Ad başarısız (çıkış kodu $kod)." }
}

Adim "Tahta Kontrol $Surum Windows paketi"
New-Item -ItemType Directory -Force (Join-Path $Dist 'cikti') | Out-Null

Adim 'testler'
Calistir 'Testler' { uv run pytest -q }

Adim 'PyInstaller'
Calistir 'PyInstaller' {
    uv run --with $PyInstaller pyinstaller --noconfirm --clean `
        --distpath $Dist --workpath (Join-Path $Build 'pyinstaller') packaging\windows\tahta-kontrol.spec
}
$Exe = Join-Path $Dist 'TahtaKontrol\TahtaKontrol.exe'

# Kapılar Windows'un ayırdığı 8789-9188 aralığının dışında (netsh int ipv4 show excludedportrange).
Adim 'duman testi (geçici veri dizini, 18797/18798 kapıları)'
$Gecici = Join-Path $Build 'duman-veri'
if (Test-Path $Gecici) { Remove-Item -Recurse -Force $Gecici }
New-Item -ItemType Directory -Force $Gecici | Out-Null
$env:TAHTA_VERI_DIZINI = $Gecici
$env:TAHTA_HTTP_PORT = '18797'
$env:TAHTA_HTTPS_PORT = '18798'
$Surec = Start-Process -FilePath $Exe -ArgumentList 'sunucu' -PassThru -WindowStyle Hidden
try {
    $hazir = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $yanit = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18797/saglik' -TimeoutSec 2
            if ($yanit.StatusCode -eq 200) { $hazir = $true; break }
        } catch { }
    }
    if (-not $hazir) { throw 'Paketlenmiş sunucu 30 saniyede açılmadı.' }
    $kurulum = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18797/kurulum' -TimeoutSec 5
    if ($kurulum.Content -notmatch 'İlk kurulum') { throw 'Kurulum sayfası beklenen içeriği vermedi.' }
    $stil = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18797/statik/stil.css' -TimeoutSec 5
    if ($stil.StatusCode -ne 200) { throw 'Statik dosyalar sunulmuyor.' }
    $paket = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18797/kur/paket' -TimeoutSec 10
    if ($paket.RawContentLength -lt 5000) { throw 'Ajan paketi üretilemedi.' }
    $betik = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18797/kur' -TimeoutSec 5
    $betikMetni = $betik.Content
    if ($betikMetni -is [byte[]]) { $betikMetni = [Text.Encoding]::UTF8.GetString($betikMetni) }
    if ($betikMetni -notmatch 'PAKET_SHA256') { throw 'Kurulum betiği üretilemedi.' }
    foreach ($dosya in 'tahta-kontrol.db', 'sunucu-sertifika.pem', 'sunucu-anahtar.pem') {
        if (-not (Test-Path (Join-Path $Gecici $dosya))) { throw "Veri dizininde $dosya oluşmadı." }
    }
    $durum = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18797/yerel/durum' -TimeoutSec 5
    if ($durum.Content -notmatch '"hizmet"') { throw '/yerel/durum beklenen içeriği vermedi.' }
    Write-Host 'Duman testi geçti.'
} finally {
    if (-not $Surec.HasExited) { Stop-Process -Id $Surec.Id -Force; $Surec.WaitForExit(10000) | Out-Null }
    Remove-Item Env:TAHTA_VERI_DIZINI, Env:TAHTA_HTTP_PORT, Env:TAHTA_HTTPS_PORT -ErrorAction SilentlyContinue
}

function Exe-Kodu([string[]]$Bagimsiz, [int]$Sn) {
    # Pencereli exe: işlenmemiş hata iletişim kutusu açarsa bekleme süresi dolar ve derleme durur.
    $s = Start-Process -FilePath $Exe -ArgumentList $Bagimsiz -PassThru -WindowStyle Hidden
    if (-not $s.WaitForExit($Sn * 1000)) {
        Stop-Process -Id $s.Id -Force
        throw "TahtaKontrol.exe $($Bagimsiz -join ' ') $Sn saniyede bitmedi (hata penceresi açılmış olabilir)."
    }
    return $s.ExitCode
}

Adim 'duman testi: hizmet kabuğu ve veri taşıma (kurulu hizmete dokunmaz)'
# Hizmet yöneticisi dışından başlatılan hizmet 2 koduyla çıkmalı (pywin32 pakete girmiş demektir).
$kod = Exe-Kodu @('hizmet') 20
if ($kod -ne 2) { throw "Hizmet kabuğu beklenmeyen kodla çıktı: $kod (beklenen 2)." }
# Taşıma: duman testinin veri dizini geçici bir hedefe kopyalanır; ikinci çalıştırma "hedef dolu" (11) der.
$TasimaHedef = Join-Path $Build 'duman-tasima'
if (Test-Path $TasimaHedef) { Remove-Item -Recurse -Force $TasimaHedef }
$kod = Exe-Kodu @('tasi', '--hedef', "`"$TasimaHedef`"", '--kaynak', "`"$Gecici`"") 60
if ($kod -ne 0) { throw "Veri taşıma başarısız (kod $kod)." }
foreach ($dosya in 'tahta-kontrol.db', 'sunucu-sertifika.pem', 'sunucu-anahtar.pem') {
    if (-not (Test-Path (Join-Path $TasimaHedef $dosya))) { throw "Taşımada $dosya kopyalanmadı." }
}
if (-not (Test-Path (Join-Path $Gecici 'TASINDI.txt'))) { throw 'Taşıma kaynağa TASINDI.txt bırakmadı.' }
$kod = Exe-Kodu @('tasi', '--hedef', "`"$TasimaHedef`"", '--kaynak', "`"$Gecici`"") 60
if ($kod -ne 11) { throw "Dolu hedefe taşıma 11 yerine $kod döndü." }
Write-Host 'Hizmet kabuğu ve taşıma duman testi geçti.'

Adim 'Inno Setup'
$Iscc = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe'
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) { throw 'Inno Setup 6 (ISCC.exe) bulunamadı.' }
Calistir 'Inno Setup' {
    & $Iscc "/DSurum=$Surum" "/DKaynak=$(Join-Path $Dist 'TahtaKontrol')" "/DCikti=$(Join-Path $Dist 'cikti')" `
        /Qp packaging\windows\tahta-kontrol.iss
}
$Kurulum = Join-Path $Dist "cikti\tahta-kontrol-$Surum-windows-kurulum.exe"
if (-not (Test-Path $Kurulum)) { throw 'Kurulum dosyası oluşmadı.' }
$Ozet = (Get-FileHash $Kurulum -Algorithm SHA256).Hash.ToLower()
Write-Host "Hazır: $Kurulum"
Write-Host "Boyut: $([math]::Round((Get-Item $Kurulum).Length / 1MB, 1)) MB · sha256 $Ozet"
