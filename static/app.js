/* RESTARTION frontend — boss spec v2: user gak bisa kirim gambar. AI yang punya galeri. */
const $ = (s) => document.querySelector(s);
const msgs = $("#messages");
let SID = localStorage.getItem("sid") || null;

function scrollDown(){ $("#chat").scrollTop = $("#chat").scrollHeight; }

function addRow(role, text, imgs){
  const row = document.createElement("div");
  row.className = "row " + role;
  const av = document.createElement("div");
  av.className = "avatar"; av.textContent = role === "bot" ? "⟁" : "😎";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const who = document.createElement("div");
  who.className = "who";
  who.textContent = role === "bot" ? "restartion" : "lu";
  const body = document.createElement("div");
  body.textContent = text;
  bubble.append(who, body);
  (imgs || []).forEach(name => {
    const card = document.createElement("div");
    card.className = "imgcard";
    const img = document.createElement("img");
    img.src = "/img/" + encodeURIComponent(name);
    img.loading = "lazy";
    const cap = document.createElement("div");
    cap.className = "imgname";
    cap.textContent = "🖼 " + name + (name === "download.jpeg" ? " · mode marah" : "");
    card.append(img, cap);
    bubble.append(card);
  });
  row.append(av, bubble);
  msgs.append(row);
  scrollDown();
  return row;
}

function addTyping(){
  const row = document.createElement("div");
  row.className = "row bot";
  row.innerHTML = `<div class="avatar">⟁</div>
    <div class="bubble typing"><i></i><i></i><i></i></div>`;
  msgs.append(row); scrollDown();
  return row;
}

async function send(text){
  if(!text) return;
  addRow("user", text, []);
  const t = addTyping();
  try{
    const fd = new FormData();
    fd.append("text", text);
    if(SID) fd.append("sid", SID);
    const r = await fetch("/api/send", {method:"POST", body: fd});
    const d = await r.json();
    if(d.error){ t.remove(); addRow("bot", d.error, []); return; }
    if(d.sid){ SID = d.sid; localStorage.setItem("sid", SID); }
    t.remove();
    addRow("bot", d.reply || "...", d.images || []);
    if(d.facts){ $("#mem-chip").textContent = "🧠 mem: " + Object.keys(d.facts).length; }
  }catch(e){
    t.remove();
    addRow("bot", "bruh servernya mati banh 😭 coba lagi.", []);
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

function boot(){
  addRow("bot",
    "yo. restartion online. 🔩\n57.44M parameter transformer, dilatih DARI NOL di 2 core CPU. gak ada API, gak ada GPT, murniTensor.\ngue bisa: roasting, nge-joke, nginget hal yang lu bilang (beneran, bukan bohong), dan KIRIM FOTO dari galeri gue kalau konteksnya masuk akal — dan jangan harap lu bisa kirim gambar, di sini gue yang pegang kamera 😌 nyerang balik pakai si ijo kalau lu jahat.\ncoba: 'yo', 'roast me', 'gue barusan nonton film', 'tell me a joke', 'my cat died' ( RIP, nanti gue dance buat dia 🙏), atau titip nama lu biar gue inget.", []);
}
boot();
