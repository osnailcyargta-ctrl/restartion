"""
Export restartion (57.44M, from-scratch transformer) ke ONNX int8 buat GitHub Pages.
- fp32 ONNX dulu (dequant dari part3_i8.pt), dynamic sequence length
- manual attention (no SDPA op) biar ORT Web-compatible
- quantize_dynamic -> int8 (~63MB, di bawah limit 100MB/file Pages)
- parity check vs torch (logits + greedy 12 token)
output: site/model/restartion_i8.onnx
"""
import math
import os
import sys
import types

import torch
import torch.nn.functional as F

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from restartion.model import Restartion, RestartionConfig  # noqa: E402,F401
from restartion.engine import Engine  # noqa: E402

OUT_DIR = os.path.join(ROOT, "site", "model")
os.makedirs(OUT_DIR, exist_ok=True)


def attn_forward_manual(self, x):
    """SDPA diganti math manual — hasil numerik sama, export aman untuk ORT Web."""
    B, T, C = x.shape
    q, k, v = self.qkv(x).split(self.dim, dim=2)
    q = q.view(B, T, self.n_heads, C // self.n_heads).transpose(1, 2)
    k = k.view(B, T, self.n_heads, C // self.n_heads).transpose(1, 2)
    v = v.view(B, T, self.n_heads, C // self.n_heads).transpose(1, 2)
    att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(k.size(-1)))
    mask = torch.triu(torch.ones(T, T, dtype=torch.bool), diagonal=1)
    att = att.masked_fill(mask, float("-inf"))
    att = F.softmax(att, dim=-1)
    y = att @ v
    y = y.transpose(1, 2).contiguous().view(B, T, C)
    return self.resid_drop(self.proj(y))


class ExportWrap(torch.nn.Module):
    """idx:int64[1,T] -> logits last pos :float[1,V]"""

    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, idx):
        logits, _ = self.m(idx)  # targets=None path -> head(x[:, [-1], :])
        return logits[:, -1, :]


def main():
    torch.manual_seed(0)
    eng = Engine()  # resolver -> part3_i8, dequant on load
    model = eng.model.eval()
    for blk in model.blocks:
        blk.attn.forward = types.MethodType(attn_forward_manual, blk.attn)

    fp32_path = os.path.join(OUT_DIR, "restartion_fp32.onnx")
    i8_path = os.path.join(OUT_DIR, "restartion_i8.onnx")

    if os.path.exists(i8_path):
        print(f"int8 exists ({os.path.getsize(i8_path)/1e6:.1f} MB) — skip export")
    else:
        dummy = torch.randint(0, eng.model.config.vocab_size, (1, 16), dtype=torch.long)
        print("exporting fp32 onnx ...")
        torch.onnx.export(
            ExportWrap(model).eval(), (dummy,), fp32_path,
            input_names=["ids"], output_names=["logits"],
            dynamic_axes={"ids": {1: "seq"}, "logits": {1: "seq"}},
            opset_version=17, dynamo=False, do_constant_folding=True,
        )
        print(f"  fp32: {os.path.getsize(fp32_path)/1e6:.1f} MB")

        print("quantizing -> int8 ...")
        from onnxruntime.quantization import quantize_dynamic, QuantType
        quantize_dynamic(fp32_path, i8_path, weight_type=QuantType.QInt8)
        os.remove(fp32_path)
        print(f"  int8: {os.path.getsize(i8_path)/1e6:.1f} MB")

    # ---------- parity check ----------
    print("parity check ...")
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(os.path.join(ROOT, "data", "tokenizer.json"))
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = ort.InferenceSession(i8_path, so, providers=["CPUExecutionProvider"])

    prompt = "<bos><user>yo gng what's up<bot>"
    ids = torch.tensor([tok.encode(prompt).ids], dtype=torch.long)

    with torch.no_grad():
        ref_logits, _ = model(ids)
        ref_last = ref_logits[0, -1]  # [V]
    ort_last = sess.run(["logits"], {"ids": ids.numpy()})[0][0]  # [V]
    diff = float(np.abs(ref_last.numpy() - ort_last).max())
    print(f"  max |torch - ort_int8| = {diff:.4f}")

    cur = ids.clone()
    agree = 0
    for _ in range(12):
        with torch.no_grad():
            l_t, _ = model(cur)
        top_t = int(l_t[0, -1].argmax())
        top_o = int(sess.run(["logits"], {"ids": cur.numpy()})[0][0].argmax())
        if top_t != top_o:
            break
        agree += 1
        cur = torch.cat([cur, torch.tensor([[top_t]], dtype=torch.long)], dim=1)
    print(f"  greedy agreement: {agree}/12 tokens")
    ok = diff < 1.5 and agree >= 10
    print("PARITY OK" if ok else "PARITY WARN — cek manual")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
