/* ============================================================
   RESTARTION app.js — 100% client-side inference
   - ByteLevel BPE tokenizer (from scratch, dari tokenizer.json kita)
   - ONNX Runtime Web (wasm, int8 63MB) — model transformer dari nol
   - Engine port: memori asli (localStorage), galeri AI (videoframe/hulk),
     leak guard, grief fallback, insult streak, name grounding.
   BOSS SPEC v2: user gak bisa kirim gambar. AI yang punya galeri.
   ============================================================ */

/* ---------- 1. GPT-2 style byte <-> unicode ---------- */
const BYTES_TO_UNI = (() => {
  const bs = [];
  for (let b = 33; b < 127; b++) bs.push(b);
  for (let b = 161; b < 173; b++) bs.push(b);
  for (let b = 174; b < 256; b++) bs.push(b);
  const cs = bs.slice();
  let n = 0;
  for (let b = 0; b < 256; b++) if (!bs.includes(b)) { bs.push(b); cs.push(256 + n); n++; }
  const out = {};
  bs.forEach((b, i) => { out[b] = String.fromCharCode(cs[i]); });
  return out;
})();
const UNI_TO_BYTES = {};
Object.entries(BYTES_TO_UNI).forEach(([b, u]) => { UNI_TO_BYTES[u] = +b; });

function byteEncode(text) {
  const bytes = new TextEncoder().encode(text);
  let s = "";
  for (const b of bytes) s += BYTES_TO_UNI[b];
  return s;
}
function byteDecode(str) {
  const bytes = new Uint8Array(str.length);
  for (let i = 0; i < str.length; i++) bytes[i] = UNI_TO_BYTES[str[i]] || 63;
  return new TextDecoder().decode(bytes);
}

/* ---------- 2. tokenizer state (loaded dari tokenizer.json) ---------- */
let VOCAB = null;    // token string -> id
let ID_TOK = null;   // id -> token string
let MERGE_RANK = null;
const SPECIALS = ["<pad>", "<bos>", "<eos>", "<user>", "<bot>", "<mem>", "</mem>", "<img>", "</img>"];
const SPECIAL_RE = /(<pad>|<bos>|<eos>|<user>|<bot>|<mem>|<\/mem>|<img>|<\/img>)/;
const PRETOK = /'s|'t|'re|'ve|'m|'ll|'d| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+/gu;

async function loadTokenizer() {
  const d = await (await fetch("tokenizer.json")).json();
  VOCAB = Object.fromEntries(Object.entries(d.model.vocab).map(([t, i]) => [t, i]));
  // added_tokens menimpa vocab (id 0-8 = special)
  (d.added_tokens || []).forEach(t => { VOCAB[t.content] = t.id; });
  ID_TOK = []; Object.entries(VOCAB).forEach(([t, i]) => { ID_TOK[i] = t; });
  MERGE_RANK = new Map();
  d.model.merges.forEach((pair, r) => MERGE_RANK.set(pair[0] + "\u0000" + pair[1], r));
}

function bpe(word) {
  if (word.length <= 1) return [word];
  let parts = [...word];
  for (;;) {
    let best = Infinity, bi = -1;
    for (let i = 0; i < parts.length - 1; i++) {
      const r = MERGE_RANK.get(parts[i] + "\u0000" + parts[i + 1]);
      if (r !== undefined && r < best) { best = r; bi = i; }
    }
    if (bi < 0) break;
    parts.splice(bi, 2, parts[bi] + parts[bi + 1]);
  }
  return parts;
}

function encode(text) {
  const ids = [];
  for (const seg of text.split(SPECIAL_RE)) {
    if (!seg) continue;
    if (SPECIALS.includes(seg)) { const id = VOCAB[seg]; if (id !== undefined) ids.push(id); continue; }
    const words = seg.match(PRETOK) || [];
    for (const w of words) {
      const enc = bpe(byteEncode(w));
      for (const p of enc) { const id = VOCAB[p]; if (id !== undefined) ids.push(id); }
    }
  }
  return ids;
}

