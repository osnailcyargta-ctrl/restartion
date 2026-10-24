"""
RESTARTION trainer — cold start, no pretrained anything. AdamW + warmup + cosine.
Designed for weak CPU boxes: resumes from checkpoint, runs N steps per invocation,
logs to weights/train.log. usage:
  python train.py --part 1 --steps 900 [--resume]
"""
import argparse
import math
import os
import sys
import time

import torch
from torch.utils.data import DataLoader, TensorDataset

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from restartion.model import Restartion, RestartionConfig

ROOT = "/home/z/my-project/restartion"
ROW = 256

def get_data(part, row=ROW):
    """part can be '1' or '1,2' or '1,2,3' (mixed = rehearsal so the bot never forgets).
    special name 'long' = train_long.bin (row 512, ctx positions)."""
    import numpy as np
    if str(part) == "long":
        path = os.path.join(ROOT, "data", "train_long.bin")
        flat = np.fromfile(path, dtype=np.uint16)
        arr = flat[: (len(flat) // row) * row].reshape(-1, row)
    else:
        chunks = []
        for p in str(part).split(","):
            path = os.path.join(ROOT, "data", f"train_part{p.strip()}.bin")
            chunks.append(np.fromfile(path, dtype=np.uint16).reshape(-1, row))
        arr = np.concatenate(chunks, axis=0)
    x = torch.from_numpy(arr.astype(np.int64))
    return TensorDataset(x[:, :-1], x[:, 1:])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=900)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--lr", type=float, default=8e-4)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--tag", type=str, default=None)
    ap.add_argument("--part", type=str, default="1")  # accepts "1" or "1,2" or "long"
    ap.add_argument("--init-from", type=str, default=None)
    ap.add_argument("--row", type=int, default=ROW)
    args = ap.parse_args()
    init_from = args.init_from

    torch.manual_seed(1337 + sum(int(c) for c in str(args.part) if c.isdigit()))
    torch.set_num_threads(2)
    dev = "cpu"

    # restartion v2: vocab 6144 (5792 real tokens), ctx 8192, 16 heads — RAM <= 750MB runtime
    cfg = RestartionConfig(vocab_size=6144, block_size=8192, n_layer=10,
                           n_head=16, n_embd=640, ffn_mult=2.7, dropout=0.0)
    model = Restartion(cfg).to(dev)
    nparam = sum(p.numel() for p in model.parameters())
    print(f"restartion-small: {nparam/1e6:.2f}M params | ctx {cfg.block_size} | layers {cfg.n_layer} | d {cfg.n_embd}")

    tag = args.tag or f"part{args.part}"
    ckpt = os.path.join(ROOT, "weights", f"restartion_{tag}.pt")
    logf = os.path.join(ROOT, "weights", "train.log")
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, betas=(0.9, 0.95), weight_decay=0.1)

    if init_from:
        sd0 = torch.load(init_from, map_location=dev)
        model.load_state_dict(sd0["model"])
        print(f"init-from {init_from} (fresh optimizer)")

    start_step = 0
    if args.resume and os.path.exists(ckpt):
        sd = torch.load(ckpt, map_location=dev)
        model.load_state_dict(sd["model"])
        if "opt" in sd:
            opt.load_state_dict(sd["opt"])
        start_step = sd.get("step", 0)
        print(f"resumed from {ckpt} @ step {start_step}")

    ds = get_data(args.part, args.row)
    dl = DataLoader(ds, batch_size=args.batch, shuffle=True, drop_last=True)
    it = iter(dl)

    warmup = 40
    total = args.steps
    def lr_at(s):
        s = s - start_step
        if s < warmup:
            return args.lr * (s + 1) / warmup
        p = (s - warmup) / max(1, total - warmup)
        return args.lr * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(p, 1.0))))

    model.train()
    t0 = time.time()
    losses = []
    log = open(logf, "a")
    log.write(f"=== {tag} run: steps {start_step}->{start_step+total} | params {nparam/1e6:.2f}M ===\n")
    log.flush()
    for step in range(start_step, start_step + total):
        lr = lr_at(step)
        for g in opt.param_groups:
            g["lr"] = lr
        try:
            xb, yb = next(it)
        except StopIteration:
            it = iter(dl)
            xb, yb = next(it)
        _, loss = model(xb, yb)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        losses.append(loss.item())
        if (step + 1) % 10 == 0 or step == start_step:
            dt = time.time() - t0
            msg = (f"[{tag}] step {step+1}/{start_step+total} | loss {loss.item():.3f} | "
                   f"avg10 {sum(losses[-10:])/len(losses[-10:]):.3f} | lr {lr:.2e} | {dt/(step-start_step+1):.2f}s/step")
            print(msg, flush=True)
            log.write(msg + "\n")
            log.flush()
        if (step + 1) % 50 == 0 or (step + 1) == start_step + total:
            torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "step": step + 1, "cfg": vars(cfg) if hasattr(cfg, "__dict__") else cfg.__dict__}, ckpt)
    torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "step": start_step + total, "cfg": cfg.__dict__}, ckpt)
    print(f"saved {ckpt} @ step {start_step+total} | final avg loss {sum(losses[-30:])/30:.3f}")
    log.write(f"saved {ckpt} @ step {start_step+total} | final avg30 {sum(losses[-30:])/30:.3f}\n")
    log.close()

if __name__ == "__main__":
    main()
