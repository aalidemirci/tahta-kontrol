; Tahta Kontrol sunucusu - Windows kurulum betiği (Inno Setup 6)
; build.ps1 çağırır:  ISCC /DSurum=0.8.0 /DKaynak=...\dist\TahtaKontrol /DCikti=...\dist\cikti
;
; 0.8.0'dan itibaren sunucu bir Windows hizmetidir: "TahtaKontrol", Yerel Hizmet
; (LocalService) hesabı, bilgisayar açılınca oturum açılmadan başlar. Veri
; %ProgramData%\TahtaKontrol klasöründedir. Önceki sürümlerin verisi (oturum açan
; kullanıcının %LOCALAPPDATA%\TahtaKontrol klasörü) kurulumda KOPYALANIR
; (tahta_sunucu/tasima.py); taşınamazsa hizmet başlatılmaz ki yeni sertifika
; üretilip bütün tahtalar kopmasın. Masaüstü kısayolu yalnız durum penceresini açar.

#ifndef Surum
  #define Surum "0.0.0"
#endif
#define HizmetAdi "TahtaKontrol"

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
; Hizmet ve açık pencereler PrepareToInstall'da durdurulur; Yeniden Başlatma Yöneticisi yedek güvencedir.
CloseApplications=yes
RestartApplications=no
WizardStyle=modern
UninstallDisplayName=Tahta Kontrol
UninstallDisplayIcon={app}\TahtaKontrol.exe
; {localappdata} yalnız eski veriyi bulmak için okunur (taşıma "tercih"i); kullanıcı alanına dosya yazılmaz.
UsedUserAreasWarning=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[CustomMessages]
turkish.HizmetBasladi=Sunucu Windows hizmeti olarak çalışıyor: bilgisayar açılınca, kimse oturum açmadan başlar. Masaüstündeki "Tahta Kontrol" kısayolu durum penceresini açar; pencereyi kapatmak sunucuyu durdurmaz.
turkish.HizmetBaslamadi=UYARI: Sunucu hizmeti başlatılamadı. Durum penceresinden "Hizmeti başlat" deneyin. Ayrıntı (yönetici olarak): %1\gunluk\sunucu.log ve Olay Görüntüleyicisi > Windows Günlükleri > Uygulama.
turkish.TasimaTamam=Önceki sürümün verisi ve sunucu sertifikası %1 klasörüne kopyalandı; tahtalar yeniden kurulum yapılmadan bağlanmayı sürdürür. Eski klasör silinmedi, içine TASINDI.txt bırakıldı.
turkish.TasimaYok=Önceki bir kurulumun verisi bulunmadı. Durum penceresinden "Paneli aç" ile ilk kurulumu yapın.
turkish.TasimaHedefDolu=Sunucu %1 klasöründeki mevcut veriyle çalışıyor.
turkish.TasimaBelirsiz=DİKKAT: Önceki sürümün verisi taşınmadı (birden çok eski veri klasörü var ya da daha önce taşınmış eski klasör sonradan yeniden kullanılmış; hangisinin doğru olduğu anlaşılamadı). Sunucu hizmeti, yeni sertifika üretip bütün tahtaları koparmasın diye BAŞLATILMADI. Bulunan klasörler ve çözüm adımları: %1\TASIMA-BEKLIYOR.txt (yönetici olarak açın).
turkish.TasimaHata=DİKKAT: Önceki sürümün verisi kopyalanamadı; yarım kopya silindi, eski veri yerinde duruyor. Sunucu hizmeti, yeni sertifika üretip bütün tahtaları koparmasın diye BAŞLATILMADI. Ayrıntı ve çözüm adımları: %1\TASIMA-BEKLIYOR.txt ve %1\gunluk\tasima.log (yönetici olarak açın).
turkish.AclHata=UYARI: %1 klasörünün izinleri kısıtlanamadı; sıradan kullanıcılar veritabanını okuyabilir. Yönetici komut isteminde: icacls "%1" /inheritance:r /grant:r *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F *S-1-5-19:(OI)(CI)M
turkish.UykuNotu=Bu bilgisayar uykuya ya da hazırda beklemeye geçerse tahtalar çevrimdışı kalır; güç ayarlarında uykuyu kapatın.
turkish.KaldirmaVeri=Sunucu hizmeti kaldırıldı. Veri, sertifika ve yedekler SİLİNMEDİ: %1%n%nProgram yeniden kurulursa aynı veriyle açılır. Bu klasörü silerseniz sertifika da gider ve bütün tahtalara ajan yeniden kurulmalıdır.

[Tasks]
Name: "masaustu"; Description: "Masaüstüne kısayol oluştur (durum penceresi)"

