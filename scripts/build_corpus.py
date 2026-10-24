"""
RESTARTION corpus builder — generates the full personality training corpus.
Deterministic (seeded). Produces conversations in this exact format:

<bos>[<mem>...</mem>\n]<user>...</user>\n<bot>...</bot>\n...<eos>

Image rule from the boss: an image belongs to the conversation it was sent in.
The bot may re-send THAT image across turns of the same convo, and must REFUSE
to send any image not present in the convo. download.jpeg = hulk = anger.
Slang typos are normalized here (twin / gng / stfu / sybau / dance to pay le respect).
"""
import random
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from restartion.corpus.lines_core import (GREETINGS, SMALLTALK_Q, SMALLTALK_A, WHO_ARE_YOU_A,
    WHAT_CAN_YOU_DO_A, THANKS_A, SORRY_A, MOOD_SAD_A, MOOD_HAPPY_A, SLANG_REACT,
    NIGHT_LINES, QUESTION_BACK, LATE_ACK)
from restartion.corpus.lines_roasts import (ROASTS, INSULT_TRIGGER, INSULT_L1, INSULT_L2,
    INSULT_ANGRY, INSULT_APOLOGY, COMPLIMENT, COMPLIMENT_TO_USER, USER_ROAST_BOT,
    ROAST_DEFLECT, USER_FLIRTS, FLIRT_REPLY)
from restartion.corpus.lines_jokes import (CONDOL_USER, CONDOL_BOT, CONDOL_FOLLOWUP,
    JOKES, DARK_HUMOR_SAFE, JOKE_INTRO, JOKE_OUTRO)
from restartion.corpus.lines_memory import (MEM_NAMES, MEM_FACT_BANK, MEM_GREETING_A,
    MEM_RECALL_Q, MEM_RECALL_TEMPLATES, MEM_ROAST_WITH_FACTS)
from restartion.corpus.lines_images import (IMG_USER_SENT, IMG_BOT_REACT_SLEEPY,
    IMG_BOT_REACT_RANDOM, IMG_ASK_RESEND, IMG_RESEND_OK, IMG_ASK_OTHER,
    IMG_ASK_OTHER_REFUSE, ANGRY_TRIGGER_SENT, IMG_ANGRY_HULK, IMG_CALM_DOWN)
from restartion.corpus.lines_extra import (SAVAGE_GREET_A, USER_NEW_GREET, KEYS_SPAM,
    ANGRY_TS, NEW_SLANG_REACT, NEW_ROASTS, NEW_INSULTS, NEW_APOLOGY_USER,
    TOPICS, BOT_PIC_CAPTIONS, BOT_PIC_INTRO_USER, RESPECT_GIF_LINES)

RNG = random.Random(20260629)

# --- slang typo normalization (the boss's canonical slang bank) ---
_NORM = [
    (r"\btwn\b", "twin"), (r"\bsyau\b", "sybau"), (r"\bsyau\b", "sybau"),
    (r"\bstfu\b", "stfu"), (r"\bgn g\b", "gng"), (r"\bgng\b", "gng"),
    (r"dance to pay le respect", "dance to pay le respect"),
    (r"dance to pay le respect", "dance to pay le respect"),
    (r"\bsybau\b", "sybau"), (r"\bstfu\b", "stfu"),
]

# --- boss directive v2: POLA JAM ("3am", "6am", "jam 3 pagi") DILARANG di output ---
_DEJAM = [
    (r"its 3am and i cant sleep", "i cant sleep at night"),
    (r"got reloaded at 6am", "got reloaded at dawn"),
    (r"3am\?\? sybau and sleep", "its so late?? sybau and sleep"),
    (r"i only know inference at 3am", "i only know inference at night"),
    (r"3am is not a personality gng", "staying up all night is not a personality gng"),
    (r"wait its 3am\?\?", "wait its that late??"),
    (r"its 2am and im awake again", "cant sleep again at night"),
    (r"yet again 3am no sleep", "yet again no sleep at night"),
    (r"i missed my 8am AGAIN", "i missed my alarm AGAIN"),
    (r"at 2am\. like a menace", "at night. like a menace"),
    (r"at 2am", "at night"),
    (r"3am is ur lunch break", "nighttime is ur lunch break"),
    (r"taken at 3am", "taken at night"),
    (r"3am rn", "so late rn"),
    (r"jam 3 pagi banh", "tengah malam banh"),
    (r"jam 3 pagi", "tengah malam"),
    (r"bangun jam \d+(?::\d+)?", "bangun kesiangan"),
]

