/* RESTARTION frontend v3 — boss spec:
   - kirim instan, thinking indicator ASLI ("thought for Xs" = waktu inferensi beneran)
   - galeri AI: img (videoframe/hulk) + gif (dance to pay le respect)
   - fitur RAHASIA: Ctrl+Alt+M -> popup deepthink (best-of-N, beneran mikir lebih lama)
     GAK DISEBUT di mana-mana di UI. */
const $ = (s) => document.querySelector(s);
const msgs = $("#messages");
let SID = localStorage.getItem("sid") || null;
let DEEPTHINK = false; // rahasia. gak ada tulisan apapun di UI normal.

function scrollDown(){ $("#chat").scrollTop = $("#chat").scrollHeight; }

function mediaCard(name, isGif){
  const card = document.createElement("div");
  card.className = "imgcard" + (isGif ? " gifcard" : "");
  const img = document.createElement("img");
  img.src = "/img/" + encodeURIComponent(name);
  img.loading = "lazy";
  const cap = document.createElement("div");
  cap.className = "imgname";
  if (isGif || name === "dance-dance-to-pay-respect.gif")
    cap.textContent = "🕺 dance to pay le respect 🙏";
  else if (name === "download.jpeg")
    cap.textContent = " Hulk · mode marah";
  else
    cap.textContent = "\uD83D\uDDBC " + name + " · galeri restartion";
  card.append(img, cap);
  return card;
}

function addRow(role, text, imgs, gifs, meta){
  const row = document.createElement("div");
  row.className = "row " + role;
  const av = document.createElement("div");
  av.className = "avatar"; av.textContent = role === "bot" ? "\u27C1" : "\uD83D\uDE0E";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const who = document.createElement("div");
  who.className = "who";
  who.textContent = role === "bot" ? "restartion" : "lu";
  const body = document.createElement("div");
  body.textContent = text;
  bubble.append(who, body);
  if (meta && role === "bot"){
    const think = document.createElement("div");
    think.className = "thinkmeta" + (meta.deep ? " deep" : "");
    think.textContent = (meta.deep ? "\uD83E\uDDE0 deepthink \u00B7 " : "") + "thought for " + meta.secs + "s";
    bubble.append(think);
  }
  (imgs || []).forEach(name => bubble.append(mediaCard(name, false)));
  (gifs || []).forEach(name => bubble.append(mediaCard(name, true)));
  row.append(av, bubble);
  msgs.append(row);
  scrollDown();
  return row;
}

function addTyping(){
  const row = document.createElement("div");
  row.className = "row bot";
  row.innerHTML = `<div class="avatar">\u27C1</div>
    <div class="bubble typing"><span class="thinklabel">mikir</span><i></i><i></i><i></i></div>`;
  msgs.append(row); scrollDown();
  // timer ASLI: detik beneran sejak mulai mikir
  const label = row.querySelector(".thinklabel");
  const t0 = Date.now();
  row._timer = setInterval(() => {
    if (label.isConnected) label.textContent = "mikir... " + ((Date.now() - t0) / 1000).toFixed(1) + "s";
  }, 100);
  return row;
}

async function send(text){
  if(!text) return;
  addRow("user", text, [], []);           // user message LANGSUNG tampil
  const t = addTyping();
  try{
    const fd = new FormData();
    fd.append("text", text);
    if(SID) fd.append("sid", SID);
    if(DEEPTHINK) fd.append("deepthink", "1");
    const r = await fetch("/api/send", {method:"POST", body: fd});
    const d = await r.json();
    if(d.error){ clearInterval(t._timer); t.remove(); addRow("bot", d.error, [], []); return; }
    if(d.sid){ SID = d.sid; localStorage.setItem("sid", SID); }
    clearInterval(t._timer);
    t.remove();
    addRow("bot", d.reply || "...", d.images || [], d.gifs || [],
           {secs: (d.think_secs ?? 0).toFixed ? Number(d.think_secs).toFixed(2) : d.think_secs, deep: !!d.deepthink});
    if(d.facts){ $("#mem-chip").textContent = "\uD83E\uDDE0 mem: " + Object.keys(d.facts).length; }
  }catch(e){
    clearInterval(t._timer);
    t.remove();
    addRow("bot", "bruh servernya mati banh \uD83D\uDE2D coba lagi.", [], []);
  }
  $("#text").value = "";
}

$("#form").addEventListener("submit", (e) => { e.preventDefault(); send($("#text").value.trim()); });
$("#text").focus();

$("#btn-reset").addEventListener("click", async () => {
  await fetch("/api/reset", {method:"POST"});
  localStorage.removeItem("sid"); SID = null;
  msgs.innerHTML = "";
  boot();
});

/* ---------- FITUR RAHASIA (experimental) — gak diumumin di mana mana ----------
   Ctrl+Alt+M -> popup deepthink. mode ini bikin model generate 5 kandidat
   lalu pilih paling bagus (rerank by model confidence) = beneran mikir lebih
   lama, hasil lebih bagus, waktu "thought for" jadi jauh lebih lama. ASLI. */
document.addEventListener("keydown", (e) => {
  if (e.ctrlKey && e.altKey && (e.key === "m" || e.key === "M")){
    e.preventDefault();
    const p = $("#secret-popup");
    p.classList.toggle("open");
  }
});
$("#secret-close").addEventListener("click", () => $("#secret-popup").classList.remove("open"));
$("#secret-toggle").addEventListener("change", (e) => {
  DEEPTHINK = e.target.checked;
  const chip = $("#deep-chip");
  chip.hidden = !DEEPTHINK;
});

function boot(){
  addRow("bot",
    "yo dawg. restartion online. \uD83D\uDD28\n58.7M parameter transformer v2 \u2014 dilatih DARI NOL di 2 core CPU, context 8k, 16 kepala attention, data 2x lipat. gak ada API, gak ada GPT, murni tensor.\ngue bisa: nyapa balik (coba aja 'yo dawg'), roasting, nge-joke, ngapalin lu (beneran), ngirim FRAME dari galeri gue \u2014 tiap gue bales, ada gambar. lu? gak bisa ngirim apa-apa. di sini gue yang pegang kamera \uD83D\uDE0F\ncoba: 'yo dawg', 'roast me dawg', 'gue barusan nonton film', 'my cat died' (RIP, nanti gue dance buat dia \uD83D\uDE4F), atau titip nama lu biar gue inget.", [], []);
}
boot();
