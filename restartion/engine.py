"""
RESTARTION ENGINE — brain stem between the transformer and the world.
Loads the from-scratch checkpoint, builds memory-aware context, enforces the
boss's rules:

  1. REAL persistent memory  -> memory/memory.json + <mem>...</mem> context block
  2. images are AI-owned     -> the AI thinks and sends a pic when it makes sense.
     user cannot send anything. EVERY reply ends with an image: the one the model
     chose (gif/hulk) or a videoframe fallback when no tag matched.
  3. persona stays unserious -> sampling tuned for max chaos but on-script.
  4. no clock talk           -> "3am"/"6am"-style patterns are stripped (annoying).
  5. deepthink (secret)      -> best-of-N reranking = REAL longer thinking.
"""
import json
import os
import re
import time
import random
import torch
import torch.nn.functional as F
from tokenizers import Tokenizer

from .model import Restartion, RestartionConfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM_DIR = os.path.join(ROOT, "memory")
ASSETS = os.path.join(ROOT, "assets")

INSULTS = re.compile(
    r"\b(dumb|dumbass|stupid|idiot|useless|trash|garbage|stfu|kys|keys|loser|bego|goblok|tolol|"
    r"jelek|kasihan|kasian|mid|suck|sucks|worst|annoying|hate (u|you)|fuck (u|you)|fuck yourself|"
    r"fuck you|shit|bitch|ass|shut up|ngentot|anjing|gila)\b", re.I)
DEATH = re.compile(r"\b(died|passed away|passed|rest in peace|rip|meninggal|wafat|"
                   r"gugur|tiada|mati)\b", re.I)
NAME_PAT = re.compile(r"\b(?:my name(?:'s| is)?|call me|aku|gue|namaku|nama gue)\s+([A-Z][a-z]{1,15})")
PET_PAT = re.compile(r"\bmy (cat|dog|hamster|bird|rabbit)(?:'s name| named| is named| namanya)?\s+([A-Z][a-z]{1,15})")
LIKE_PAT = re.compile(r"\bi (?:really )?(love|like|hate|fear)\s+([a-z ][a-z ]{2,28}?)(?:[.,!?]|$)", re.I)

IMG_TAG = re.compile(r"<img>([^<]+)</img>")
USER_TAG = re.compile(r"<user>|<eos>")
BOT_TAG = re.compile(r"<bot>")

# ---------- the AI's own photo gallery (boss spec v2 + v3) ----------
# GUE (restartion) yang punya kamera. user GAK BISA ngirim apa-apa — user cuma bisa
# ngomong. KALAU konteksnya masuk akal, GUE yang mikir dan kirim foto yang nyambung.
# DAN: setiap reply yang gak punya tag gambar apapun -> fallback videoframe.
#   videoframe_20260629_220129.jpg      -> frame film. fallback "selalu ada gambar".
#   download.jpeg                       -> si ijo. keluar cuma pas gue beneran marah.
#   dance-dance-to-pay-respect.gif      -> gerakan sakral dance to pay le respect (tag <gif>).
GALLERY = ("videoframe_20260629_220129.jpg", "dance-dance-to-pay-respect.gif")
FALLBACK_PIC = "videoframe_20260629_220129.jpg"
ANGER_IMG = "download.jpeg"
RESPECT_GIF = "dance-dance-to-pay-respect.gif"
GIF_TAG = re.compile(r"<gif>([^<]+)</gif>")
ANY_MEDIA = re.compile(r"<(?:img|gif)>[^<]+</(?:img|gif)>")
# konteks yang bikin foto film-frame "nyambung" buat dikirim si ai
VIDEO_HINT = re.compile(r"\b(movie|film|nonton|cinema|bioskop|frame|scene|drakor|"
                        r"series|episode|netflix|trailer|videoframe|hwachua|anime|"
                        r"kw|mov|ending|plot|spoiler|reels|shorts)\b", re.I)
# greeting detector buat savage-greet injector (boss: jangan talking shit doang, nyapa balik)
GREET_RE = re.compile(
    r"^\s*(yo+|yoo|wsg|wassup|what'?s up|hey+|hi+|hello+|sup|halo|hai|pagi|siang|sore|malam)\b", re.I)