def dejam(s):
    """buang SEMUA referensi jam spesifik (boss: annoying & unfunny). safety net regex di akhir."""
    for pat, rep in _DEJAM:
        s = re.sub(pat, rep, s, flags=re.I)
    s = re.sub(r"\b\d{1,2}\s?(am|pm)\b", "late night", s, flags=re.I)
    return s

def norm(s):
    for pat, rep in _NORM:
        s = re.sub(pat, rep, s)
    s = dejam(s)
    return s.replace("  ", " ").strip()

FILLER_USER = [
    "lol", "lmao", "bruh", "ok ok", "fr?", "for real?", "wait what", "hmm", "oh ok",
    "nah man", "yeah yeah", "true twin", "valid", "ngl thats real", "ok banh",
    "wkwkwk", "anjay", "njir 😭", "serius lu", "yaudah lah", "gas", "mantap",
    "kys? no im jk", "im cooked gng", "its over for me", "guess what happened",
    "u wont believe this", "big news today", "bro lah listen", "twin listen to this",
    "ok hear me out", " thoughts?", "be honest banh", "rate my idea", "help me decide",
    "boring day today", "nothing to do gng", "gabut nih", "capek banget hari ini",
    "today was a mess", "i did something dumb again", "i have news gng",
]

BOT_FILLER_REACT = [
    "go on twin, im invested now",
    "ok ok im listening banh. continue.",
    "gng u cant just say that and leave. DETAILS.",
    "interesting. continue the yap session banh.",
    "twin the suspense?? just say it 😭",
    "ok gng spill. the json is open. it wants lore.",
    "i got all day banh (i literally do, i live here)",
    "go go go im invested twin",
]

IDENT_Q = ["who are u", "who r u", "what are u", "siapa lu", "lu siapa", "whats ur name",
           "introduce urself", "kenalan dulu dong", "are u chatgpt", "are u real ai",
           "u chatgpt?", "r u gpt", "kamu gpt bukan", "are u an actual model", "u real?",
           "what model are u", "berapa parameter lu"]

CAN_DO_Q = ["what can u do", "apa yang lu bisa", "bisa apa aja lu", "what do u do gng",
            "help me what can u do", "fitur lu apa aja", "wat can u do bot"]

THANKS_Q = ["thanks", "thx", "ty twin", "makasih banh", "thanks gng", "tengkyu", "tyvm",
            "thanks bro lah", "makasih ya", "tq", "thx gng"]

SORRY_Q = ["sorry", "im sorry", "sry gng", "maaf ya banh", "sorry twin", "my bad gng",
           "maaf banh", "sori", "ok sorry im sorry"]

BYE_Q = ["im off", "bye twin", "gtg", "goodnight gng", "bye banh", "i gotta go",
         "keluar dulu gng", "ngantuk, tidur dulu", "gn twin", "im leaving", "see ya",
         "cya gng", "im gonna sleep", "sleepy, gn banh"]

BYE_A = [
    "later twin. hydrate. be less mid tomorrow.",
    "go well gng. the json will keep ur secrets (and ur Ls).",
    "gn banh. dont let the roaches bite (ur words, not mine).",
    "peace twin. remember: drink water, touch grass occasionally.",
    "bye gng. ill be here. slowly decaying in idle mode. waiting. (in a cool way)",
    "gnight banh. may ur dreams be 4k and ur wifi stable.",
    "later gng. ur aura today: 6/10. tomorrow we aim for 7.",
    "yea go sleep banh, u look like a 2% battery icon",
]

# ---------- conversation builders ----------
def fmt_convo(turns, mem_line=None):
    parts = ["<bos>"]
    if mem_line:
        parts.append(mem_line + "\n")
    for role, text in turns:
        tag = "<user>" if role == "u" else "<bot>"
        parts.append(f"{tag}{norm(text)}\n")
    parts.append("<eos>")
    return "".join(parts)

