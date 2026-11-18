// Panel sayfalarının tam sayfa ekran görüntüsünü ve yerleşim ölçümlerini alır (0.15.0, kabuk).
// Başsız Edge/Chrome + Chrome DevTools Protocol; Node 22+'nın yerleşik fetch ve WebSocket'i, bağımlılık yok.
// YALNIZ deneme sunucusuna (uydurma veri) karşı çalıştırılır; çıktı depo DIŞINA yazılır (görüntüler depoya girmez).
//
// Ortam değişkenleri (betikte adres, kullanıcı, parola, yol YOKTUR):
//   PANEL_ADRES      deneme sunucusunun kökü (zorunlu)
//   PANEL_KULLANICI  PANEL_PAROLA   deneme hesabı (zorunlu; PANEL_CEREZ dosyasında geçerli çerez varsa kullanılmaz)
//   PANEL_CIKTI      çıktı klasörü (zorunlu; depo dışı)
//   PANEL_CEREZ      oturum çerezinin saklanacağı dosya (isteğe bağlı; giriş hız sınırına takılmamak için)
//   PANEL_TARAYICI   tarayıcı yolu (isteğe bağlı; varsayılan Edge'in olağan kurulum yeri)
// Kullanım: node scripts/panel_olcum.mjs <genişlik> <acik|koyu> [ad-süzgeci] [--boy=768] [--ilk] [--gorsuz]
//           [--zorlanmis] [--ek=-ad] [--yol=/adres] [--oturumsuz]
//   --ilk       yalnız ilk ekranın görüntüsü          --gorsuz   görüntü alma, yalnız ölç
//   --zorlanmis forced-colors: active öykünmesi       --yol=     listedeki sayfalar yerine tek adres ("ozel" adıyla)
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const ort = process.env;
const KOK = (ort.PANEL_ADRES || "").replace(/\/$/, "");
const CIKTI = ort.PANEL_CIKTI || "";
if (!KOK || !CIKTI) {
  console.error("PANEL_ADRES ve PANEL_CIKTI ortam değişkenleri gerekli (dosya başındaki açıklamaya bakın).");
  process.exit(2);
}
const TARAYICI = ort.PANEL_TARAYICI || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const arg = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const bayrak = (ad) => process.argv.includes("--" + ad);
const deger = (ad) => (process.argv.find((a) => a.startsWith(`--${ad}=`)) || "").split("=").slice(1).join("=");
const GEN = Number(arg[0] || 1366);
const TEMA = arg[1] === "koyu" ? "koyu" : "acik";
const SUZ = arg[2] || "";
const BOY = Number(deger("boy")) || (GEN < 600 ? 844 : 768);
mkdirSync(CIKTI, { recursive: true });

// Şube defterinin gün görünümü (fırça şeridi) bugünün tarihiyle açılır.
const BUGUN = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
export const SAYFALAR = [
  ["pano", "/"], ["tahta-ayrinti", "/tahta/1"], ["tahta-onay-bekleyen", "/tahta/13"], ["tahta-ekle", "/ekle"],
  ["gruplar", "/gruplar"], ["tahtalar-ice-aktar", "/tahtalar/ice-aktar"], ["duyurular", "/duyurular"],
  ["duyuru-yeni", "/duyurular/yeni"], ["program-zil", "/program?bolum=zil"], ["program-derslik", "/program?bolum=derslik"],
  ["program-kurallar", "/program?bolum=kurallar"], ["program-istisnalar", "/program?bolum=istisnalar"],
  ["program-uyarilar", "/program/uyarilar"], ["program-aktar", "/program/aktar"], ["program-gecmis", "/program/gecmis"],
  ["program-gun", "/program/gun"], ["program-cizelge", "/program/cizelge/1"], ["sinavlar", "/sinavlar"],
  ["sinav-ayrinti", "/sinav/1"], ["yoklama-gunluk", "/yoklama"], ["yoklama-sube-defteri", "/yoklama/sube?sube=9/A"],
  ["yoklama-sube-gun", "/yoklama/sube?sube=9/A&tarih=" + BUGUN],
  ["yoklama-son-gunler", "/yoklama/son-gunler"], ["yoklama-mazeret", "/yoklama/mazeret"], ["yoklama-gir", "/yoklama/gir"],
  ["yoklama-icmal", "/yoklama/icmal"], ["ogretmenler", "/ogretmenler"], ["ogrenciler", "/ogrenciler"],
  ["usb-anahtarlar", "/usb-anahtarlar"], ["ogretmen-programi", "/ogretmen-programi"], ["arizalar", "/arizalar"],
  ["ariza-ayrinti", "/ariza/1"], ["envanter", "/envanter"], ["yedekler", "/yedekler"], ["islem-kaydi", "/kayit"],
  ["kullanicilar", "/kullanicilar"], ["ayarlar", "/ayarlar"], ["acil", "/acil"], ["giris", "/giris"],
];

