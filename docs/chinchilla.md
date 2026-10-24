# restartion × Chinchilla — catatan jujur soal scaling

## kenapa file ini ada
bosen nanya "chinchilla apan itu bagus buat ai gak" — jadi gini:

**Chinchilla** (Hoffmann et al., 2022, DeepMind) = paper yang ngasih tahu alokasi optimal
antara **ukuran model (N parameter)** dan **jumlah token training (D)**.
Rule-nya: **D ≈ 20 × N**. Model yang "compute-optimal" dilatih dengan token sebanyak
20x jumlah parameternya — bukan dilatih sepanjang mungkin kayak GPT-3 era.

## artinya buat restartion

```
N = 57.44M parameters
D chinchilla-optimal ≈ 20 × 57.44M ≈ 1.15 BILYUN token
```

**korpus restartion: ±500 ribu token** (5200 percakapan × 3 bagian).
Jadi kita latih di **~0.04% dari chinchilla-optimal.** JUJUR: ini jauh dari optimal.

## terus kenapa masih jalan?

1. **restartion bukan model pengetahuan — dia model kepribadian.**
   Chinchilla optimal itu buat model yang harus *tahu semua hal*.
   restartion cuma perlu *satu gaya ngomong*. Untuk itu, overfit sengaja
   (beberapa epoch di corpus template yang sama) justru perilaku yang diinginkan:
   dia HAVAL gaya ngomongnya sendiri, slang-nya konsisten, dan
   `dance to pay le respect`-nya gak pernah lupa.
2. **compute budget kita = 2 core CPU.** 1.15B token × 6×57M FLOPs ≈ 4×10¹⁷ FLOPs ≈
   berbulan-bulan di box ini. Nggak mungkin. Kita jalanin yang mungkin:
   ~4M token total (3 stage × ~1.3M) dengan cosine decay panjang.
3. **fallback deterministik di engine** menutup celah yang gak sempat dihafal model:
   kondolensi, hulk-marahan, filter gambar. Hybrid = personality selalu on-brand
   walau parameternya kecil.

## yang BENERAN diambil dari chinchilla di proyek ini

- **rasio param:token dihormati searah sebaliknya** — karena D kecil, kita gak
  ngembangin model lebih gede dari 57M (makin gede makin parah di data kecil,
  makin cepat hafal sampai Bobrok — classic overparameterized-small-data trap).
- **cosine decay + warmup** sesuai resep training-era-chinchilla.
- **banyak epoch kecil di data bersih > 1 epoch besar di data kotor**
  (kita gak ada GPU buat 1B token, jadi disiplin data > skala data).

## kalau mau chinchilla-real

butuh ±1.15B token corpus slang percakapan + GPU (misal 1×A100 ±36 jam).
skrip-nya sudah siap — tinggal feed `train_part*.bin` yang lebih besar dan
naikin `--steps`. arsitektur & pipeline gak berubah.