[Dirs]
; Veri klasörü kaldırmada silinmez (veritabanı, sertifika, yedekler).
Name: "{commonappdata}\TahtaKontrol"; Flags: uninsneveruninstall

[InstallDelete]
; 0.8 öncesinin "Windows açılınca başlat" kısayolu: hizmetle birlikte ikinci bir sunucu açmasın.
Type: files; Name: "{commonstartup}\Tahta Kontrol.lnk"

[Files]
Source: "{#Kaynak}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Tahta Kontrol"; Filename: "{app}\TahtaKontrol.exe"
Name: "{autodesktop}\Tahta Kontrol"; Filename: "{app}\TahtaKontrol.exe"; Tasks: masaustu

[Run]
Filename: "{app}\TahtaKontrol.exe"; Description: "Durum penceresini aç"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\net.exe"; Parameters: "stop {#HizmetAdi}"; Flags: runhidden waituntilterminated; RunOnceId: "HizmetDurdur"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM TahtaKontrol.exe"; Flags: runhidden waituntilterminated; RunOnceId: "SurecKapat"
Filename: "{sys}\sc.exe"; Parameters: "delete {#HizmetAdi}"; Flags: runhidden waituntilterminated; RunOnceId: "HizmetSil"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Tahta Kontrol"""; Flags: runhidden; RunOnceId: "GuvenlikDuvari"

[Code]
const
  HIZMET = '{#HizmetAdi}';
  HIZMET_YOK = 1060;
  { tahta_sunucu/tasima.py çıkış kodları }
  TASIMA_TAMAM = 0;
  TASIMA_YOK = 10;
  TASIMA_HEDEF_DOLU = 11;
  TASIMA_BELIRSIZ = 20;

var
  TasimaKodu: Integer;
  HizmetCalisiyor: Boolean;
  AclTamam: Boolean;

function Calistir(const Dosya, Parametre: String): Integer;
var
  Kod: Integer;
begin
  if not Exec(Dosya, Parametre, '', SW_HIDE, ewWaitUntilTerminated, Kod) then
    Kod := -1;
  Log(Format('Calistir: %s %s -> %d', [Dosya, Parametre, Kod]));
  Result := Kod;
end;

function Sistem(const Ad: String): String;
begin
  Result := ExpandConstant('{sys}\') + Ad;
end;

function VeriDizini: String;
begin
  Result := ExpandConstant('{commonappdata}\TahtaKontrol');
end;

function HizmetVar: Boolean;
begin
  Result := Calistir(Sistem('sc.exe'), 'query ' + HIZMET) <> HIZMET_YOK;
end;

function TasimaGuvenli: Boolean;
begin
  Result := (TasimaKodu = TASIMA_TAMAM) or (TasimaKodu = TASIMA_YOK) or (TasimaKodu = TASIMA_HEDEF_DOLU);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  { Yükseltme: hizmet dosyalar değişmeden durdurulur (net stop durana kadar bekler). Çökme döngüsündeki
    hizmeti hizmet yöneticisi 5-30 sn sonra yeniden açmasın diye önce otomatik başlatma ve yeniden
    başlatma eylemleri kapatılır; ikisi de HizmetiKaydet'te geri yazılır. }
  if HizmetVar then
  begin
    Calistir(Sistem('sc.exe'), 'config ' + HIZMET + ' start= demand');
    Calistir(Sistem('sc.exe'), 'failure ' + HIZMET + ' reset= 0 actions= ""');
    Calistir(Sistem('net.exe'), 'stop ' + HIZMET);
  end;
  { 0.8 öncesi oturum programı (başlangıç kısayoluyla her oturum açan kullanıcıda açılmış
    olabilir) ve durum pencereleri kapatılır. SQLite işlenmiş kayıtları diske yazmıştır;
    -wal dosyası taşımada kopyalanır. }
  Calistir(Sistem('taskkill.exe'), '/F /T /IM TahtaKontrol.exe');
  Sleep(1500);
end;

procedure HizmetiKaydet;
var
  Ikili, Ortak: String;
begin
  Ikili := '"\"' + ExpandConstant('{app}\TahtaKontrol.exe') + '\" hizmet"';
  Ortak := ' binPath= ' + Ikili + ' start= auto obj= "NT AUTHORITY\LocalService" password= ""'
    + ' DisplayName= "Tahta Kontrol Sunucusu"';
  if HizmetVar then
    Calistir(Sistem('sc.exe'), 'config ' + HIZMET + Ortak)
  else
    Calistir(Sistem('sc.exe'), 'create ' + HIZMET + Ortak);
  Calistir(Sistem('sc.exe'), 'description ' + HIZMET
    + ' "Okul ağındaki etkileşimli tahtaların kontrol sunucusu. Veri: ' + VeriDizini + '"');
  { Çökerse 5 sn sonra yeniden başlat; geri yüklemedeki bilinçli çıkış (75) da böyle döner. }
  Calistir(Sistem('sc.exe'), 'failure ' + HIZMET + ' reset= 86400 actions= restart/5000/restart/5000/restart/30000');
  Calistir(Sistem('sc.exe'), 'failureflag ' + HIZMET + ' 1');
end;

procedure GuvenlikDuvari;
begin
  { Tahtalar ve diğer idari bilgisayarlar sunucuya 8788 numaralı kapıdan bağlanır. }
  Calistir(Sistem('netsh.exe'), 'advfirewall firewall delete rule name="Tahta Kontrol"');
  Calistir(Sistem('netsh.exe'), 'advfirewall firewall add rule name="Tahta Kontrol" dir=in action=allow'
    + ' protocol=TCP localport=8788 profile=private,domain,public');
end;

procedure KurulumSonrasi;
var
  Veri, Bekliyor: String;
begin
  Veri := VeriDizini;
  ForceDirectories(Veri);
  { 1. İzinler: yalnız SYSTEM, Administrators (tam) ve LocalService (değiştirme). Devralma
       kesilir; ProgramData'nın varsayılanı Users'a okuma verir. Adlar yerelleştiği için SID. }
  AclTamam := Calistir(Sistem('icacls.exe'), '"' + Veri + '" /inheritance:r /grant:r'
    + ' *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F *S-1-5-19:(OI)(CI)M') = 0;
  { 2. Eski veriyi kopyala (yönetici yetkisiyle; hizmet hesabı kullanıcı profillerini okuyamaz). }
  TasimaKodu := Calistir(ExpandConstant('{app}\TahtaKontrol.exe'), 'tasi --hedef "' + Veri + '" --tercih "'
    + ExpandConstant('{localappdata}\TahtaKontrol') + '"');
  { 3. Kopyalanan dosyalar klasörün izinlerini devralsın. }
  Calistir(Sistem('icacls.exe'), '"' + Veri + '\*" /reset /T /C /Q');
  { Taşıma programı hiç çalışamadıysa da hizmet yeni sertifika üretmesin. }
  Bekliyor := Veri + '\TASIMA-BEKLIYOR.txt';
  if (not TasimaGuvenli) and (TasimaKodu <> TASIMA_BELIRSIZ) and (not FileExists(Bekliyor)) then
    SaveStringToFile(Bekliyor, 'Tahta Kontrol: veri tasima programi calismadi (kod '
      + IntToStr(TasimaKodu) + '). Eski veri yerinde. Ayrinti: gunluk\tasima.log' + #13#10, False);
  { 4. Hizmet ve güvenlik duvarı. }
  HizmetiKaydet;
  GuvenlikDuvari;
  { 5. Taşıma güvenle bittiyse başlat. }
  HizmetCalisiyor := False;
  if TasimaGuvenli then
    HizmetCalisiyor := Calistir(Sistem('net.exe'), 'start ' + HIZMET) = 0;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    KurulumSonrasi;
end;

function Ozet: String;
var
  Veri: String;
begin
  Veri := VeriDizini;
  case TasimaKodu of
    TASIMA_TAMAM: Result := FmtMessage(CustomMessage('TasimaTamam'), [Veri]);
    TASIMA_YOK: Result := CustomMessage('TasimaYok');
    TASIMA_HEDEF_DOLU: Result := FmtMessage(CustomMessage('TasimaHedefDolu'), [Veri]);
    TASIMA_BELIRSIZ: Result := FmtMessage(CustomMessage('TasimaBelirsiz'), [Veri]);
  else
    Result := FmtMessage(CustomMessage('TasimaHata'), [Veri]);
  end;
  if HizmetCalisiyor then
    Result := CustomMessage('HizmetBasladi') + #13#10#13#10 + Result + #13#10#13#10 + CustomMessage('UykuNotu')
  else if TasimaGuvenli then
    Result := Result + #13#10#13#10 + FmtMessage(CustomMessage('HizmetBaslamadi'), [Veri]);
  if not AclTamam then
    Result := Result + #13#10#13#10 + FmtMessage(CustomMessage('AclHata'), [Veri]);
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Metin: String;
begin
  if CurPageID = wpFinished then
  begin
    Metin := Ozet;
    WizardForm.FinishedLabel.Caption := Metin;
    { Uzun metin "Durum penceresini aç" kutusunun üstüne binmesin. }
    WizardForm.RunList.Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(12);
    Log('Kurulum özeti: ' + Metin);
    if (not TasimaGuvenli) and (not WizardSilent) then
      MsgBox(Metin, mbCriticalError, MB_OK);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    MsgBox(FmtMessage(CustomMessage('KaldirmaVeri'), [VeriDizini]), mbInformation, MB_OK);
end;
