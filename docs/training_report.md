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