// Sayfanın içinde çalışan ölçüm (yalnız okur).
const OLCUM = `(() => {
  const GENISLIK = ${GEN};
  const g = (s) => [...document.querySelectorAll(s)];
  const kutu = (e) => e.getBoundingClientRect();
  const gorunur = (e) => { const r = kutu(e); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden"; };
  const ad = (e) => e.tagName.toLowerCase() + (e.id ? "#" + e.id : "") + (e.classList.length ? "." + e.classList[0] : "");
  const KABUK = ".yan-menu, .ust-cubuk, .alt-cubuk";
  // Kendi kaydırma kutusunun içinde kalan öğe (tablo kabı, sekme şeridi, pre…) taşma sayılmaz: kutu onu kırpar.
  const kirpilir = (e) => { for (let k = e.parentElement; k && k !== document.body; k = k.parentElement) {
    if (getComputedStyle(k).overflowX !== "visible") return true; } return false; };
  const tasan = g("body *").filter((e) => gorunur(e) && kutu(e).right > innerWidth + 1)
    .filter((e) => !e.closest(".gizli, dialog") && !kirpilir(e)).map(ad);
  const cnv = document.createElement("canvas"); cnv.width = cnv.height = 1;
  const cv = cnv.getContext("2d", { willReadFrequently: true });
  const coz = (s) => { if (!s || s === "transparent" || s === "rgba(0, 0, 0, 0)") return { r: 0, g: 0, b: 0, a: 0 };
    cv.clearRect(0, 0, 1, 1); cv.fillStyle = s; cv.fillRect(0, 0, 1, 1); const d = cv.getImageData(0, 0, 1, 1).data;
    return { r: d[0], g: d[1], b: d[2], a: d[3] / 255 }; };
  const lum = (c) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const zemin = (e) => { const k = [];
    for (let x = e; x; x = x.parentElement) { const b = coz(getComputedStyle(x).backgroundColor); if (b.a > 0) { k.push(b); if (b.a >= 1) break; } }
    let s = { r: 255, g: 255, b: 255 };
    for (const q of k.reverse()) s = { r: q.r * q.a + s.r * (1 - q.a), g: q.g * q.a + s.g * (1 - q.a), b: q.b * q.a + s.b * (1 - q.a) };
    return s; };
  const oran = (e) => { const o = coz(getComputedStyle(e).color); if (o.a === 0) return 21; const z = zemin(e);
    const on = { r: o.r * o.a + z.r * (1 - o.a), g: o.g * o.a + z.g * (1 - o.a), b: o.b * o.a + z.b * (1 - o.a) };
    const a = lum(on), b = lum(z); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05); };
  const metinli = g("body *").filter((e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) && gorunur(e)
    && !e.closest(".gizli, [hidden], [aria-hidden=true], .tahta-onizleme, script, option, dialog:not([open])")
    && !e.disabled && !e.closest("button:disabled") && getComputedStyle(e).opacity === "1");
  const dusuk = metinli.map((e) => { const cs = getComputedStyle(e); const px = parseFloat(cs.fontSize);
    const buyuk = px >= 24 || (px >= 18.66 && +cs.fontWeight >= 700); return { e, o: oran(e), px, esik: buyuk ? 3 : 4.5 }; })
    .filter((x) => x.o < x.esik);
  const yaz = (x) => ad(x.e) + " '" + x.e.textContent.trim().slice(0, 20) + "' " + x.o.toFixed(2);
  const kucuk = metinli.filter((e) => parseFloat(getComputedStyle(e).fontSize) < 12);
  const esik = innerWidth < 1024 ? 44 : 36;
  const hedefler = g("button, a.dugme, summary.dugme, .sekmeler a, .yan-menu a, .ust-cubuk a, .alt-cubuk a").filter(gorunur)
    .filter((e) => !e.closest(".firca-sec, .defter, dialog:not([open])"));
  const kucukHedef = hedefler.filter((e) => kutu(e).height < esik - .5);
  const ilk = [...(document.querySelector("main") || document.body).children].find(gorunur);
  const cikis = document.querySelector(".yan-cikis");
  const kap = document.querySelector(".defter-kap.sigar");
  const alt = document.querySelector(".alt-cubuk");
  const ust = document.querySelector(".ust-cubuk");
  // Kendi kabında yana kayan tablolar: "kaydırılan en / görünen en" (görüş dışında sütun var demektir).
  const kayanTablo = g(".tablo-kap").filter((e) => gorunur(e) && e.scrollWidth > e.clientWidth + 1).map((e) => e.scrollWidth + "/" + e.clientWidth);
  return {
    baslik: (document.querySelector("main h1") || {}).textContent?.trim().replace(/\\s+/g, " ") || "",
    kip: getComputedStyle(document.body).getPropertyValue("--kb-kip").trim() || "yok",
    yukseklik: document.documentElement.scrollHeight,
    // Telefon öykünmesinde taşan sayfa görüntü alanını büyütür (innerWidth > istenen genişlik): o da taşmadır.
    yatay_tasma: document.documentElement.scrollWidth > innerWidth || innerWidth > GENISLIK,
    sayfa_eni: Math.max(document.documentElement.scrollWidth, innerWidth),
    tasan_oge: [...new Set(tasan)].slice(0, 6),
    icerik_y: ilk ? Math.round(kutu(ilk).top + scrollY) : null,
    kontrast_kabuk: dusuk.filter((x) => x.e.closest(KABUK)).map(yaz).slice(0, 8),
    kontrast_icerik: dusuk.filter((x) => !x.e.closest(KABUK)).length,
    kontrast_icerik_ornek: [...new Set(dusuk.filter((x) => !x.e.closest(KABUK)).map(yaz))].slice(0, 8),
    kucuk_yazi_kabuk: kucuk.filter((e) => e.closest(KABUK)).map(ad).slice(0, 5),
    kucuk_yazi_icerik: [...new Set(kucuk.filter((e) => !e.closest(KABUK)).map((e) => ad(e) + " " + getComputedStyle(e).fontSize))].slice(0, 6),
    kucuk_hedef: kucukHedef.length,
    kucuk_hedef_ornek: [...new Set(kucukHedef.map((e) => ad(e) + " " + Math.round(kutu(e).height)))].slice(0, 8),
    cikis_gorunur: cikis && gorunur(cikis) ? kutu(cikis).bottom <= innerHeight + 1 : null,
    alt_cubuk: !!alt && gorunur(alt),
    alt_cubuk_eni: alt && gorunur(alt) ? Math.round(kutu(alt).width) : null,
    ust_cubuk_yapiskan: ust && gorunur(ust) ? getComputedStyle(ust).position === "sticky" : null,
    kayan_tablo: kayanTablo,
    defter_sigar: kap ? kap.scrollWidth <= kap.clientWidth : null,
  };
})()`;