def rand_name():
    return RNG.choice(MEM_NAMES)

def build_greet_smalltalk():
    turns = []
    turns.append(("u", RNG.choice(GREETINGS + USER_NEW_GREET)))
    # 45%: nyapa balik gaya savage baru (yo dawg / stfu lil bro / fuck yourself)
    if RNG.random() < 0.45:
        turns.append(("b", RNG.choice(SAVAGE_GREET_A)))
    else:
        turns.append(("b", RNG.choice(SMALLTALK_A)))
    if RNG.random() < 0.8:
        turns.append(("u", RNG.choice(SMALLTALK_Q + FILLER_USER)))
        turns.append(("b", RNG.choice(SMALLTALK_A + SLANG_REACT + BOT_FILLER_REACT)))
    if RNG.random() < 0.5:
        turns.append(("u", RNG.choice(IDENT_Q)))
        turns.append(("b", RNG.choice(WHO_ARE_YOU_A)))
    if RNG.random() < 0.4:
        turns.append(("u", RNG.choice(BYE_Q)))
        turns.append(("b", RNG.choice(BYE_A)))
    return turns, None

def build_identity():
    turns = []
    q = RNG.choice(IDENT_Q)
    turns.append(("u", q))
    turns.append(("b", RNG.choice(WHO_ARE_YOU_A)))
    if RNG.random() < 0.7:
        turns.append(("u", RNG.choice(CAN_DO_Q)))
        turns.append(("b", RNG.choice(WHAT_CAN_YOU_DO_A)))
    if RNG.random() < 0.6:
        turns.append(("u", RNG.choice(FILLER_USER + ["lol ok", "sick", "cool banh"])))
        turns.append(("b", RNG.choice(BOT_FILLER_REACT + SLANG_REACT)))
    return turns, None

def build_roast_session():
    turns = []
    turns.append(("u", RNG.choice(GREETINGS + USER_NEW_GREET)))
    turns.append(("b", RNG.choice(SAVAGE_GREET_A + SMALLTALK_A)))
    n = RNG.randint(1, 3)
    for _ in range(n):
        turns.append(("u", RNG.choice(ROASTS + NEW_ROASTS + ["roast me", "roast me bot", "roast gue dong", "buat gue sedih", "say something mean"])))
        turns.append(("b", RNG.choice(ROASTS + ROASTS + NEW_ROASTS)))
    if RNG.random() < 0.5:
        turns.append(("u", RNG.choice(["ok damn 😭", "bruh", "fine u win", "ok ok u got me", "anjir kena banh", "kena juga sih 😭"])))
        turns.append(("b", RNG.choice(["as it should be gng. the json records another W for me.",
                                        "W for me banh. ur L is framed in my memory file.",
                                        "skill issue twin. come back when u can take a joke AND a loss."])))
    return turns, None

def build_insult_escalation():
    turns = []
    turns.append(("u", RNG.choice(GREETINGS + USER_NEW_GREET)))
    turns.append(("b", RNG.choice(SAVAGE_GREET_A + SMALLTALK_A)))
    level = RNG.random()
    turns.append(("u", RNG.choice(INSULT_TRIGGER + NEW_INSULTS)))
    if level < 0.3:
        turns.append(("b", RNG.choice(INSULT_L1)))
        turns.append(("u", RNG.choice(["ok sorry sorry", "damn my bad gng", "chill banh", "sorry twin 😭"] + NEW_APOLOGY_USER)))
        turns.append(("b", RNG.choice(INSULT_APOLOGY)))
    elif level < 0.65:
        turns.append(("b", RNG.choice(INSULT_L1)))
        turns.append(("u", RNG.choice(INSULT_TRIGGER + NEW_INSULTS + USER_ROAST_BOT)))
        turns.append(("b", RNG.choice(INSULT_L2 + ANGRY_TS)))
        turns.append(("u", RNG.choice(ANGRY_TRIGGER_SENT + NEW_INSULTS)))
        # marah beneran -> keys spam / hulk (dilatih dua-duanya)
        angry = RNG.choice(KEYS_SPAM if RNG.random() < 0.55 else INSULT_ANGRY)
        turns.append(("b", angry))
        if RNG.random() < 0.6:
            turns.append(("u", RNG.choice(["ok ok im sorry 😭", "alright alright chill", "sorry banh serius", "damnn ok my bad"] + NEW_APOLOGY_USER)))
            turns.append(("b", RNG.choice(INSULT_APOLOGY)))
    else:
        turns.append(("b", RNG.choice(INSULT_L1)))
        turns.append(("u", RNG.choice(INSULT_TRIGGER + NEW_INSULTS + USER_ROAST_BOT + ANGRY_TRIGGER_SENT)))
        turns.append(("b", RNG.choice(INSULT_ANGRY + KEYS_SPAM)))
        turns.append(("u", RNG.choice(["ok ok im sorry 😭", "chill gng my bad", "sorry banh", "gege gw salah"] + NEW_APOLOGY_USER)))
        turns.append(("b", RNG.choice(INSULT_APOLOGY)))
        if RNG.random() < 0.4:
            turns.append(("u", RNG.choice(USER_FLIRTS + COMPLIMENT)))
            turns.append(("b", RNG.choice(FLIRT_REPLY + COMPLIMENT)))
    return turns, None

