# RESTARTION 🔩

> transformer kecil yang dilatih **DARI NOL** buat nge-roast lu. 58.75M parameter. no API, no GPT, no wrapper. murni tensor + kebencian (positif).

```
 restartion v2
 ├─ 58.75M params (10 layer, d=640, 16 heads, SwiGLU, RMSNorm)
 ├─ context window: 8192 token (8k) — dilatih sampai posisi 2048
 ├─ attention heads: 16 (naik dari 10)
 ├─ tokenizer: BPE dilatih dari nol di corpus v2 (5792 id terpakai dari slot 6144, +<gif>)
 ├─ data: corpus v2 3.2 juta karakter (1.8x lipat) — savage greet, keys, ts, crine, swearing
 ├─ runtime RAM: 558MB peak (terukur) — muat di VPS 1GB
 └─ personality: joker, roaster, unserious, nyapa balik gaya bebas, kesel = keys keys keys
```

## 🔴 LIVE DEMO — jalan di browser lu
**https://osnailcyargta-ctrl.github.io/restartion/**

model int8 (63MB) ke-download sekali → inferensi 100% di CPU browser lu, gak ada server, gak ada API.
- `site/` = source code site (BPE byte-level in JS + ONNX Runtime Web + engine port v2)
- branch `gh-pages` = isi site lengkap dgn `model/restartion_i8.onnx` (export via `scripts/export_onnx.py`, parity check greedy 12/12 token identik dgn torch)
- deploy ulang: `bash scripts/deploy_pages.sh`

## fitur v2 (yang *beneran ada*, bukan janji)

| fitur | status | cara |
|---|---|---|
| transformer asli dari scratch | ✅ | `restartion/model.py` — causal self-attention + SwiGLU, init random, dilatih dari 0 |
| BPE dari nol | ✅ | `scripts/train_tokenizer.py` — vocab slot 6144 (5792 kepake), 5525 merges, special `<gif>` |
| context 8k | ✅ | positional embedding 8192 posisi; corpus long-context ROW 2048 ke-latih |
| 16 kepala attention | ✅ | head dim 40, paralel 16 |
| memori asli | ✅ | `memory/memory.json` persistent + `<mem>` block tiap turn, recall lintas sesi |
| SAVAGE GREET | ✅ | "yo dawg" → "stfu lil bro go fuck yourself" / "youre so ugly lil dawg you didnt deserve to say hi to me" — dilatih di corpus + injector engine |
| swearing santuy | ✅ | fuck, shit, dumbass, ass, bitch — masuk corpus (`lines_extra.py`) |
| slang baru | ✅ | lil bro, dawg, lil dawg, keys, ts, ts frying me, im crine, im crying |
| keys keys keys | ✅ | marah = spam "keys" (plesetan kys biar lolos moderasi sosmed) + si ijo keluar |
| gif **day to pay respect** | ✅ | tag baru `<gif>dance-dance-to-pay-respect.gif</gif>` — kabar duka → AI ngesend gif tarian |
| SELALU ada gambar | ✅ | reply tanpa tag media apapun otomatis dikasih videoframe (boss rule v3) |
| no clock talk | ✅ | pola "3am"/"6am" dilarang — di corpus DAN di-strip engine |
| thinking indicator ASLI | ✅ | "thought for 0.89s" = waktu inferensi beneran, bukan animasi |
| 🧪 deepthink (RAHASIA) | ✅ | **Ctrl+Alt+M** di site → popup tersembunyi → best-of-5 kandidat + rerank (heuristic + model confidence) — mikir 5-20x lebih lama, hasil dipilih, ASLI |
| user gak bisa kirim apa-apa | ✅ | upload dihapus total; galeri 100% milik AI |

## jalanin

```bash
pip install -r requirements.txt

# CLI
python chat.py

# web UI (flask)
python webui.py  # -> http://localhost:7860

# site (github.io) lokal
cd site && python -m http.server 8901  # model/ harus ada (export dulu)
```

## struktur

```
restartion/
├─ restartion/          # model + engine + corpus banks
│  ├─ model.py          # decoder-only transformer (dari nol)
│  ├─ engine.py         # brain stem: memori, aturan media, persona, deepthink
│  └─ corpus/           # banks kalimat (lines_core/extra/jokes/roasts/...)
├─ scripts/             # build_corpus, train_tokenizer, pack_data, train, export_i8, export_onnx
├─ data/                # corpus + tokenizer.json + train_part*.bin + train_long.bin
├─ weights/             # restartion_part3_i8.pt (runtime, 62.8MB)
├─ site/                # github.io (BPE JS + ORT Web + engine port)
├─ assets/              # galeri AI: videoframe, si ijo, gif respect
├─ docs/                # training_report, chinchilla
└─ webui.py / chat.py   # flask UI + CLI
```

## training v2 (ringkas)

- 3900 step total (cold init, AdamW + warmup + cosine), loss 9.12 → 0.08 (corpus) / 0.86 (long-ctx row 2048)
- corpus v2: 3.25M chars, ~720k token packed ROW 256 + long ROW 512 (posisi jauh)
- runtime: 558MB RAM peak, 0.5–1.1s per reply (2 core CPU)
- detail: `docs/training_report.md`
