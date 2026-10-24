# restartion — github.io edition 🔩

transformer 57.44M parameter yang **dilatih dari nol** — sekarang jalan **100% di browser lu**, tanpa server.

- `model/restartion_i8.onnx` — 63 MB, hasil quantize int8 dari checkpoint `restartion_part3_i8.pt` (parity check: greedy 12/12 token identik dgn torch, max logit diff 0.31)
- `tokenizer.json` — BPE vocab 8192 (4762 kepake), dilatih dari nol — di-decode langsung di JS (GPT-2 style byte-level)
- `app.js` — ByteLevel BPE + ONNX Runtime Web (wasm) + sampling (temp 0.82 / top-k 45 / top-p 0.90 / rep-pen 1.15) + engine: memori asli (localStorage), galeri AI, leak guard, grief fallback, insult streak, name grounding

## rule main (boss spec v2)
- **user GAK BISA kirim gambar.** titik.
- **restartion yang pegang kamera**: konteksnya masuk akal → dia kirim `videoframe_20260629_220129.jpg` (frame film). marah banget → `download.jpeg` (si ijo). satu konvo max satu gambar.
- kabar duka → *dance to pay le respect* 🙏
- memori beneran: titip nama lu, refresh browser, dia tetep inget.

repo utama: [github.com/osnailcyargta-ctrl/restartion](https://github.com/osnailcyargta-ctrl/restartion)