const bekle = (ms) => new Promise((r) => setTimeout(r, ms));

async function girisYap() {
  const y = await fetch(KOK + "/giris", {
    method: "POST", redirect: "manual",
    headers: { "Content-Type": "application/x-www-form-urlencoded", Origin: KOK },
    body: new URLSearchParams({ ad: ort.PANEL_KULLANICI || "", parola: ort.PANEL_PAROLA || "" }),
  });
  const c = (y.headers.getSetCookie() || []).find((s) => s.startsWith("tk_oturum="));
  if (!c) throw new Error("giriş başarısız: " + y.status);
  return c.split(";")[0].split("=")[1];
}

async function cerezAl() {
  const dosya = ort.PANEL_CEREZ || "";
  let cerez = dosya && existsSync(dosya) ? readFileSync(dosya, "utf8").trim() : "";
  if (cerez) {
    const s = await fetch(KOK + "/", { redirect: "manual", headers: { Cookie: "tk_oturum=" + cerez } });
    if (s.status !== 200) cerez = "";
  }
  if (!cerez) { cerez = await girisYap(); if (dosya) writeFileSync(dosya, cerez); }
  return cerez;
}

async function main() {
  const cerez = bayrak("oturumsuz") ? "" : await cerezAl();
  const kapi = 9361 + Math.floor(Math.random() * 200);
  const tarayici = spawn(TARAYICI, ["--headless=new", "--disable-gpu", "--hide-scrollbars", `--remote-debugging-port=${kapi}`,
    `--user-data-dir=${join(tmpdir(), "panel-olcum-profil-" + process.pid + "-" + Date.now())}`, "--no-first-run", "--no-default-browser-check", "about:blank"],
  { stdio: "ignore" });
  let hedef;
  for (let i = 0; i < 60 && !hedef; i++) {
    await bekle(250);
    try { hedef = (await (await fetch(`http://127.0.0.1:${kapi}/json/list`)).json()).find((t) => t.type === "page"); } catch { /* açılıyor */ }
  }
  const ws = new WebSocket(hedef.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  let no = 0; const bekleyen = new Map(); const olaylar = [];
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.id && bekleyen.has(m.id)) { bekleyen.get(m.id)(m); bekleyen.delete(m.id); } else if (m.method) olaylar.push(m);
  });
  const cdp = (method, params = {}) => new Promise((r) => { const id = ++no; bekleyen.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
  const olcu = (boy) => cdp("Emulation.setDeviceMetricsOverride", { width: GEN, height: boy, deviceScaleFactor: 1, mobile: GEN < 600 });
  await cdp("Page.enable"); await cdp("Network.enable"); await cdp("Runtime.enable");
  // Statik dosyalar sürümlü adresle uzun önbelleğe alınır; sürüm yükseltilmeden ölçülen değişiklik eski stille görünmesin.
  await cdp("Network.setCacheDisabled", { cacheDisabled: true });
  if (cerez) await cdp("Network.setCookie", { name: "tk_oturum", value: cerez, url: KOK, httpOnly: true });
  await olcu(BOY);
  const ozellikler = [{ name: "prefers-color-scheme", value: TEMA === "koyu" ? "dark" : "light" }];
  if (bayrak("zorlanmis")) ozellikler.push({ name: "forced-colors", value: "active" });
  await cdp("Emulation.setEmulatedMedia", { features: ozellikler });

  const liste = deger("yol") ? [["ozel", deger("yol")]] : SAYFALAR.filter(([ad]) => !SUZ || ad.includes(SUZ));
  const sonuc = {};
  for (const [ad, yol] of liste) {
    if (ad === "giris") await cdp("Network.deleteCookies", { name: "tk_oturum", url: KOK });
    olaylar.length = 0;
    await cdp("Page.navigate", { url: KOK + yol });
    for (let i = 0; i < 80 && !olaylar.some((o) => o.method === "Page.loadEventFired"); i++) await bekle(100);
    await bekle(1200); // panel.js'in ilk durum turu
    const o = (await cdp("Runtime.evaluate", { expression: OLCUM, returnByValue: true })).result?.result?.value || {};
    o.yol = yol;
    o.hatalar = olaylar.filter((x) => x.method === "Runtime.exceptionThrown")
      .map((x) => x.params.exceptionDetails.exception?.description || x.params.exceptionDetails.text);
    if (!bayrak("gorsuz")) {
      // Tam sayfada sabit ve yapışkan öğeler doğal yerinde dursun diye görüntü alanı sayfa boyuna uzatılır.
      const yuk = bayrak("ilk") ? BOY : Math.min(Math.max(o.yukseklik || BOY, BOY), 16000);
      if (yuk > BOY) { await olcu(yuk); await bekle(300); }
      const g = await cdp("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: GEN, height: yuk, scale: 1 } });
      if (yuk > BOY) await olcu(BOY);
      writeFileSync(join(CIKTI, `${GEN}${deger("boy") ? "x" + BOY : ""}-${TEMA}-${ad}${deger("ek")}.png`), Buffer.from(g.result.data, "base64"));
    }
    sonuc[ad] = o;
    const sorun = [o.yatay_tasma ? "YATAY TAŞMA" : "", o.tasan_oge?.length ? "taşan: " + o.tasan_oge.join(" ") : "",
      o.kontrast_kabuk?.length ? "kabuk kontrastı: " + o.kontrast_kabuk.join(" | ") : "",
      o.kucuk_yazi_kabuk?.length ? "kabukta küçük yazı" : "", o.kayan_tablo?.length ? "kayan tablo: " + o.kayan_tablo.join(" ") : "",
      o.ust_cubuk_yapiskan === false ? "ÜST ÇUBUK YAPIŞKAN DEĞİL" : "", o.alt_cubuk_eni > GEN ? "ALT ÇUBUK TAŞTI " + o.alt_cubuk_eni : "",
      o.hatalar.length ? "JS HATASI: " + o.hatalar[0] : ""].filter(Boolean);
    console.log(ad.padEnd(22), o.kip, "y=" + o.icerik_y, "kontrast=" + o.kontrast_icerik, "hedef=" + o.kucuk_hedef, sorun.join(" ; "));
  }
  writeFileSync(join(CIKTI, `olcum-${GEN}${deger("boy") ? "x" + BOY : ""}-${TEMA}${SUZ ? "-" + SUZ : ""}${deger("ek")}.json`), JSON.stringify(sonuc, null, 1));
  ws.close(); tarayici.kill();
}
main().catch((h) => { console.error(h); process.exit(1); });
