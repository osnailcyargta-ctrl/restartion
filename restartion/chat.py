"""
RESTARTION chat — CLI. Dark metal, zero mercy.
  python -m restartion.chat            (or python chat.py)
commands: /mem /img <file> /reset /stats /quit
"""
import json
import os
import sys
import time

from .engine import Engine, MEM_DIR, ASSETS

CLR = {
    "dim": "\033[2m", "red": "\033[91m", "steel": "\033[37m",
    "bold": "\033[1m", "cyan": "\033[96m", "end": "\033[0m",
}
BANNER = r"""
 ██▀███   ███▄ ▄███▓ ▒█████   ███▄    █  ▄▄▄       ██ ▄█▀
▓██ ▒ ██▒▓██▒▀█▀ ██▒▒██▒  ██▒ ██ ▀█   █ ▒████▄     ██▄█▒
▓██ ░▄█ ▒▓██    ▓██░▒██░  ██▓▓██  ▀█ ██▒▒██  ▀█▄  ▓███▄░
▒██▀▀█▄  ▒██    ▒██ ▒██   ██▒▓██▒  ▐▌██▒░██▄▄▄▄██ ▓██ █▄
░██▓ ▒██▒▒██▒   ░██▒░ ████▓▒░▒██░   ▓██░ ▓█   ▓██▒▒██▒ █▄
░ ▒▓ ░▒▓░░ ▒░   ░  ░░ ▒░▒░▒░ ░ ▒░   ▒  ░ ▒▒   ▓▒█░▒ ▒▒ ▓▒
"""

def main():
    print(f"{CLR['red']}{BANNER}{CLR['end']}")
    print(f"{CLR['dim']} restartion · transformer asli · 57.44M params · dilatih dari nol · 4k ctx{CLR['end']}")
    print(f"{CLR['dim']} commands: /mem /img <file> /reset /stats /quit{CLR['end']}\n")

    weights = None
    if len(sys.argv) > 1:
        weights = sys.argv[1]
    eng = Engine(weights=weights)
    print(f"{CLR['dim']}[loaded {os.path.basename(eng.weights_path)} @ step {eng.step}]{CLR['end']}")

    convo_id = f"cli_{time.strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(os.path.join(MEM_DIR, "sessions"), exist_ok=True)
    sess_path = os.path.join(MEM_DIR, "sessions", f"{convo_id}.jsonl")
    history, images = [], {}

    def save(role, text):
        with open(sess_path, "a") as f:
            f.write(json.dumps({"t": time.time(), "role": role, "text": text}) + "\n")

    def show_images(text):
        import re
        for name in re.findall(r"<img>([^<]+)</img>", text):
            p = os.path.join(ASSETS, name)
            print(f"{CLR['cyan']}   🖼 [IMG: {name}]{CLR['end']} {CLR['dim']}({p}){CLR['end']}")

    while True:
        try:
            line = input(f"{CLR['steel']}you ▸ {CLR['end']}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{CLR['dim']}bye twin.{CLR['end']}")
            break
        if not line:
            continue
        if line == "/quit":
            print(f"{CLR['dim']}peace gng.{CLR['end']}")
            break
        if line == "/mem":
            print(f"{CLR['dim']}{json.dumps(eng.mem.d['facts'], indent=2)}{CLR['end']}")
            continue
        if line == "/reset":
            history, images = [], {}
            eng.convo_turns = 0
            print(f"{CLR['dim']}convo wiped. memory file kept (REAL memory).{CLR['end']}")
            continue
        if line == "/stats":
            print(f"{CLR['dim']}weights={eng.weights_path} step={eng.step} turns={eng.convo_turns} facts={len(eng.mem.d['facts'])}{CLR['end']}")
            continue
        if line.startswith("/img"):
            fname = line.split(maxsplit=1)[1].strip()
            p = os.path.join(ASSETS, fname)
            if os.path.exists(p):
                images[fname] = p
                eng.mem.register_image(convo_id, fname)
                print(f"{CLR['dim']}[attached {fname} to this convo]{CLR['end']}")
                line = f"look at this <img>{fname}</img>"
            else:
                print(f"{CLR['dim']}no such asset in assets/. available: {os.listdir(ASSETS)}{CLR['end']}")
                continue

        save("user", line)
        history.append(("user", line))
        reply = eng.reply(line, history, convo_id=convo_id, images=images)
        history.append(("bot", reply))
        save("bot", reply)
        print(f"{CLR['red']}restartion ▸{CLR['end']} {reply}")
        show_images(reply)

if __name__ == "__main__":
    main()
