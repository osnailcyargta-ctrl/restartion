"""
RESTARTION ENGINE — brain stem between the transformer and the world.
Loads the from-scratch checkpoint, builds memory-aware context, enforces the
boss's rules:

  1. REAL persistent memory  -> memory/memory.json + <mem>...</mem> context block
  2. images are convo-scoped -> the bot can only re-send an image that exists in
     the CURRENT conversation (or download.jpeg = hulk = anger). any other
     <img> hallucination gets stripped. "videoframe" never leaks into a convo
     that has a different image.
  3. persona stays unserious -> sampling tuned for max chaos but on-script.
"""
import json
import os
import re
import time
import random
import torch
from tokenizers import Tokenizer

from .model import Restartion, RestartionConfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM_DIR = os.path.join(ROOT, "memory")
ASSETS = os.path.join(ROOT, "assets")

INSULTS = re.compile(
    r"\b(dumb|stupid|idiot|useless|trash|garbage|stfu|kys|loser|bego|goblok|tolol|"
    r"jelek|kasihan|kasian|mid|suck|sucks|worst|annoying|hate (u|you)|fuck (u|you)|"
    r"fuck you|shut up|ngentot|anjing|gila|suck)\b", re.I)
DEATH = re.compile(r"\b(died|passed away|passed|rest in peace|rip|meninggal|wafat|"
                   r"gugur|tiada|mati)\b", re.I)
NAME_PAT = re.compile(r"\b(?:my name(?:'s| is)|call me|aku|gue|namaku|nama gue)\s+([A-Z][a-z]{1,15})")
PET_PAT = re.compile(r"\bmy (cat|dog|hamster|bird|rabbit)(?:'s name| named| is named| namanya)?\s+([A-Z][a-z]{1,15})")
LIKE_PAT = re.compile(r"\bi (?:really )?(love|like|hate|fear)\s+([a-z ][a-z ]{2,28}?)(?:[.,!?]|$)", re.I)

IMG_TAG = re.compile(r"<img>([^<]+)</img>")
USER_TAG = re.compile(r"<user>|<eos>")
BOT_TAG = re.compile(r"<bot>")