const KEEP_SPECIALS = new Set(["<img>", "</img>"]);  // img tag HARUS survive decode (sistem gambar!)
function decode(ids) {
  let s = "";
  for (const id of ids) {
    const t = ID_TOK[id];
    if (!t) continue;
    if (SPECIALS.includes(t) && !KEEP_SPECIALS.has(t)) continue;
    s += t;
  }
  return byteDecode(s);
}

/* ---------- 3. ONNX Runtime ---------- */
let SESSION = null;
const PAD = 0, EOS = 2, USER = 3;

async function fetchWithProgress(url, onPct) {
  const r = await fetch(url);
  const total = +r.headers.get("Content-Length") || 63000000;
  const reader = r.body.getReader();
  let recv = 0; const chunks = [];
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value); recv += value.length;
    onPct(Math.min(1, recv / total));
  }
  const buf = await new Blob(chunks).arrayBuffer();
  return buf;
}

async function loadModel(onPct, onStage) {
  onStage("download restartion_i8.onnx (63 MB, sekali doang — browser cache)…");
  const buf = await fetchWithProgress("model/restartion_i8.onnx", onPct);
  onPct(1);
  onStage("init onnxruntime (wasm)…");
  ort.env.wasm.numThreads = 1; // github.io gak ada COOP/COEP → single thread
  SESSION = await ort.InferenceSession.create(buf, {
    executionProviders: ["wasm"],
    graphOptimizationLevel: "all",
  });
}

async function forward(ids) {
  const t = new ort.Tensor("int64", BigInt64Array.from(ids, BigInt), [1, ids.length]);
  const out = await SESSION.run({ ids: t });
  return out.logits.data; // Float32Array [V]
}

/* ---------- 4. sampling (port dari model.generate) ---------- */
async function generate(ids, opts) {
  const { maxNew = 80, temp = 0.82, topK = 45, topP = 0.90, repPen = 1.15 } = opts || {};
  const out = ids.slice();
  for (let step = 0; step < maxNew; step++) {
    const cond = out.length > 3900 ? out.slice(-3900) : out;
    const logits = await forward(cond);
    const V = logits.length;
    const L = new Float64Array(V);
    for (let t = 0; t < V; t++) L[t] = logits[t] / temp;
    const seen = new Set(out);
    for (const t of seen) L[t] = L[t] > 0 ? L[t] / repPen : L[t] * repPen;
    L[PAD] = -Infinity;
    // sort desc
    const idx = Array.from({ length: V }, (_, i) => i);
    idx.sort((a, b) => L[b] - L[a]);
    if (topK > 0 && idx.length > topK) idx.length = topK;
    const probs = idx.map(t => Math.exp(L[t]));
    const sum = probs.reduce((a, b) => a + b, 0);
    const norms = probs.map(p => p / sum);
    let cum = 0; const kept = [];
    for (let j = 0; j < idx.length; j++) { if (cum > topP) break; kept.push(j); cum += norms[j]; }
    const tot = kept.reduce((a, j) => a + norms[j], 0);
    let r = Math.random() * tot, pick = kept[0];
    for (const j of kept) { r -= norms[j]; if (r <= 0) { pick = j; break; } }
    const nextTok = idx[pick];
    if (nextTok === EOS || nextTok === USER) break;
    out.push(nextTok);
    if (onToken) onToken(step + 1);
  }
  return out.slice(ids.length);
}
let onToken = null;

/* ---------- 5. engine: memori asli + galeri + persona ---------- */
const MEM = JSON.parse(localStorage.getItem("restartion_mem") || '{"facts":{},"images":{},"history":[]}');
function saveMem() { localStorage.setItem("restartion_mem", JSON.stringify(MEM)); updateMemChip(); }
function updateMemChip() {
  const el = document.getElementById("mem-chip");
  if (el) el.textContent = "🧠 mem: " + Object.keys(MEM.facts).length;
}