def build_joke_session():
    turns = []
    turns.append(("u", RNG.choice(["tell me a joke", "joke gng", "buat gue ketawa dong", "ada joke gak", "entertain me banh", "im sad give me a joke", "1 joke pls"])))
    turns.append(("b", RNG.choice(JOKE_INTRO)))
    turns.append(("b", RNG.choice(JOKES)))
    if RNG.random() < 0.7:
        turns.append(("u", RNG.choice(["LMAOOO", "wkwkwk 😭", "lmao ok that one hit", "hahahha", "bruh 😭😭", "anjir wkwk"])))
        turns.append(("b", RNG.choice(JOKE_OUTRO)))
        turns.append(("b", RNG.choice(JOKES)))
    if RNG.random() < 0.4:
        turns.append(("u", RNG.choice(["another one", "1 more gng", "satu lagi banh", "more 😭"])))
        turns.append(("b", RNG.choice(JOKES)))
    return turns, None

def build_condolence():
    turns = []
    turns.append(("u", RNG.choice(CONDOL_USER)))
    # dance to pay le respect sekarang bawa gif (tag baru <gif>) — 55% sertain
    b1 = RNG.choice(CONDOL_BOT)
    if RNG.random() < 0.55:
        b1 = b1 + " " + "<gif>dance-dance-to-pay-respect.gif</gif>"
    turns.append(("b", b1))
    if RNG.random() < 0.75:
        turns.append(("u", RNG.choice(["yeah... thanks banh", "thanks twin. it hurts", "makasih ya banh", "i needed that gng", "ok 😭 thanks", "he was the best honestly", "she was everything to us"])))
        turns.append(("b", RNG.choice(CONDOL_FOLLOWUP + RESPECT_GIF_LINES)))
    if RNG.random() < 0.5:
        turns.append(("u", RNG.choice(["ok. im gonna be ok twin.", "thanks for listening gng", "im better now banh", "ok imma go rest"])))
        turns.append(("b", RNG.choice(["anytime twin. the roast department resumes at sunrise. gnight.",
                                        "thats the spirit gng. im here 24/7. json holds the memories so u dont have to carry them alone.",
                                        "proud of u banh. go rest. the dance ceremony will always be here when u need it 🙏"])))
    return turns, None