GREET_SHORT = re.compile(r"\b(lil bro|lil dawg|dawg)\b", re.I)
SAVAGE_MARK = re.compile(r"\b(lil bro|lil dawg|fuck|stfu|ugly|keys|trash|dumbass|bitch|shit)\b", re.I)
# user minta ai ngirim pic (user sendiri gak bisa ngsend)
ASK_PIC = re.compile(r"\b(send|kirim|show)\b[^.?!\n]{0,40}\b(pic|img|image|photo|foto|"
                     r"gambar|selfie|videoframe)s?\b|\b(pic|foto|gambar|selfie)s?\b[^^.?!\n]{0,24}"
                     r"\b(dong|lah|gih|donk|banh|gng|twin)\b", re.I)


def ensure_mem_dir():
    os.makedirs(MEM_DIR, exist_ok=True)
    p = os.path.join(MEM_DIR, "memory.json")
    if not os.path.exists(p):
        json.dump({"facts": {}, "images": {}, "history": [], "created": time.strftime("%Y-%m-%d %H:%M:%S")}, open(p, "w"), indent=2)
    return p


class Memory:
    """REAL persistent memory: survives restarts, stored as json, injected as <mem> block."""

    def __init__(self):
        self.path = ensure_mem_dir()
        self.d = json.load(open(self.path))

    def save(self):
        json.dump(self.d, open(self.path, "w"), indent=2)

    def set_fact(self, k, v):
        self.d["facts"][k] = v
        self.save()

    def fact(self, k, default=None):
        return self.d["facts"].get(k, default)

    def mem_block(self):
        """EXACTLY the training format: <mem>user: NAME | fact; fact</mem>"""
        facts = self.d["facts"]
        if not facts:
            return None
        head = f"user: {facts['name']}" if "name" in facts else ""
        rest = "; ".join(f"{k}: {v}" for k, v in facts.items() if k != "name")
        body = head + (" | " + rest if rest else "")
        return f"<mem>{body}</mem>"

    def extract(self, text):
        """pull facts out of user text — the bot REMEMBERS, not a gimmick."""
        m = NAME_PAT.search(text)
        if m and m.group(1).lower() not in {"guess", "what", "the", "just", "not", "so", "very", "really"}:
            self.set_fact("name", m.group(1))
        m = PET_PAT.search(text)
        if m:
            self.set_fact(f"{m.group(1)}", m.group(2))
        for m in LIKE_PAT.finditer(text):
            verb, obj = m.group(1).lower(), m.group(2).strip()
            if len(obj.split()) <= 4:
                self.set_fact(verb, obj)
        if re.search(r"\b(\d{1,2})\s*(?:am|pm)\b.*\b(?:sleep|bed)\b", text.lower()):
            self.set_fact("sleeps", "super late")
        if re.search(r"\b(gabut|bored)\b", text.lower()):
            self.set_fact("vibe", "always gabut")

    def note_history(self, line):
        self.d["history"].append(line)
        self.d["history"] = self.d["history"][-24:]
        self.save()

    def register_image(self, convo_id, fname):
        self.d["images"].setdefault(convo_id, [])
        if fname not in self.d["images"][convo_id]:
            self.d["images"][convo_id].append(fname)
            self.d["images"][convo_id] = self.d["images"][convo_id][-6:]
            self.save()