const GALLERY = ["videoframe_20260629_220129.jpg"];
const ANGER_IMG = "download.jpeg";
const MEM_NAMES = ["Riz", "Dimas", "Kevin", "Farhan", "Bagas", "Ares", "Nabil", "Raka", "Dafa",
  "Gilang", "Yoga", "Ilham", "Rey", "Satria", "Alvin", "Panji", "Bayu", "Zaki",
  "Rizky", "Fajar", "Andra", "Wahyu", "Tegar", "Galih", "Bintang"];

const INSULTS = /\b(dumb|stupid|idiot|useless|trash|garbage|stfu|kys|loser|bego|goblok|tolol|jelek|kasihan|kasian|mid|suck|sucks|worst|annoying|hate (u|you)|fuck (u|you)|fuck you|shut up|ngentot|anjing|gila|suck)\b/i;
const DEATH = /\b(died|passed away|passed|rest in peace|rip|meninggal|wafat|gugur|tiada|mati)\b/i;
const NAME_PAT = /\b(?:my name(?:'s| is)|call me|aku|gue|namaku|nama gue)\s+([A-Z][a-z]{1,15})/;
const PET_PAT = /\bmy (cat|dog|hamster|bird|rabbit)(?:'s name| named| is named| namanya)?\s+([A-Z][a-z]{1,15})/;
const LIKE_PAT = /\bi (?:really )?(love|like|hate|fear)\s+([a-z ][a-z ]{2,28}?)(?:[.,!?]|$)/i;
const VIDEO_HINT = /\b(movie|film|nonton|cinema|bioskop|frame|scene|drakor|series|episode|netflix|trailer|videoframe|hwachua|anime|kw|mov|ending|plot|spoiler|reels|shorts)\b/i;
const ASK_PIC = /\b(send|kirim|show)\b[^.?!\n]{0,40}\b(pic|img|image|photo|foto|gambar|selfie|videoframe)s?\b|\b(pic|foto|gambar|selfie)s?\b[^^.?!\n]{0,24}\b(dong|lah|gih|donk|banh|gng|twin)\b/i;
const IMG_TAG = /<img>([^<]+)<\/img>/g;
const LEAK = /<mem>|<\/mem>|user:|\| [a-z]+:/;

function memExtract(text) {
  const m = NAME_PAT.exec(text);
  if (m && !["guess", "what", "the", "just", "not", "so", "very", "really"].includes(m[1].toLowerCase()))
    MEM.facts.name = m[1];
  const p = PET_PAT.exec(text);
  if (p) MEM.facts[p[1]] = p[2];
  const likes = text.matchAll(new RegExp(LIKE_PAT.source, "gi"));
  for (const l of likes) {
    const obj = l[2].trim();
    if (obj.split(" ").length <= 4) MEM.facts[l[1].toLowerCase()] = obj;
  }
  const low = text.toLowerCase();
  if (/\b\d{1,2}\s*(?:am|pm)\b.*\b(?:sleep|bed)\b/.test(low)) MEM.facts.sleeps = "super late";
  if (/\b(gabut|bored)\b/.test(low)) MEM.facts.vibe = "always gabut";
  saveMem();
}

function memBlock() {
  const f = MEM.facts, keys = Object.keys(f);
  if (!keys.length) return null;
  const head = "name" in f ? `user: ${f.name}` : "";
  const rest = keys.filter(k => k !== "name").map(k => `${k}: ${f[k]}`).join("; ");
  // PERSIS format training python: head + (" | " + rest if rest else "")
  return `<mem>${head}${rest ? " | " + rest : ""}</mem>`;
}

function buildPrompt(history) {
  const mem = memBlock();
  let s = "<bos>" + (mem ? mem + "\n" : "");
  for (const [role, text] of history.slice(-14))
    s += (role === "user" ? "<user>" : "<bot>") + text + "\n";
  s += "<bot>";
  let ids = encode(s);
  if (ids.length > 3900) ids = ids.slice(-3900);
  return ids;
}

async function genText(history, temp) {
  const ids = buildPrompt(history);
  const newIds = await generate(ids, { maxNew: 80, temp });
  let t = decode(newIds);
  for (const stopper of ["<user>", "<eos>", "<bos>"]) t = t.split(stopper)[0];
  return t.trim();
}

async function engineReply(userText, history, convoId) {
  memExtract(userText);
  const grief = DEATH.test(userText);
  const convoImgs = new Set(MEM.images[convoId] || []);

  let text = await genText(history, 0.82);
  if (LEAK.test(text)) {                       // mem-block leak guard
    text = await genText(history, 0.62);
    if (LEAK.test(text)) {
      text = text.split("\n").filter(l => !/<mem>|<\/mem>|user:/.test(l)).join(" ").trim();
    }
  }
  text = text.replace(/<\/?(mem|bot)>/g, " ").replace(/\n+/g, "\n").trim();

  /* ---- AI THINKS: kirim foto kalau konteks masuk akal (spec v2) ---- */
  const otherImgInConvo = [...convoImgs].some(i => i !== ANGER_IMG);
  if ((VIDEO_HINT.test(userText) || ASK_PIC.test(userText)) && !grief &&
      !otherImgInConvo && !convoImbsHas(convoId, GALLERY[0]) && !text.includes("<img>")) {
    text = `${text} <img>${GALLERY[0]}</img>`.trim();
  }
  // filter: cuma galeri, max 1 gambar per reply
  const keepTags = [];
  for (const m of text.matchAll(IMG_TAG)) {
    const name = m[1];
    if (name === ANGER_IMG || (GALLERY.includes(name) && !otherImgInConvo)) keepTags.push(m[0]);
  }
  text = text.replace(IMG_TAG, "").trim();
  if (keepTags.length) text = (text + " " + keepTags[0]).trim();
  // register gambar yang AI kirim
  for (const m of text.matchAll(IMG_TAG)) {
    (MEM.images[convoId] = MEM.images[convoId] || []).push(m[1]);
    MEM.images[convoId] = [...new Set(MEM.images[convoId])].slice(-6);
    saveMem();
  }

  /* ---- persona guarantees ---- */
  let sentImg = /<img>[^<]+<\/img>/.test(text);
  if (grief && !/(respect|sorry|strong|sabar|stay)/i.test(text)) {
    const lines = [
      "aight twin, line up: dance to pay le respect 🙏💫 ... and fr, im here if u need to yap banh.",
      "o7 ... dance to pay le respect gng 🙏 stay strong twin, the json keeps their memory.",
    ];
    text = lines[Math.floor(Math.random() * lines.length)];
  }
  let streak = 0;
  for (let i = history.length - 1; i >= 0; i--) {
    const [role, t2] = history[i];
    if (role === "user" && INSULTS.test(t2)) streak++;
    else if (role === "user") break;
  }
  if (streak >= 3 && !sentImg && !grief) {
    if (streak >= 4 || Math.random() < 0.5) text = `${text} <img>${ANGER_IMG}</img>`.trim();
  }
  // name grounding: nama asli dari memori
  const realName = MEM.facts.name;
  if (realName && !text.includes(realName)) {
    for (const wrong of MEM_NAMES) {
      if (wrong !== realName && new RegExp(`\\b${wrong}\\b`).test(text)) {
        text = text.replace(new RegExp(`\\b${wrong}\\b`), realName);
        break;
      }
    }
  }
  if (!text) {
    const lines = ["... twin the void answered. try again banh.", "bruh the tokens slipped. say that again gng 😭"];
    text = lines[Math.floor(Math.random() * lines.length)];
  }
  return text;
}
function convoImbsHas(convoId, name) { return (MEM.images[convoId] || []).includes(name); }

/* ---------- 6. UI ---------- */
const $ = s => document.querySelector(s);
const msgs = $("#messages");
let SID = sessionStorage.getItem("convo") || ("web_" + Math.random().toString(36).slice(2, 8));
sessionStorage.setItem("convo", SID);

function scrollDown() { $("#chat").scrollTop = $("#chat").scrollHeight; }

function addRow(role, text, imgs) {
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
    img.src = "assets/" + encodeURIComponent(name);
    img.loading = "lazy";
    const cap = document.createElement("div");
    cap.className = "imgname";
    cap.textContent = "🖼 " + name + (name === ANGER_IMG ? " · mode marah" : " · galeri restartion");
    card.append(img, cap);
    bubble.append(card);
  });
  row.append(av, bubble);
  msgs.append(row);
  scrollDown();
  return row;
}

function addTyping() {
  const row = document.createElement("div");
  row.className = "row bot";
  row.innerHTML = `<div class="avatar">⟁</div><div class="bubble typing"><i></i><i></i><i></i></div>`;
  msgs.append(row); scrollDown();
  return row;
}

let BUSY = false;
async function send(text) {
  if (!text || BUSY || !SESSION) return;
  BUSY = true;
  addRow("user", text, []);
  const t = addTyping();
  const hist = (sessionStorage.getItem("hist_" + SID) ? JSON.parse(sessionStorage.getItem("hist_" + SID)) : []);
  hist.push(["user", text]);
  try {
    const reply = await engineReply(text, hist, SID);
    hist.push(["bot", reply]);
    sessionStorage.setItem("hist_" + SID, JSON.stringify(hist.slice(-30)));
    t.remove();
    const imgs = [...reply.matchAll(/<img>([^<]+)<\/img>/g)].map(m => m[1]);
    addRow("bot", reply.replace(/\s*<img>[^<]+<\/img>/g, "").trim(), imgs);
  } catch (e) {
    console.error(e);
    t.remove();
    addRow("bot", "bruh token lu ketelen waswas 😭 coba lagi gng.", []);
  }
  $("#text").value = "";
  BUSY = false;
}

$("#form").addEventListener("submit", e => { e.preventDefault(); send($("#text").value.trim()); });
$("#text").focus();

$("#btn-reset").addEventListener("click", () => {
  SID = "web_" + Math.random().toString(36).slice(2, 8);
  sessionStorage.setItem("convo", SID);
  sessionStorage.removeItem("hist_" + SID);
  msgs.innerHTML = "";
  boot();
});

function boot() {
  addRow("bot",
    "yo. restartion online. 🔩\nmodel gue (57.44M params, dilatih DARI NOL) barusan lu download DAN jalan di CPU browser lu. gak ada server, gak ada API, gak ada GPT — murni tensor.\ngue bisa: roasting, nge-joke, nginget hal yang lu bilang (beneran — localStorage gue, gak hilang walau lu refresh), dan KIRIM FOTO dari galeri gue kalau konteksnya masuk akal. di sini gue yang pegang kamera 😌\ncoba: 'yo', 'roast me', 'gue barusan nonton film', 'tell me a joke', 'my cat died' (RIP, nanti gue dance buat dia 🙏), atau titip nama lu biar gue inget.", []);
}

/* ---------- 7. boot sequence ---------- */
(async () => {
  const wrap = $("#loadwrap"), fill = $("#loadfill"), desc = $("#loaddesc");
  const pct = p => { fill.style.width = (p * 100).toFixed(1) + "%"; };
  try {
    desc.textContent = "load tokenizer (BPE from scratch)…";
    await loadTokenizer();
    onToken = n => { desc.textContent = `generating… token ${n}`; };
    await loadModel(pct, s => { desc.textContent = s; });
    wrap.remove();
    updateMemChip();
    $("#text").disabled = false; $("#btn-send").disabled = false;
    $("#text").focus();
    boot();
  } catch (e) {
    console.error(e);
    desc.textContent = "gagal load model 😭 cek console / koneksi. refresh untuk coba lagi.";
  }
})();
