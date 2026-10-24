"""Tokenize corpus parts -> packed uint16 bin files (GPT-2 style packing, rows of 256)."""
import os
import numpy as np
from tokenizers import Tokenizer

ROOT = "/home/z/my-project/restartion"
ROW = 256  # packing row length for training (inference ctx is 4096)

def pack(part, row=ROW):
    tok = Tokenizer.from_file(os.path.join(ROOT, "data", "tokenizer.json"))
    pad = tok.token_to_id("<pad>")
    txt = open(os.path.join(ROOT, "data", f"corpus_part{part}.txt")).read()
    convos = [c for c in txt.split("\n") if c.strip()]
    ids = []
    for c in convos:
        e = tok.encode(c)
        ids.extend(e.ids)
    n_full = len(ids) // row
    arr = np.array(ids[: n_full * row], dtype=np.uint16).reshape(n_full, row)
    out = os.path.join(ROOT, "data", f"train_part{part}.bin")
    arr.tofile(out)
    print(f"part{part}: {len(convos)} convos -> {len(ids)} tokens -> {arr.shape} saved {out}")
    return arr.shape[0]

if __name__ == "__main__":
    import sys
    parts = [int(x) for x in sys.argv[1:]] or [1, 2, 3]
    for p in parts:
        pack(p)
