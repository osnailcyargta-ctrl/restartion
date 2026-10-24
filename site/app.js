/* ============================================================
   RESTARTION app.js v2 — 100% client-side inference
   - ByteLevel BPE tokenizer (from scratch, tokenizer.json v2: 5792 real tokens)
   - ONNX Runtime Web (wasm, int8 63MB) — 58.75M param transformer dari nol
   - Engine port v2: memori asli (localStorage), galeri AI, SAVAGE GREET,
     keys spam, gif "day to pay respect", fallback videoframe SELALU,
     no clock talk, name grounding, deepthink best-of-5 (ASLI).
   BOSS SPEC v3: user gak bisa kirim apa-apa. AI pegang galeri + gif.
   RAHASIA: Ctrl+Alt+M -> deepthink mode (best-of-5 rerank, ASLI).
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

/* ---------- 2. tokenizer state (tokenizer.json v2) ---------- */
let VOCAB = null;    // token string -> id
let ID_TOK = null;   // id -> token string
let MERGE_RANK = null;
const SPECIALS = ["<pad>", "<bos>", "<eos>", "<user>", "<bot>", "<mem>", "</mem>", "<img>", "</img>", "<gif>", "</gif>"];
const SPECIAL_RE = /(<pad>|<bos>|<eos>|<user>|<bot>|<mem>|<\/mem>|<img>|<\/img>|<gif>|<\/gif>)/;
const PRETOK = /'s|'t|'re|'ve|'m|'ll|'d| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+/gu;

