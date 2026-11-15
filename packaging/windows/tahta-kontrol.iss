; Tahta Kontrol sunucusu - Windows kurulum betiği (Inno Setup 6)
; build.ps1 çağırır:  ISCC /DSurum=0.1.0 /DKaynak=...\dist\TahtaKontrol /DCikti=...\dist\cikti

#ifndef Surum
  #define Surum "0.0.0"
#endif

[Setup]
AppId={{6E0B7C1E-3B4D-4E7B-9E0A-7A1D5B0C2F41}
AppName=Tahta Kontrol
AppVersion={#Surum}
AppPublisher=okulapp.org
DefaultDirName={autopf}\Tahta Kontrol
DefaultGroupName=Tahta Kontrol
DisableProgramGroupPage=yes
OutputDir={#Cikti}
OutputBaseFilename=tahta-kontrol-{#Surum}-windows-kurulum
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
WizardStyle=modern
UninstallDisplayName=Tahta Kontrol

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "masaustu"; Description: "Masaüstüne kısayol oluştur"
Name: "baslangic"; Description: "Windows açılınca Tahta Kontrol sunucusunu başlat (önerilir)"

[Files]
Source: "{#Kaynak}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Tahta Kontrol"; Filename: "{app}\TahtaKontrol.exe"
Name: "{autodesktop}\Tahta Kontrol"; Filename: "{app}\TahtaKontrol.exe"; Tasks: masaustu
Name: "{commonstartup}\Tahta Kontrol"; Filename: "{app}\TahtaKontrol.exe"; Tasks: baslangic

[Run]
; Tahtalar ve diğer idari bilgisayarlar sunucuya 8788 numaralı kapıdan bağlanır.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Tahta Kontrol"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Tahta Kontrol"" dir=in action=allow protocol=TCP localport=8788 profile=private,domain,public"; Flags: runhidden
Filename: "{app}\TahtaKontrol.exe"; Description: "Tahta Kontrol'ü başlat"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Tahta Kontrol"""; Flags: runhidden; RunOnceId: "GuvenlikDuvari"
