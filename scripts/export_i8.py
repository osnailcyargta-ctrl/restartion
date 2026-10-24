"""Export fp32 weights -> int8 (~4x smaller, fits GitHub <100MB, runs everywhere)."""
import os
import sys
import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def quant_i8(t):
    scale = t.abs().max().clamp(min=1e-8) / 127.0
    q = (t / scale).round().clamp(-127, 127).to(torch.int8)
    return q, scale

def main(src, dst):
    sd = torch.load(src, map_location="cpu")
    out = {"cfg": sd["cfg"], "step": sd.get("step", 0), "model_i8": {}}
    for k, v in sd["model"].items():
        if v.dtype in (torch.float32, torch.float16) and v.numel() > 4096:
            q, s = quant_i8(v.float())
            out["model_i8"][k] = (q, s)
        else:
            out["model_i8"][k] = (v, None)
    torch.save(out, dst)
    mb = os.path.getsize(dst) / 1e6
    print(f"saved {dst} ({mb:.1f} MB, src {os.path.getsize(src)/1e6:.1f} MB) @ step {sd.get('step')}")

if __name__ == "__main__":
    part = sys.argv[1] if len(sys.argv) > 1 else "part1"
    main(os.path.join(ROOT, "weights", f"restartion_{part}.pt"),
         os.path.join(ROOT, "weights", f"restartion_{part}_i8.pt"))