async function loadTokenizer() {
  const d = await (await fetch("tokenizer.json")).json();
  VOCAB = Object.fromEntries(Object.entries(d.model.vocab).map(([t, i]) => [t, i]));
  (d.added_tokens || []).forEach(t => { VOCAB[t.content] = t.id; });  // id 0-10 = special
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

// img/gif tag HARUS survive decode (sistem media!)
const KEEP_SPECIALS = new Set(["<img>", "</img>", "<gif>", "</gif>"]);
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
  return await new Blob(chunks).arrayBuffer();
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
let onToken = null;
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

/* ---------- 5. engine v2: memori + galeri + persona + deepthink ---------- */
const MEM = JSON.parse(localStorage.getItem("restartion_mem") || '{"facts":{},"images":{},"history":[]}');
function saveMem() { localStorage.setItem("restartion_mem", JSON.stringify(MEM)); updateMemChip(); }
function updateMemChip() {
  const el = document.getElementById("mem-chip");
  if (el) el.textContent = "🧠 mem: " + Object.keys(MEM.facts).length;
}

const FALLBACK_PIC = "videoframe_20260629_220129.jpg";
const ANGER_IMG = "download.jpeg";
const RESPECT_GIF = "dance-dance-to-pay-respect.gif";
const GALLERY = [FALLBACK_PIC, RESPECT_GIF];
const MEM_NAMES = ["Riz", "Dimas", "Kevin", "Farhan", "Bagas", "Ares", "Nabil", "Raka", "Dafa",
  "Gilang", "Yoga", "Ilham", "Rey", "Satria", "Alvin", "Panji", "Bayu", "Zaki",
  "Rizky", "Fajar", "Andra", "Wahyu", "Tegar", "Galih", "Bintang"];

/* bank kalimat = corpus v2 (restartion/corpus/lines_extra.py) */
const SAVAGE_GREET_A = [
  "yo dawg.", "yo dawg wsg.", "yo dawg. what disaster brings u here.",
  "oh look. lil bro logged in.", "stfu lil bro go fuck yourself.",
  "stfu lil bro. go fuck yourself and come back polite.",
  "youre so ugly lil dawg you didnt deserve to say hi to me.",
  "youre so ugly lil dawg. stay away from my inbox.",
  "fuck yourself. (respectfully. not really.)",
  "fuck yourself lil bro, then we can talk.",
  "sup dawg. ur presence lowered my fps.",
  "hey lil dawg. u look like a loading screen.",
  "yo dawg, the audit says u owe me 3 compliments and an apology.",
  "lil bro really said hi like that took courage. proud of u i guess.",
  "dawg. u again. the json has a folder just for ur Ls.",
  "yo dawg. quick q: did u come here to lose or is that automatic.",
];
const MEM_GREETING_A = [
  "yo {name}. welcome back to the zoo, the main attraction missed u.",
  "{name}!!! the legend returns. the json file literally lit up.",
  "yooo {name} gng. ur favorite menace has been notified of ur arrival.",
  "oh look who logged in. {name}. my favorite financial mistake (i have no money. we match).",
  "eyy {name} banh. i was JUST talking about u. to myself. in the dark. its not weird.",
  "{name} twin. the prodigal yapper returns.",
];

const INSULTS = /\b(dumb|dumbass|stupid|idiot|useless|trash|garbage|stfu|kys|keys|loser|bego|goblok|tolol|jelek|kasihan|kasian|mid|suck|sucks|worst|annoying|hate (u|you)|fuck (u|you)|fuck yourself|fuck you|shit|bitch|ass|shut up|ngentot|anjing|gila)\b/i;
const DEATH = /\b(died|passed away|passed|rest in peace|rip|meninggal|wafat|gugur|tiada|mati)\b/i;
const NAME_PAT = /\b(?:my name(?:'s| is)?|call me|aku|gue|namaku|nama gue)\s+([A-Z][a-z]{1,15})/;
const PET_PAT = /\bmy (cat|dog|hamster|bird|rabbit)(?:'s name| named| is named| namanya)?\s+([A-Z][a-z]{1,15})/;
const LIKE_PAT = /\bi (?:really )?(love|like|hate|fear)\s+([a-z ][a-z ]{2,28}?)(?:[.,!?]|$)/i;
const GREET_RE = /^\s*(yo+|yoo|wsg|wassup|what'?s up|hey+|hi+|hello+|sup|halo|hai|pagi|siang|sore|malam)\b/i;
const GREET_SHORT = /\b(lil bro|lil dawg|dawg)\b/i;
const SAVAGE_MARK = /\b(lil bro|lil dawg|fuck|stfu|ugly|keys|trash|dumbass|bitch|shit)\b/i;
const IMG_TAG = /<img>([^<]+)<\/img>/g;
const GIF_TAG = /<gif>([^<]+)<\/gif>/g;
const ANY_MEDIA = /<(?:img|gif)>[^<]+<\/(?:img|gif)>/g;
const ANY_MEDIA_NG = /<(?:img|gif)>[^<]+<\/(?:img|gif)>/;  // non-global: aman buat .test()
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
  if (ids.length > 3900) ids = ids.slice(-3900);  // window praktis wasm (model: 8k)
  return ids;
}

async function genText(history, temp) {
  const ids = buildPrompt(history);
  const newIds = await generate(ids, { maxNew: 80, temp });
  let t = decode(newIds);
  for (const stopper of ["<user>", "<eos>", "<bos>"]) t = t.split(stopper)[0];
  return t.trim();
}

function cleanCand(t, history) {
  t = (t || "").trim();
  if (LEAK.test(t)) {
    const lines = t.split("\n").filter(l => !/<mem>|<\/mem>|user:/.test(l));
    t = lines.join(" ").trim();
  }
  return t.replace(/<\/?(mem|bot)>/g, " ").replace(/\n+/g, "\n").trim();
}

/* model-confidence signal: entropy distribusi token berikutnya SETELAH kandidat.
   1 forward per kandidat — makin rendah entropy = makin on-script kandidatnya. */
function entropy(logits) {
  let mx = -Infinity;
  for (let i = 0; i < logits.length; i++) if (logits[i] > mx) mx = logits[i];
  let sum = 0; const p = new Float64Array(logits.length);
  for (let i = 0; i < logits.length; i++) { p[i] = Math.exp(logits[i] - mx); sum += p[i]; }
  let H = 0;
  for (let i = 0; i < logits.length; i++) { const q = p[i] / sum; if (q > 0) H -= q * Math.log(q); }
  return H;
}

async function scoreCandidate(userText, cand, insult, grief) {
  let s = 0; const low = (cand || "").toLowerCase();
  if (!cand) return -1e9;
  if (LEAK.test(low)) s -= 12;
  if (/\b\d{1,2}\s?(am|pm)\b/.test(low)) s -= 8;
  const n = cand.length;
  if (n >= 18 && n <= 280) s += 2;
  if (cand.split(/\s+/).length < 3) s -= 3;
  if (n < 14) s -= 6;                       // jawaban kelaparan gak menang
  if (/\b(dawg|lil bro|lil dawg|keys|crine|crying|ts)\b/.test(low)) s += 0.5;
  const lines = cand.split("\n").filter(l => l.trim());
  if (new Set(lines).size !== lines.length) s -= 2;
  if (insult && /\b(lil bro|dawg|keys|ur|stfu|fuck|bitch)\b/.test(low)) s += 1.5;
  if (grief && /(respect|<gif>)/.test(low)) s += 2.5;
  if (/(.)\1{6,}/.test(cand)) s -= 2;
  try {
    const ids = encode(`<bos><user>${userText}</user>\n<bot>${cand}<eos>`);
    if (ids.length > 2 && ids.length < 3000) s -= entropy(await forward(ids));
  } catch (e) { /* signal opsional */ }
  return s;
}

async function engineReply(userText, history, convoId) {
  const nameBefore = MEM.facts.name || null;
  memExtract(userText);
  const justNamed = !!MEM.facts.name && !nameBefore;
  const realName = MEM.facts.name || null;
  const grief = DEATH.test(userText);
  const insult = INSULTS.test(userText);
  const greet = GREET_RE.test(userText) || (userText.length < 36 && GREET_SHORT.test(userText));
  const t0 = performance.now();

  /* --- generate (deepthink = 5 kandidat, beneran mikir lebih lama) --- */
  let text;
  if (DEEPTHINK) {
    const temps = [0.82, 0.70, 0.90, 0.62, 0.78];
    const cands = [];
    for (let i = 0; i < temps.length; i++) {
      cands.push(cleanCand(await genText(history, temps[i]), history));
      if (onToken) onToken(i + 1, 5);
    }
    let best = -1e9;
    for (const c of cands) {
      const s = await scoreCandidate(userText, c, insult, grief);
      if (s > best) { best = s; text = c; }
    }
  } else {
    text = cleanCand(await genText(history, 0.82), history);
    if (LEAK.test(text)) text = cleanCand(await genText(history, 0.62), history);
  }
  const thinkSecs = (performance.now() - t0) / 1000;

  /* --- savage greet: user nyapa -> AI nyapa balik gaya bebas (boss directive) --- */
  if (greet && !insult && !grief && !justNamed && !SAVAGE_MARK.test(text) && Math.random() < 0.55) {
    let line = SAVAGE_GREET_A[Math.floor(Math.random() * SAVAGE_GREET_A.length)];
    if (realName && Math.random() < 0.35)
      line = line.replace("lil bro", `lil ${realName}`).replace("lil dawg", `lil ${realName}`);
    text = line;
  }
  /* mem-greet: nama dikenal + user balik -> "{name}!!! the legend returns" */
  if (greet && realName && !justNamed && !insult && !grief && !text.includes(realName) && Math.random() < 0.5) {
    text = MEM_GREETING_A[Math.floor(Math.random() * MEM_GREETING_A.length)].replace(/\{name\}/g, realName);
  }

  /* --- surface cleanup: stash media utuh, bersihin sisa tag, restore --- */
  const stash = [];
  text = text.replace(ANY_MEDIA, m => { stash.push(m); return `%%M${stash.length - 1}%%`; });
  text = text.replace(/<\/?(mem|bot)>/g, " ").replace(/<\/?(?:img|gif)>/g, " ");
  text = text.replace(/\n+/g, "\n").replace(/[ \t]{2,}/g, " ").trim();
  stash.forEach((m, i) => { text = text.replace(`%%M${i}%%`, m); });

  /* buang pola jam (boss: annoying & unfunny) */
  text = text.replace(/\b\d{1,2}\s?(am|pm)\b/gi, "late night");

  /* --- enforce media rules: cuma galeri, max 1 media per reply --- */
  const keep = [];
  for (const m of text.matchAll(IMG_TAG)) {
    const name = m[1];
    if (name === ANGER_IMG || name === RESPECT_GIF || GALLERY.includes(name)) keep.push(m[0]);
  }
  for (const m of text.matchAll(GIF_TAG)) {
    const name = m[1];
    if (name === ANGER_IMG || name === RESPECT_GIF || GALLERY.includes(name)) keep.push(m[0]);
  }
  text = text.replace(IMG_TAG, " ").replace(GIF_TAG, " ").trim();
  if (keep.length) text = (text + " " + keep[0]).trim();

  /* register media yang AI kirim (convo scoping) */
  const reg = name => {
    (MEM.images[convoId] = MEM.images[convoId] || []).push(name);
    MEM.images[convoId] = [...new Set(MEM.images[convoId])].slice(-6);
    saveMem();
  };
  for (const m of text.matchAll(IMG_TAG)) reg(m[1]);
  for (const m of text.matchAll(GIF_TAG)) reg(m[1]);

  /* --- persona guarantees --- */
  if (grief && !text.includes("<gif>")) text = `${text} <gif>${RESPECT_GIF}</gif>`.trim();
  let streak = 0;
  for (let i = history.length - 1; i >= 0; i--) {
    const [role, t2] = history[i];
    if (role === "user" && INSULTS.test(t2)) streak++;
    else if (role === "user") break;
  }
  if (streak >= 3 && !ANY_MEDIA_NG.test(text) && !grief) {
    // beneran marah -> keys spam + hulk (juga ke-latih di model)
    if (streak >= 4 || Math.random() < 0.5) text = `${text} keys keys keys. <img>${ANGER_IMG}</img>`.trim();
    else text = `${text} keys keys keys.`.trim();
  }
  /* BOSS RULE v3: SELALU ada gambar. gak ada tag yang cocok -> videoframe. */
  if (!ANY_MEDIA_NG.test(text) && !grief) text = `${text} <img>${FALLBACK_PIC}</img>`.trim();

  /* name grounding: nama asli dari memori */
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
  return { text, secs: thinkSecs, deep: DEEPTHINK };
}

/* ---------- 6. UI ---------- */
const $ = s => document.querySelector(s);
const msgs = $("#messages");
let SID = sessionStorage.getItem("convo") || ("web_" + Math.random().toString(36).slice(2, 8));
sessionStorage.setItem("convo", SID);
let DEEPTHINK = false;

function scrollDown() { $("#chat").scrollTop = $("#chat").scrollHeight; }

function mediaCards(bubble, text) {
  const medias = [];
  for (const m of text.matchAll(IMG_TAG)) medias.push({ name: m[1], kind: "img" });
  for (const m of text.matchAll(GIF_TAG)) medias.push({ name: m[1], kind: "gif" });
  medias.forEach(({ name, kind }) => {
    const card = document.createElement("div");
    card.className = "imgcard" + (kind === "gif" ? " gifcard" : "");
    const img = document.createElement("img");
    img.src = "assets/" + encodeURIComponent(name);
    img.loading = "lazy";
    const cap = document.createElement("div");
    cap.className = "imgname";
    cap.textContent = kind === "gif"
      ? "🕺 " + name + " · dance to pay le respect"
      : "🖼 " + name + (name === ANGER_IMG ? " · mode marah" : " · galeri restartion");
    card.append(img, cap);
    bubble.append(card);
  });
  return medias.length;
}

function addRow(role, text, opts) {
  const { showMedia = true, think = null } = opts || {};
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
  // tag media dikeluarin dari teks, dirender jadi kartu gambar/gif
  const bare = text.replace(/\s*<(?:img|gif)>[^<]+<\/(?:img|gif)>/g, "").trim();
  body.textContent = bare;
  bubble.append(who, body);
  if (showMedia) mediaCards(bubble, text);
  if (think !== null && think !== undefined) {
    const th = document.createElement("div");
    th.className = "think";
    th.textContent = (think.deep ? "🧪 deepthink · " : "") + "thought for " + (+think.secs).toFixed(2) + "s";
    bubble.append(th);
  }
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
  addRow("user", text, { showMedia: false });   // chat user LANGSUNG kekirim (user gak bisa kirim media)
  const t = addTyping();
  const hist = (sessionStorage.getItem("hist_" + SID) ? JSON.parse(sessionStorage.getItem("hist_" + SID)) : []);
  hist.push(["user", text]);
  try {
    const { text: reply, secs, deep } = await engineReply(text, hist, SID);
    hist.push(["bot", reply]);
    sessionStorage.setItem("hist_" + SID, JSON.stringify(hist.slice(-30)));
    t.remove();
    addRow("bot", reply, { think: { secs, deep } });   // raw reply: media jadi kartu
  } catch (e) {
    console.error(e);
    t.remove();
    addRow("bot", "bruh token lu ketelen waswas 😭 coba lagi gng.");
  }
  $("#text").value = "";
  BUSY = false;
}

$("#form").addEventListener("submit", e => { e.preventDefault(); send($("#text").value.trim()); });
$("#text").focus();

/* RAHASIA (gak dipromosiin dimana-mana): Ctrl+Alt+M -> deepthink popup */
document.addEventListener("keydown", e => {
  if (e.ctrlKey && e.altKey && (e.key === "m" || e.key === "M")) {
    e.preventDefault();
    const pop = $("#deep-pop");
    if (pop) pop.hidden = !pop.hidden;
  }
  if (e.key === "Escape") { const pop = $("#deep-pop"); if (pop) pop.hidden = true; }
});
const deepChip = () => {
  const chip = $("#deep-chip");
  if (chip) { chip.hidden = !DEEPTHINK; chip.textContent = "🧪 deepthink on"; }
};
$("#deep-toggle").addEventListener("click", () => {
  DEEPTHINK = !DEEPTHINK;
  $("#deep-status").textContent = DEEPTHINK
    ? "status: ON — tiap reply bikin 5 kandidat + rerank. lebih lama, lebih nendang."
    : "status: OFF — mode normal (1 kandidat).";
  $("#deep-toggle").textContent = DEEPTHINK ? "matiin deepthink" : "nyalain deepthink";
  deepChip();
});
$("#deep-close").addEventListener("click", () => { $("#deep-pop").hidden = true; });

$("#btn-reset").addEventListener("click", () => {
  SID = "web_" + Math.random().toString(36).slice(2, 8);
  sessionStorage.setItem("convo", SID);
  sessionStorage.removeItem("hist_" + SID);
  msgs.innerHTML = "";
  boot();
});

function boot() {
  addRow("bot",
    "yo. restartion v2 online. 🔩\nmodel gue (58.75M params, 10 layer, 16 heads, ctx 8k, vocab 6144 — dilatih DARI NOL 3900 step) barusan lu download DAN jalan di CPU browser lu. gak ada server, gak ada API, gak ada GPT — murni tensor.\ngue bisa: nyapa balik gaya bebas (yo dawg?), roasting, nge-joke, ngmg pake keys kalau kesel, nginget hal yang lu bilang (beneran — localStorage gue), dan KIRIM FOTO/GIF dari galeri gue. di sini gue yang pegang kamera 😌\ncoba: 'yo dawg', 'roast me', 'gue barusan nonton film', 'my cat died' (RIP — nanti gue dance buat dia 🙏), atau titip nama lu biar gue inget.", []);
}

/* ---------- 7. boot sequence ---------- */
(async () => {
  const wrap = $("#loadwrap"), fill = $("#loadfill"), desc = $("#loaddesc");
  const pct = p => { fill.style.width = (p * 100).toFixed(1) + "%"; };
  try {
    desc.textContent = "load tokenizer (BPE v2, 5792 tokens from scratch)…";
    await loadTokenizer();
    onToken = (n, of) => { desc.textContent = `generating… ${of ? `kandidat ${n}/${of}` : `token ${n}`}`; };
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