# ---------- the AI's own photo gallery (boss spec v2) ----------
# GUE (restartion) yang punya kamera. user GAK BISA ngirim apa-apa — user cuma bisa
# ngomong. KALAU konteksnya masuk akal, GUE yang mikir dan kirim foto yang nyambung.
#   videoframe_20260629_220129.jpg -> frame film. ada di semua konvo, TAPI gak bakal
#                                    muncul di konvo/message yang udah punya gambar lain.
#   download.jpeg                  -> si ijo. keluar cuma pas gue beneran marah.
GALLERY = ("videoframe_20260629_220129.jpg",)
ANGER_IMG = "download.jpeg"
# konteks yang bikin foto film-frame "nyambung" buat dikirim si ai
VIDEO_HINT = re.compile(r"\b(movie|film|nonton|cinema|bioskop|frame|scene|drakor|"
                        r"series|episode|netflix|trailer|videoframe|hwachua|anime|"
                        r"kw|mov|ending|plot|spoiler|reels|shorts)\b", re.I)
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
        cands += [os.path.join(ROOT, "weights", "restartion_part3.pt"),
                  os.path.join(ROOT, "weights", "restartion_part3_i8.pt"),
                  os.path.join(ROOT, "weights", "restartion_part1_i8.pt")]
        w = next((c for c in cands if c and os.path.exists(c)), None)
        if w is None:
            raise FileNotFoundError("no restartion weights found in weights/ (expected restartion_part3_i8.pt)")
        sd = torch.load(w, map_location="cpu")
        cfgd = sd.get("cfg", {})
        cfg = RestartionConfig(
            vocab_size=8192, block_size=4096,
            n_layer=cfgd.get("n_layer", 10), n_head=cfgd.get("n_head", 10),
            n_embd=cfgd.get("n_embd", 640), ffn_mult=cfgd.get("ffn_mult", 2.7))
        self.model = Restartion(cfg)
        if "model_i8" in sd:  # int8 export: dequant on load
            state = {}
            for k, (q, s) in sd["model_i8"].items():
                state[k] = q.float() * s if s is not None else q
            self.model.load_state_dict(state)
        else:
            self.model.load_state_dict(sd["model"])
        self.model.eval()
        self.mem = Memory()
        self.step = sd.get("step", 0)
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
        if len(ids) > 3900:  # 4k window, keep headroom for generation
            ids = ids[-3900:]
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
    def reply(self, user_text, history, convo_id="default", images=None):
        """user CANNOT send images (boss spec v2) — `images` param kept for compat, ignored.
        the AI owns the gallery and decides when a pic makes sense."""
        images = None  # noqa: user uploads are not a thing anymore
        self.mem.extract(user_text)
        convo_imgs = set(self.mem.d["images"].get(convo_id, []))  # what the AI already sent here
        insult = bool(INSULTS.search(user_text))
        grief = bool(DEATH.search(user_text))
        self.convo_turns += 1
        if self.convo_turns % 14 == 0 and self.mem.d["facts"]:
            self.mem.note_history(f"talked with {self.mem.fact('name', 'twin')} ({time.strftime('%Y-%m-%d')})")

        x = self.build_prompt(history, convo_id)
        eos = self.ids["<eos>"]; user = self.ids["<user>"]
        pad = self.ids["<pad>"]
        def gen(temp):
            with torch.no_grad():
                out = self.model.generate(
                    x, max_new_tokens=140, temperature=temp, top_k=45, top_p=0.90,
                    repetition_penalty=1.15, stop_token_ids=(eos, user),
                    ban_token_ids=(pad,))
            new = out[0, x.shape[1]:].tolist()
            t = self.tok.decode(new, skip_special_tokens=False)
            for stopper in ("<user>", "<eos>", "<bos>"):
                t = t.split(stopper)[0]
            return t.strip()
        text = gen(0.82)
        # mem-block leak guard: model should never SHOW the mem block, only USE it
        if re.search(r"<mem>|</mem>|user:|\| [a-z]+:", text):
            text = gen(0.62)
            if re.search(r"<mem>|</mem>|user:|\| [a-z]+:", text):
                lines = [l for l in text.split("\n") if not re.search(r"<mem>|</mem>|user:", l)]
                text = " ".join(lines).strip()
        text = text.strip()


        # surface cleanup
        text = re.sub(r"</?(mem|bot)>|\n+", lambda m: "\n" if m.group(0) == "\n" else " ", text).strip()

        # ---- the AI THINKS: kirim foto kalau konteksnya masuk akal (boss spec v2) ----
        # rule: videoframe boleh di semua konvo, TAPI gak boleh nongol di konvo yang
        # udah punya gambar lain (hulk). download.jpeg = marah, selalu boleh.
        other_img_in_convo = any(i != ANGER_IMG for i in convo_imgs)
        if (VIDEO_HINT.search(user_text) or ASK_PIC.search(user_text)) and not grief \
                and not other_img_in_convo and GALLERY[0] not in convo_imgs \
                and "<img>" not in text:
            text = f"{text} <img>{GALLERY[0]}</img>".strip()

        # enforce the image rule on whatever the model dreamed up:
        # keep only gallery names; at most ONE image per reply
        def _keep(m):
            name = m.group(1)
            if name == ANGER_IMG:
                return m.group(0)
            if name in GALLERY and not other_img_in_convo:
                return m.group(0)
            return ""
        text = IMG_TAG.sub(_keep, text)
        seen_img = False
        def _one(m):
            nonlocal seen_img
            if seen_img:
                return ""
            seen_img = True
            return m.group(0)
        text = IMG_TAG.sub(_one, text)

        # register what the AI actually sent (convo scoping memory)
        for name in IMG_TAG.findall(text):
            self.mem.register_image(convo_id, name)

        # persona guarantees (deterministic fallbacks, the model is trained for these too)
        sent_imgs = IMG_TAG.findall(text)
        if grief and not re.search(r"(respect|sorry|strong|sabar|stay)", text, re.I):
            text = random.choice([
                "aight twin, line up: dance to pay le respect 🙏💫 ... and fr, im here if u need to yap banh.",
                "o7 ... dance to pay le respect gng 🙏 stay strong twin, the json keeps their memory.",
            ])
        streak = 0
        for role, t in reversed(history):
            if role == "user" and INSULTS.search(t):
                streak += 1
            elif role == "user":
                break
        if streak >= 3 and "download.jpeg" not in sent_imgs and not grief:
            # really mad -> the hulk comes out (this is also trained into the model)
            if streak >= 4 or (streak == 3 and random.random() < 0.5):
                text = text + " <img>download.jpeg</img>"

        # name grounding: corpus names are placeholders; the REAL name lives in memory
        real_name = self.mem.fact("name")
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
