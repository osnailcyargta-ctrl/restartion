"""
RESTARTION MODEL — a real decoder-only transformer, written from scratch.
No GPT-2 weights, no pretrained anything. Trained from a cold init on the
restartion slang corpus. This is the actual thing, not a wrapper.

Architecture (restartion v2 ~58.7M params):
  - decoder-only, causal self-attention, learned positional embeddings (ctx 8192)
  - RMSNorm (pre-norm) + SwiGLU MLP  (llama-style blocks, written by hand)
  - tied input/output embeddings, 16 attention heads
  - BPE tokenizer trained from scratch (5792 real tokens, model slot 6144) on the restartion corpus v2
"""
import math
import torch
import torch.nn as nn
import torch.nn.functional as F


class RMSNorm(nn.Module):
    def __init__(self, dim, eps=1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x):
        norm = x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)
        return norm * self.weight


class CausalSelfAttention(nn.Module):
    def __init__(self, dim, n_heads, dropout=0.0):
        super().__init__()
        assert dim % n_heads == 0
        self.n_heads = n_heads
        self.dim = dim
        self.qkv = nn.Linear(dim, 3 * dim, bias=False)
        self.proj = nn.Linear(dim, dim, bias=False)
        self.dropout = dropout
        self.attn_drop = nn.Dropout(dropout)
        self.resid_drop = nn.Dropout(dropout)

    def forward(self, x):
        B, T, C = x.shape
        q, k, v = self.qkv(x).split(self.dim, dim=2)
        # (B, T, C) -> (B, nh, T, hs)
        q = q.view(B, T, self.n_heads, C // self.n_heads).transpose(1, 2)
        k = k.view(B, T, self.n_heads, C // self.n_heads).transpose(1, 2)
        v = v.view(B, T, self.n_heads, C // self.n_heads).transpose(1, 2)
        # flash attention (scaled_dot_product_attention) — still our own math around it
        y = F.scaled_dot_product_attention(
            q, k, v,
            attn_mask=None, dropout_p=self.dropout if self.training else 0.0,
            is_causal=True,
        )
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        return self.resid_drop(self.proj(y))


class SwiGLU(nn.Module):
    def __init__(self, dim, hidden):
        super().__init__()
        self.w_gate = nn.Linear(dim, hidden, bias=False)
        self.w_up = nn.Linear(dim, hidden, bias=False)
        self.w_down = nn.Linear(hidden, dim, bias=False)

    def forward(self, x):
        return self.w_down(F.silu(self.w_gate(x)) * self.w_up(x))


class Block(nn.Module):
    def __init__(self, dim, n_heads, ffn_mult, dropout):
        super().__init__()
        self.n1 = RMSNorm(dim)
        self.attn = CausalSelfAttention(dim, n_heads, dropout)
        self.n2 = RMSNorm(dim)
        hidden = int(ffn_mult * dim)
        # make hidden divisible by 8 for tensor cores (harmless on cpu)
        hidden = int(8 * math.ceil(hidden / 8))
        self.mlp = SwiGLU(dim, hidden)

    def forward(self, x):
        x = x + self.attn(self.n1(x))
        x = x + self.mlp(self.n2(x))
        return x


class RestartionConfig:
    def __init__(
        self,
        vocab_size=8192,
        block_size=4096,     # 4k context window, as requested
        n_layer=10,
        n_head=10,
        n_embd=640,
        ffn_mult=2.7,        # swiglu hidden ~1728
        dropout=0.0,
    ):
        self.vocab_size = vocab_size
        self.block_size = block_size
        self.n_layer = n_layer
        self.n_head = n_head
        self.n_embd = n_embd
        self.ffn_mult = ffn_mult
        self.dropout = dropout


class Restartion(nn.Module):
    def __init__(self, config: RestartionConfig):
        super().__init__()
        self.config = config
        self.tok_emb = nn.Embedding(config.vocab_size, config.n_embd)
        self.pos_emb = nn.Embedding(config.block_size, config.n_embd)
        self.drop = nn.Dropout(config.dropout)
        self.blocks = nn.ModuleList([
            Block(config.n_embd, config.n_head, config.ffn_mult, config.dropout)
            for _ in range(config.n_layer)
        ])
        self.norm_f = RMSNorm(config.n_embd)
        self.head = nn.Linear(config.n_embd, config.vocab_size, bias=False)
        # tie weights (input embedding == output head)
        self.head.weight = self.tok_emb.weight
        self.apply(self._init_weights)
        # scaled init on residual projections, gpt-style
        for name, p in self.named_parameters():
            if name.endswith("proj.weight") or name.endswith("w_down.weight"):
                nn.init.normal_(p, mean=0.0, std=0.02 / math.sqrt(2 * config.n_layer))

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def num_params(self, non_embedding=True):
        n = sum(p.numel() for p in self.parameters())
        if non_embedding:
            n -= self.pos_emb.weight.numel()  # tok_emb is tied to head, keep counted once
        return n

    def forward(self, idx, targets=None):
        B, T = idx.shape
        assert T <= self.config.block_size, f"seq {T} > context {self.config.block_size}"
        pos = torch.arange(T, device=idx.device)
        x = self.tok_emb(idx) + self.pos_emb(pos)[None, :, :]
        x = self.drop(x)
        for block in self.blocks:
            x = block(x)
        x = self.norm_f(x)
        if targets is not None:
            logits = self.head(x)
            loss = F.cross_entropy(
                logits.view(-1, logits.size(-1)), targets.view(-1), ignore_index=-100
            )
            return logits, loss
        else:
            logits = self.head(x[:, [-1], :])  # only last position needed
            return logits, None

    @torch.no_grad()
    def generate(
        self,
        idx,
        max_new_tokens=96,
        temperature=0.9,
        top_k=64,
        top_p=0.95,
        repetition_penalty=1.15,
        stop_token_ids=(),
        ban_token_ids=(),
    ):
        self.eval()
        out = idx
        for _ in range(max_new_tokens):
            idx_cond = out[:, -self.config.block_size:]
            logits, _ = self(idx_cond)
            logits = logits[:, -1, :] / max(temperature, 1e-5)
            # repetition penalty (ctrl-style)
            if repetition_penalty and repetition_penalty != 1.0:
                for b in range(out.size(0)):
                    seen = set(out[b].tolist())
                    for t in seen:
                        logits[b, t] = logits[b, t] / repetition_penalty if logits[b, t] > 0 else logits[b, t] * repetition_penalty
            for t in ban_token_ids:
                logits[:, t] = float("-inf")
            # top-k
            if top_k is not None and top_k > 0:
                v, _ = torch.topk(logits, min(top_k, logits.size(-1)))
                logits[logits < v[:, [-1]]] = float("-inf")
            # top-p (nucleus)
            if top_p is not None and 0.0 < top_p < 1.0:
                probs = F.softmax(logits, dim=-1)
                sorted_probs, sorted_idx = torch.sort(probs, descending=True, dim=-1)
                cum = sorted_probs.cumsum(dim=-1)
                mask = cum - sorted_probs > top_p
                sorted_probs[mask] = 0.0
                sorted_probs = sorted_probs / sorted_probs.sum(dim=-1, keepdim=True)
                next_tok = sorted_idx.gather(-1, torch.multinomial(sorted_probs, 1))
            else:
                probs = F.softmax(logits, dim=-1)
                next_tok = torch.multinomial(probs, 1)
            if next_tok.item() in stop_token_ids:
                break
            out = torch.cat((out, next_tok), dim=1)
        return out


def small_config():
    """~58.7M params (v2): vocab 6144, ctx 8192, 16 heads. RAM runtime <= 750MB."""
    return RestartionConfig(vocab_size=6144, block_size=8192, n_layer=10, n_head=16, n_embd=640, ffn_mult=2.7)


if __name__ == "__main__":
    cfg = small_config()
    m = Restartion(cfg)
    n = m.num_params(non_embedding=False)
    print(f"restartion-small: {n/1e6:.1f}M parameters (ctx {cfg.block_size}, {cfg.n_layer}L, d={cfg.n_embd}, {cfg.n_head}H)")