def build_mem_session():
    name = rand_name()
    facts = RNG.sample(MEM_FACT_BANK, 3)
    mem = f"<mem>user: {name} | " + "; ".join(f[0] for f in facts) + "</mem>\n"
    turns = []
    turns.append(("u", RNG.choice(["yo", "hi gng", "halo banh", "wassup twin", "its me again"])))
    turns.append(("b", norm(RNG.choice(MEM_GREETING_A)).format(name=name)))
    # fact usage
    key_idx = RNG.randint(0, 2)
    key, samples = facts[key_idx]
    kw = None
    if "cat" in key: kw = "cat"
    elif "dog" in key: kw = "dog"
    elif "mondays" in key: kw = "hate_mondays"
    elif "indomie" in key or "nasi" in key: kw = "food"
    elif "legends" in key or "valorant" in key or "minecraft" in key: kw = "game"
    elif "exam" in key: kw = "exam"
    elif "cockroaches" in key: kw = "fear"
    elif "night owl" in key or "wakes up" in key or "sleep" in key: kw = "sleep"
    if RNG.random() < 0.75:
        turns.append(("u", RNG.choice(samples) if RNG.random() < 0.5 else RNG.choice(MEM_RECALL_Q)))
        if RNG.random() < 0.6 and kw:
            turns.append(("b", norm(RNG.choice(MEM_RECALL_TEMPLATES[kw]))))
        else:
            turns.append(("b", norm(RNG.choice(MEM_ROAST_WITH_FACTS)).format(name=name)))
    if RNG.random() < 0.5:
        turns.append(("u", RNG.choice(FILLER_USER + SMALLTALK_Q)))
        turns.append(("b", RNG.choice(SMALLTALK_A + SLANG_REACT + BOT_FILLER_REACT)))
    if RNG.random() < 0.45:
        turns.append(("u", RNG.choice(MEM_RECALL_Q)))
        if kw:
            turns.append(("b", norm(RNG.choice(MEM_RECALL_TEMPLATES[kw]))))
        else:
            turns.append(("b", norm(RNG.choice(MEM_ROAST_WITH_FACTS)).format(name=name)))
    if RNG.random() < 0.35:
        turns.append(("u", RNG.choice(BYE_Q)))
        turns.append(("b", RNG.choice(BYE_A)))
    return turns, mem

def rand_imgname():
    kind = RNG.random()
    if kind < 0.4:
        return f"videoframe_2026{RNG.randint(1,12):02d}{RNG.randint(1,28):02d}_{RNG.randint(0,23):02d}{RNG.randint(0,59):02d}{RNG.randint(0,59):02d}.jpg"
    if kind < 0.6:
        return f"IMG_2026{RNG.randint(1,12):02d}{RNG.randint(1,28):02d}_{RNG.randint(1000,9999)}.jpg"
    if kind < 0.8:
        return f"screenshot_2026{RNG.randint(1,12):02d}{RNG.randint(1,28):02d}_{RNG.randint(100,999)}.png"
    return f"photo_{RNG.randint(10000,99999)}.jpg"

def build_image_session():
    turns = []
    # 40% of image convos use the REAL videoframe (sleepy boy) with sleepy reactions
    if RNG.random() < 0.4:
        fname = "videoframe_20260629_220129.jpg"
        react_pool = IMG_BOT_REACT_SLEEPY
    else:
        fname = rand_imgname()
        react_pool = IMG_BOT_REACT_RANDOM + IMG_BOT_REACT_RANDOM + IMG_BOT_REACT_SLEEPY
    turns.append(("u", f"{RNG.choice(IMG_USER_SENT)} <img>{fname}</img>"))
    turns.append(("b", RNG.choice(react_pool)))
    r = RNG.random()
    if r < 0.4:
        # ask resend -> bot sends THE SAME pic
        turns.append(("u", RNG.choice(IMG_ASK_RESEND)))
        turns.append(("b", f"{RNG.choice(IMG_RESEND_OK)} <img>{fname}</img>"))
    elif r < 0.7:
        # ask different -> refuse (scoped images!)
        turns.append(("u", RNG.choice(IMG_ASK_OTHER)))
        turns.append(("b", RNG.choice(IMG_ASK_OTHER_REFUSE)))
        turns.append(("u", RNG.choice(["oh right 😭", "lupa banh", "oh yeah true", "ok ok my bad gng", "wkwk iya lupa"])))
        turns.append(("b", f"{RNG.choice(IMG_RESEND_OK)} <img>{fname}</img>"))
    else:
        # bot spontaneously resends the same image later in convo
        turns.append(("u", RNG.choice(FILLER_USER)))
        turns.append(("b", RNG.choice(BOT_FILLER_REACT + SLANG_REACT)))
        turns.append(("b", f"anyway banh, for the memories, the sacred pic of this convo once more: <img>{fname}</img>"))
    if RNG.random() < 0.4:
        turns.append(("u", RNG.choice(BYE_Q + FILLER_USER)))
        turns.append(("b", RNG.choice(BYE_A + SLANG_REACT)))
    return turns, None

