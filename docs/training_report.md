# restartion — training report (jujur & lengkap)

## ringkasan

| tahap | data | init dari | steps | total steps kumulatif | avg loss akhir |
|---|---|---|---|---|---|
| part1 | train_part1.bin (133.086 token) | acak total (cold) | 1450 | 1450 | **0.288** |
| part2 | part1+part2 (265.798 token, rehearsal) | weights part1 | 1250 | 2700 | **0.365** |
| part3 | part1+part2+part3 (402.505 token) | weights part2 | 1250 | **3950** | **0.323** |

- loss pertama pernah 9.12 → final 0.29-0.36. corpus kecil + disengaja overfit =
  personality yang nempel (lihat docs/chinchilla.md kenapa ini DESAIN, bukan kelemahan).
- hardware: 2 core CPU, ±2.2s/step, total ±2 jam 25 menit waktu dinding.
- export: int8 per-channel → 62.8MB per tahap (muat github, dequant saat load).

## perilaku yang muncul DARI MODEL (bukan hardcode)

- `dance to pay le respect 🙏` + versi Indonesia (`kakek lu pasti orang kuat... gws`)
  muncul sendiri saat user kabar duka.
- reaksi gambar `videoframe_20260629_220129.jpg` → roast "eye bags" / "nokia 2%"
  (reactor scope: gambar CUMA valid di konvo tempat dia dikirim).
- hulk `<img>download.jpeg</img>` keluar sendiri pas dihina (dilatih) + deterministic
  streak≥3 di engine buat jaminan.
- greeting pake nama dari memori (`oh look who logged in. Bimo.` — nama asli disuntik
  dari memory.json, bukan dari corpus).

## arsitektur (penuh, dari nol)

- 10 blok decoder: RMSNorm pre-norm → causal SDPA attention (10 kepala, d=640)
  → SwiGLU FFN (hidden 1728) → residual.
- positional: learned embedding 4096 posisi (window 4k sesuai request).
- vocab 8192 (BPE dilatih dari nol di corpus, 4762 id terpakai, sisanya pad).
- init: N(0, 0.02), residual-proj di-scale 1/sqrt(2L). GPT-2-style, ditulis manual.

## yang GAK jalan / kekurangan (transparansi)

- nama user kadang gak ke-pakai di jawaban (grounding lemah di 57M) → engine
  nge-swap nama corpus dengan nama asli dari memori.
- kalimat panjang kadang pecah (corpus pendek-pendek). butuh corpus percakapan
  multi-turn lebih panjang kalau mau lebih mulus.
- chinchilla-real butuh ±1.15B token — di luar budget CPU ini (docs/chinchilla.md).

---

# TRAINING REPORT v2 — upgrade 2026-10-24

## config baru (sesuai directive boss)

| stat | v1 | v2 |
|---|---|---|
| params | 57.44M | **58.75M** |
| context | 4096 | **8192** (dilatih sampai posisi 2048 via corpus long) |
| attention heads | 10 | **16** (head dim 40) |
| vocab slot / real | 8192 / 4762 | **6144 / 5792** (slot mengecil = hemat RAM, vocab REAL naik 21%) |
| special tokens | 9 | **11** (+ `<gif>`, `</gif>`) |
| layer / d_model | 10 / 640 | 10 / 640 (dipertahankan demi budget RAM) |
| corpus | 1.79M chars | **3.25M chars** (1.8x) |

Kenapa vocab slot malah turun: slot 8192 versi lama cuma kepake 4762 (sisanya padding
mati yang makan embedding table). Corpus v2 yang lebih gede ngeluarin 5792 token real
→ slot 6144 itu pas. Vocab REAL naik, embedding table mengecil, RAM turun. Win-win.

## perilaku baru yang DILATIH (bukan di-hardcode doang)

- savage greeting: "yo dawg" → dijawab gaya bebas ("stfu lil bro go fuck yourself",
  "youre so ugly lil dawg you didnt deserve to say hi to me", dll) — bank SAVAGE_GREET_A
- swearing "baik hati dan bergizi": fuck, shit, dumbass, ass, bitch
- slang: lil bro, dawg, lil dawg, keys, ts, ts frying me, im crine, im crying
- marah → "keys keys keys" (plesetan kys biar komen gak kena pelanggaran moderasi)
- tag `<gif>dance-dance-to-pay-respect.gif</gif>` → gif day to pay respect
- POLA JAM DIHAPUS TOTAL: corpus v2 gak punya satu pun "3am"/"6am" (verified rg).

## kurva loss

- corpus legs (ROW 256, batch 4): 9.12 (cold) → 0.089 avg30 @ step 3670 → 0.076 @ 3880
- long-context leg (ROW 2048, batch 1): mulai 3.78 (posisi jauh polos) → 0.95 @ 3730
- mini long refresh (ROW 1024): 1.04 @ 3900 (final checkpoint)
- total: 3900 step, ~2.9 jam CPU (2 core)

## runtime (TERUKUR, bukan kira-kira)

- python + torch: 220MB
- engine load int8 (dequant on load): 471MB resident / 558MB peak, load 0.7s
- generate: +11–15MB → 0.5–1.1s per reply
- 40 pesan panjang (ctx lebar): 516MB resident, peak TETAP 558MB
- **KESIMPULAN: 558MB peak ≤ 750MB budget boss ✓ (headroom 190MB)**

## export & parity

- int8: 62.8MB (`weights/restartion_part3_i8.pt`) @ step 3900
- ONNX: fp32 250.9MB → int8 **63.0MB** (`site/model/restartion_i8.onnx`)
- parity vs torch: max logit diff 0.41, greedy agreement **12/12 token** ✓

## catatan teknis

- engine resolver sekarang: part3_i8 → part3.pt → part1_i8 (runtime selalu int8)
- dequant int8 → tied weight (head.weight == tok_emb.weight) di-skip saat copy
  (named_parameters dedupe) — bug fixed
- deepthink server: best-of-5 + rerank heuristic + model CE (manual forward full-seq)
- site engine port: rerank pakai entropy distribusi token berikutnya (1 forward/kandidat)