class Engine:
    def __init__(self, weights=None, threads=2):
        torch.set_num_threads(threads)
        self.tok = Tokenizer.from_file(os.path.join(ROOT, "data", "tokenizer.json"))
        self.ids = {t: i for i, t in enumerate(
                   ["<pad>", "<bos>", "<eos>", "<user>", "<bot>", "<mem>", "</mem>",
                    "<img>", "</img>"])}
        # weight resolver: persis -> varian _i8 -> part3_i8 -> part1_i8 (int8 export, dequant on load)
        cands = []
        if weights:
            cands += [weights, weights.replace(".pt", "_i8.pt")]
        cands += [os.path.join(ROOT, "weights", "restartion_part3_i8.pt"),
                  os.path.join(ROOT, "weights", "restartion_part3.pt"),
                  os.path.join(ROOT, "weights", "restartion_part1_i8.pt")]
        w = next((c for c in cands if c and os.path.exists(c)), None)
        if w is None:
            raise FileNotFoundError("no restartion weights found in weights/ (expected restartion_part3_i8.pt)")
        sd = torch.load(w, map_location="cpu")
        step_saved = sd.get("step", 0)
        cfgd = sd.get("cfg", {})
        # v2: vocab/ctx/heads dibaca DARI CHECKPOINT (gak ada lagi hardcode)
        cfg = RestartionConfig(
            vocab_size=cfgd.get("vocab_size", 6144), block_size=cfgd.get("block_size", 8192),
            n_layer=cfgd.get("n_layer", 10), n_head=cfgd.get("n_head", 16),
            n_embd=cfgd.get("n_embd", 640), ffn_mult=cfgd.get("ffn_mult", 2.7))
        self.model = Restartion(cfg)
        if "model_i8" in sd:  # int8 export: dequant langsung ke parameter (hemat peak RAM)
            mi8 = sd["model_i8"]
            params = dict(self.model.named_parameters())
            with torch.no_grad():
                for k, (q, s) in mi8.items():
                    if k not in params:
                        continue  # tied duplicate (head.weight == tok_emb.weight)
                    if s is not None:
                        params[k].copy_(q.float() * s)
                    else:
                        params[k].copy_(q)
            sd.clear(); mi8 = None
        else:
            self.model.load_state_dict(sd["model"])
        self.model.eval()
        self.mem = Memory()
        self.step = step_saved
        self.weights_path = w
        self.convo_turns = 0

    # ---------- context ----------
    def build_prompt(self, history, convo_id):
        """history: list of (role, text). returns prompt token ids."""
        mem = self.mem.mem_block()
        parts = ["<bos>"]
        if mem:
            parts.append(mem + "\n")
        for role, text in history[-14:]:
            parts.append(("<user>" if role == "user" else "<bot>") + text + "\n")
        parts.append("<bot>")
        s = "".join(parts)
        ids = self.tok.encode(s).ids
        cap = min(self.model.config.block_size - 2200, 6100)  # window praktis (RAM & latensi)
        if len(ids) > cap:
            ids = ids[-cap:]
        return torch.tensor([ids], dtype=torch.long)

    # ---------- image rule enforcement ----------
    def filter_images(self, text, convo_images):
        """strip any <img> that is not in this convo or the hulk."""
        def repl(m):
            name = m.group(1)
            if name in convo_images or name == "download.jpeg":
                return m.group(0)
            return ""
        return IMG_TAG.sub(repl, text)

    # ---------- main ----------
    def _gen_once(self, x, temp, max_new=140):
        eos, user, pad = self.ids["<eos>"], self.ids["<user>"], self.ids["<pad>"]
        with torch.no_grad():
            out = self.model.generate(
                x, max_new_tokens=max_new, temperature=temp, top_k=45, top_p=0.90,
                repetition_penalty=1.15, stop_token_ids=(eos, user),
                ban_token_ids=(pad,))
        new = out[0, x.shape[1]:].tolist()
        t = self.tok.decode(new, skip_special_tokens=False)
        for stopper in ("<user>", "<eos>", "<bos>"):
            t = t.split(stopper)[0]
        return t.strip()

    def _logprob(self, user_text, text):
        """rerank signal ASLI: seberapa yakin model sama kandidat ini (mean CE loss)."""
        s = f"<bos><user>{user_text}</user>\n<bot>{text}<eos>"
        ids = self.tok.encode(s).ids[:self.model.config.block_size - 1]
        idx = torch.tensor([ids], dtype=torch.long)
        m = self.model
        with torch.no_grad():
            pos = torch.arange(idx.size(1))
            x = m.tok_emb(idx) + m.pos_emb(pos)[None, :, :]
            for blk in m.blocks:
                x = blk(x)
            x = m.norm_f(x)
            logits = m.head(x)                    # [1, T, V]
        lg = logits[:, :-1, :].reshape(-1, logits.size(-1))
        tg = idx[:, 1:].reshape(-1)
        return float(F.cross_entropy(lg, tg))

    def _score(self, user_text, text, insult, grief):
        """heuristic + model confidence. dipakai deepthink buat milih kandidat TERBAIK."""
        if not text:
            return -1e9
        s = 0.0
        low = text.lower()
        if re.search(r"<mem>|</mem>|user:|\| [a-z]+:", low):
            s -= 12.0
        if re.search(r"\b\d{1,2}\s?(am|pm)\b", low):
            s -= 8.0
        n = len(text)
        if 18 <= n <= 280:
            s += 2.0
        if len(text.split()) < 3:
            s -= 3.0
        if n < 14:
            s -= 6.0  # jawaban kelaparan ("ayooo") gak layak menang deepthink
        if re.search(r"\b(dawg|lil bro|lil dawg|keys|crine|crying|ts)\b", low):
            s += 0.5
        lines = [l for l in text.split("\n") if l.strip()]
        if len(lines) != len(set(lines)):
            s -= 2.0
        if insult and re.search(r"\b(lil bro|dawg|keys|ur|stfu|fuck|bitch)\b", low):
            s += 1.5
        if grief and ("respect" in low or "<gif>" in low):
            s += 2.5
        # gagap token kasar ( karakter aneh bertumpuk )
        if re.search(r"(.)\1{6,}", text):
            s -= 2.0
        s -= min(8.0, self._logprob(user_text, text))  # model confidence: loss rendah = kandidat enak
        return s

    def reply(self, user_text, history, convo_id="default", images=None, deepthink=False):
        """user CANNOT send anything (boss spec v2/v3). AI owns the gallery AND the gif.
        deepthink=True -> best-of-N reranking, beneran mikir lebih lama, hasil dipilih."""
        images = None  # noqa: user uploads are not a thing anymore
        t0 = time.time()
        name_before = self.mem.fact("name")
        self.mem.extract(user_text)
        just_named = bool(self.mem.fact("name")) and not name_before
        real_name = self.mem.fact("name")
        convo_imgs = set(self.mem.d["images"].get(convo_id, []))  # what the AI already sent here
        insult = bool(INSULTS.search(user_text))
        grief = bool(DEATH.search(user_text))
        self.convo_turns += 1
        if self.convo_turns % 14 == 0 and self.mem.d["facts"]:
            self.mem.note_history(f"talked with {self.mem.fact('name', 'twin')} ({time.strftime('%Y-%m-%d')})")

        x = self.build_prompt(history, convo_id)

        n_cand = 5 if deepthink else 1
        temps = [0.82, 0.70, 0.90, 0.62, 0.78] if deepthink else [0.82]
        cands = []
        for i in range(n_cand):
            cands.append(self._gen_once(x, temps[i % len(temps)]))
        def clean(t):
            t = t.strip()
            if re.search(r"<mem>|</mem>|user:|\| [a-z]+:", t):
                t2 = self._gen_once(x, 0.62)
                if not re.search(r"<mem>|</mem>|user:|\| [a-z]+:", t2):
                    return t2
                t = "\n".join(l for l in t.split("\n") if not re.search(r"<mem>|</mem>|user:", l))
            return t.strip()
        cands = [clean(c) for c in cands]
        if deepthink:
            scored = [(self._score(user_text, c, insult, grief), i) for i, c in enumerate(cands)]
            scored.sort(reverse=True)
            text = cands[scored[0][1]]
        else:
            text = cands[0]
        think_secs = time.time() - t0
        self.last_think_secs = think_secs
        self.last_deepthink = bool(deepthink)

        # boss directive: SAVAGE GREET — user nyapa -> AI nyapa balik gaya bebas
        # (contoh boss: "yo dawg" -> "stfu lil bro go fuck yourself"), bukan dumbass diam.
        greet = bool(GREET_RE.search(user_text)) or (
            len(user_text) < 36 and bool(GREET_SHORT.search(user_text)))
        if greet and not insult and not grief and not just_named \
                and not SAVAGE_MARK.search(text) and random.random() < 0.55:
            from .corpus.lines_extra import SAVAGE_GREET_A
            line = random.choice(SAVAGE_GREET_A)
            if real_name and random.random() < 0.35:
                line = line.replace("lil bro", f"lil {real_name}").replace(
                    "lil dawg", f"lil {real_name}")
            text = line
        # mem-greet assist: nama udah dikenal + user balik nyapa -> "Rizky!!! the legend returns"
        if greet and real_name and not just_named and not insult and not grief \
                and real_name not in text and random.random() < 0.5:
            from .corpus.lines_memory import MEM_GREETING_A
            text = random.choice(MEM_GREETING_A).format(name=real_name)

        # surface cleanup — tag media utuh di-stash, bersihin sisanya, restore
        _stash = []
        def _hold(m):
            _stash.append(m.group(0))
            return f"%%M{len(_stash)-1}%%"
        text = ANY_MEDIA.sub(_hold, text)
        text = re.sub(r"</?(mem|bot)>", " ", text)
        text = re.sub(r"</?(?:img|gif)>", " ", text)   # orphan half-tags (pasangan asli udah di-stash)
        text = re.sub(r"\n+", "\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text).strip()
        for i, mt in enumerate(_stash):
            text = text.replace(f"%%M{i}%%", mt)

        # buang pola jam (boss: annoying & unfunny)
        text = re.sub(r"\b\d{1,2}\s?(am|pm)\b", "late night", text, flags=re.I)

        # ---- enforce image rules: cuma galeri, max 1 media per reply ----
        def _keep(m):
            name = m.group(1)
            if name == ANGER_IMG or name == RESPECT_GIF:
                return m.group(0)
            if name in GALLERY:
                return m.group(0)
            return ""
        text = IMG_TAG.sub(_keep, text)
        text = GIF_TAG.sub(_keep, text)
        seen_media = False
        def _one(m):
            nonlocal seen_media
            if seen_media:
                return ""
            seen_media = True
            return m.group(0)
        text = ANY_MEDIA.sub(_one, text)

        # register what the AI actually sent (convo scoping memory)
        for name in IMG_TAG.findall(text) + GIF_TAG.findall(text):
            self.mem.register_image(convo_id, name)

        # persona guarantees (deterministic fallbacks, the model is trained for these too)
        sent_media = ANY_MEDIA.findall(text)
        if grief:
            if "<gif>" not in text:
                text = text + " <gif>" + RESPECT_GIF + "</gif>"
        streak = 0
        for role, t in reversed(history):
            if role == "user" and INSULTS.search(t):
                streak += 1
            elif role == "user":
                break
        if streak >= 3 and not ANY_MEDIA.search(text) and not grief:
            # really mad -> keys spam + the hulk comes out (also trained into the model)
            if streak >= 4 or (streak == 3 and random.random() < 0.5):
                text = text + " keys keys keys. <img>" + ANGER_IMG + "</img>"
            else:
                text = text + " keys keys keys."

        # ---- BOSS RULE v3: SELALU ada gambar. kalau gak ada tag yang cocok -> videoframe ----
        if not ANY_MEDIA.search(text) and not grief:
            text = text + " <img>" + FALLBACK_PIC + "</img>"

        # register final media (termasuk fallback)
        for name in IMG_TAG.findall(text) + GIF_TAG.findall(text):
            self.mem.register_image(convo_id, name)

        # name grounding: corpus names are placeholders; the REAL name lives in memory
        if real_name:
            from .corpus.lines_memory import MEM_NAMES as _CORPUS_NAMES
            if real_name not in text:
                for wrong in _CORPUS_NAMES:
                    if wrong != real_name and re.search(rf"\b{wrong}\b", text):
                        text = re.sub(rf"\b{wrong}\b", real_name, text)
                        break

        if not text:
            text = random.choice(["... twin the void answered. try again banh.", "bruh the tokens slipped. say that again gng 😭"])
        return text