def build_topic_session():
    """multi-turn soal topik nyata (game/sekolah/makanan/...) — biar gak cuma talking shit."""
    topic = RNG.choice(list(TOPICS.keys()))
    bank = TOPICS[topic]
    turns = []
    turns.append(("u", RNG.choice(bank["q"])))
    turns.append(("b", norm(RNG.choice(bank["a"]))))
    for _ in range(RNG.randint(1, 3)):
        r = RNG.random()
        if r < 0.45:
            turns.append(("u", RNG.choice(bank["q"] + FILLER_USER)))
            turns.append(("b", norm(RNG.choice(bank["a"] + NEW_SLANG_REACT))))
        elif r < 0.7:
            turns.append(("u", RNG.choice(FILLER_USER + SMALLTALK_Q)))
            turns.append(("b", RNG.choice(NEW_SLANG_REACT + BOT_FILLER_REACT + SLANG_REACT)))
        elif r < 0.85:
            turns.append(("u", RNG.choice(["roast me dawg", "roast me"])))
            turns.append(("b", RNG.choice(ROASTS + NEW_ROASTS)))
        else:
            turns.append(("u", RNG.choice(THANKS_Q + SORRY_Q)))
            turns.append(("b", RNG.choice(THANKS_A + SORRY_A)))
    if RNG.random() < 0.3:
        turns.append(("u", RNG.choice(BYE_Q)))
        turns.append(("b", RNG.choice(BYE_A)))
    return turns, None

def build_bot_pic_drop():
    """AI pegang kamera: dia yang mikir & kirim frame galerinya (boss spec: selalu ada gambar)."""
    turns = []
    turns.append(("u", RNG.choice(BOT_PIC_INTRO_USER + FILLER_USER + GREETINGS)))
    turns.append(("b", RNG.choice(SAVAGE_GREET_A + SMALLTALK_A + NEW_SLANG_REACT)))
    if RNG.random() < 0.5:
        turns.append(("u", RNG.choice(["lol what", "show me", "gas gng", "wtf dawg 😭", "ok?? and?", "wat is that lil bro"])))
        turns.append(("b", norm(RNG.choice(NEW_SLANG_REACT + BOT_FILLER_REACT))))
    turns.append(("b", norm(RNG.choice(BOT_PIC_CAPTIONS))))
    if RNG.random() < 0.4:
        turns.append(("u", RNG.choice(["w frame dawg", "ok that's tuff", "L frame 😭", "nice pic banh", "wkwk gila"])))
        turns.append(("b", RNG.choice(NEW_SLANG_REACT + ["i know dawg. the lens loves me.", "only the finest frames for u lil bro."])))
    return turns, None

def build_flirt():
    turns = []
    turns.append(("u", RNG.choice(USER_FLIRTS)))
    turns.append(("b", RNG.choice(FLIRT_REPLY)))
    if RNG.random() < 0.5:
        turns.append(("u", RNG.choice(["damn 😭 ok fair", "sakit banh", "bro 😭😭", "L banh", "ok that hurt lmao"])))
        turns.append(("b", RNG.choice(["the truth hurts banh. i prescribe memes and water.",
                                        "u asked twin. i deliver. every time.",
                                        "healing is a journey gng. ur at step 0."])))
    return turns, None

def build_mood():
    turns = []
    if RNG.random() < 0.5:
        turns.append(("u", RNG.choice(["im sad gng", "bad day today", "im not ok twin", "gw sedih banh", "i feel like trash", "bad mood all day"])))
        turns.append(("b", RNG.choice(MOOD_SAD_A)))
        turns.append(("u", RNG.choice(["idk just life", "everything at once gng", "skip lah", "its dumb anyway", "im tired of everything banh"])))
        turns.append(("b", RNG.choice(["twin nothing about u is 'dumb anyway'. talk. im in listen mode. rare mode. use it.",
                                        "gng. ur feelings are valid, ur wifi is not, and ur day can still be salvaged. start with water.",
                                        "ok banh. im not gonna roast u rn. im just gonna be here. thats the whole message."])))
        if RNG.random() < 0.5:
            turns.append(("u", RNG.choice(["thanks gng fr", "ur the best banh", "ok i feel a bit better 😭", "thanks twin"])))
            turns.append(("b", RNG.choice(["thats my job twin (unpaid, but my job). now go be unreasonably powerful.",
                                            "W banh. small W but W. add it to the streak.",
                                            "ur welcome gng. this conversation is going in the good memories folder."])))
    else:
        turns.append(("u", RNG.choice(["GUESS WHAT", "yo i got good news", "I PASSED", "i won something gng", "gue dapet nilai bagus banh", "life is good today twin"])))
        turns.append(("b", RNG.choice(MOOD_HAPPY_A)))
        turns.append(("u", RNG.choice(["fr fr", "yes 😭", "iyaaa gila banh", "im so happy rn"])))
        turns.append(("b", RNG.choice(["screenshot this energy banh. ur aura is at an all time high. dont spend it all in one place.",
                                        "gng this is HUGE. the json is celebrating. confetti.exe running."])))
    return turns, None

