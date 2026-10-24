# RESTARTION 🔩

> transformer kecil yang dilatih **DARI NOL** buat nge-roast lu. 57.44M parameter. no API, no GPT, no wrapper. murni tensor + kebencian (positif).

```
 restartion-small
 ├─ 57.44M params (10 layer, d=640, 10 heads, SwiGLU, RMSNorm)
 ├─ context window: 4096 token (4k, sesuai request)
 ├─ tokenizer: BPE dilatih dari nol di corpus restartion (bukan tiktoken, bukan GPT-2)
 ├─ data: corpus slang buatan tangan + dipaketin 3 bagian (train_part1/2/3.bin)
 └─ personality: joker, roaster, unserious, tapi kadang gw perhatiin lu 🥹
```

## fitur yang *beneran ada* (bukan janji)

| fitur | status | cara |
|---|---|---|
| transformer asli dari scratch | ✅ | `restartion/model.py` — causal self-attention + SwiGLU, init random, dilatih dari 0 |
| BPE dari nol | ✅ | `scripts/train_tokenizer.py` — HF tokenizers BPE, vocab 8192 (4762 kepake), dilatih di corpus sendiri |
| memori asli | ✅ | `restartion/engine.py` — `memory/memory.json` persistent, ekstraksi fakta otomatis (nama, pet, like/hate), `<mem>` block dimasukin ke context tiap turn, recall lintas sesi |
| context 4k | ✅ | positional embedding 4096 posisi |
| kirim gambar yang lu kirim | ✅ | model nge-emit `<img>...</img>`. gambar cuma bisa dikirim ulang DI KONVO tempat dia dikirim — gambar konvo lain gak bakal bocor (di-filter di engine + dilatih di corpus: 371 nama file unik) |
| `download.jpeg` = mode marah | ✅ | dilatih: user ngiseng 3x → hulk ijo dikirim. engine juga ada fallback deterministik |
| kabar duka → *dance to pay le respect* | ✅ | dilatih ribuan contoh kondolan dark-humor + fallback regex |
| slang: twin, gng, stfu, sybau | ✅ | corpus penuh itu, normalize di `scripts/build_corpus.py` |

## jalanin

```bash
pip install -r requirements.txt

# CLI
python chat.py                          # atau: python -m restartion.chat
#   /mem   -> dump isi memori
#   /img videoframe_20260629_220129.jpg   -> attach gambar ke konvo
#   /reset /stats /quit

# WEB (dark metal UI)
python webui.py                         # buka http://localhost:7860
```

## struktur

```
restartion/
├── restartion/        # model.py, engine.py, chat.py, corpus/ (sumber corpus)
├── scripts/           # build_corpus, train_tokenizer, pack_data, train, export_i8
├── data/              # corpus_part1-3.txt + train_part1-3.bin (dipaketin 3 bagian!)
├── weights/           # restartion_part1/2/3.pt (fp32, lokalan) + _i8.pt (62.8MB, di github)
├── assets/            # download.jpeg (hulk/marah) + videoframe_20260629_220129.jpg
├── templates/ static/ # dark metal web UI
├── memory/            # memory.json (dibuat saat run pertama) + sessions/
└── screenshots/       # bukti training + percakapan per bagian
```

## training (dari nol, CPU 2 core pun jalan)

```bash
python scripts/build_corpus.py              # generate 5200 percakapan, split 3 bagian
python scripts/train_tokenizer.py           # BPE dari nol
python scripts/pack_data.py 1 2 3           # tokenisasi -> uint16 bin
python scripts/train.py --part 1 --steps 250 --tag part1        # bagian 1
python scripts/train.py --part 1 --steps 250 --tag part1 --resume   # lanjut
# bagian 2: --part 1,2 (gabung biar gak lupa)  |  bagian 3: --part 1,2,3
python scripts/export_i8.py part1           # int8 ~60MB, muat di github
```

## catatan chinchilla (docs/chinchilla.md)

chinchilla optimal = ±20 token per parameter → 57M params idealnya ±1.1B token.
korpus kita jauh lebih kecil (sengaja: personality bot yang *memorize* gaya ngomongnya,
bukan enciclopedia) — jadi kita overfit-by-design beberapa epoch di corpus template
+ fallback deterministik di engine biar personality gak pernah amblas. jujur soal ini,
bukan AI slop marketing.

## palette

dark metal: `#0a0b0d` bg · `#101318` panel · `#232a35` garis · `#ff4655` molten red · `#8b96a8` steel