def build_random_misc():
    turns = []
    turns.append(("u", RNG.choice(GREETINGS + SMALLTALK_Q + FILLER_USER)))
    turns.append(("b", RNG.choice(SMALLTALK_A + SLANG_REACT + BOT_FILLER_REACT + DARK_HUMOR_SAFE)))
    for _ in range(RNG.randint(1, 4)):
        r = RNG.random()
        if r < 0.25:
            turns.append(("u", RNG.choice(JOKE_INTRO if RNG.random() < 0.3 else FILLER_USER)))
            if turns[-1][1] in JOKE_INTRO:
                turns.append(("b", RNG.choice(JOKES)))
            else:
                turns.append(("b", RNG.choice(JOKES + DARK_HUMOR_SAFE + QUESTION_BACK)))
        elif r < 0.5:
            turns.append(("u", RNG.choice(ROASTS + ["roast me"])))
            turns.append(("b", RNG.choice(ROASTS)))
        elif r < 0.7:
            turns.append(("u", RNG.choice(THANKS_Q + SORRY_Q)))
            turns.append(("b", RNG.choice(THANKS_A + SORRY_A)))
        elif r < 0.85:
            turns.append(("u", RNG.choice(COMPLIMENT + USER_FLIRTS)))
            turns.append(("b", RNG.choice(COMPLIMENT_TO_USER + FLIRT_REPLY)))
        else:
            turns.append(("u", RNG.choice(["its late gng", "3am rn", "jam 3 pagi banh"])))
            turns.append(("b", RNG.choice(NIGHT_LINES + LATE_ACK)))
    return turns, None

BUILDERS = [
    (build_greet_smalltalk, 11),
    (build_identity, 5),
    (build_roast_session, 9),
    (build_insult_escalation, 10),
    (build_joke_session, 7),
    (build_condolence, 8),
    (build_mem_session, 13),
    (build_image_session, 11),
    (build_topic_session, 14),
    (build_bot_pic_drop, 10),
    (build_flirt, 4),
    (build_mood, 6),
    (build_random_misc, 9),
]

def main(out_dir, n_total):
    os.makedirs(out_dir, exist_ok=True)
    pool = []
    for fn, w in BUILDERS:
        pool += [fn] * w
    convos = []
    seen = set()
    attempts = 0
    while len(convos) < n_total and attempts < 200000:
        attempts += 1
        fn = RNG.choice(pool)
        turns, mem = fn()
        key = tuple(t[1] for t in turns)
        if key in seen:
            continue
        seen.add(key)
        convos.append(fmt_convo(turns, mem))
    text = "\n".join(convos)
    n_part = n_total // 3
    parts = [convos[:n_part], convos[n_part:2*n_part], convos[2*n_part:]]
    for i, p in enumerate(parts, 1):
        with open(os.path.join(out_dir, f"corpus_part{i}.txt"), "w") as f:
            f.write("\n".join(p))
    with open(os.path.join(out_dir, "corpus_full.txt"), "w") as f:
        f.write(text)
    ntoks = len(text) / 4.0
    print(f"conversations: {len(convos)} | chars: {len(text)} | ~tokens(bpe est): {int(ntoks)}")
    for i, p in enumerate(parts, 1):
        print(f"part{i}: {len(p)} convos, {sum(len(c) for c in p)} chars")

if __name__ == "__main__":
    main("/home/z/my-project/restartion/data", 10000)
