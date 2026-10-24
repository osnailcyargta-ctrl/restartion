"""Train a BPE tokenizer FROM SCRATCH on the restartion corpus (vocab 8192)."""
import os
from tokenizers import Tokenizer, models, trainers, pre_tokenizers, decoders, processors

SPECIALS = ["<pad>", "<bos>", "<eos>", "<user>", "<bot>", "<mem>", "</mem>", "<img>", "</img>"]

def main():
    root = "/home/z/my-project/restartion"
    tok = Tokenizer(models.BPE(unk_token=None))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=True)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=8192 - len(SPECIALS),
        special_tokens=SPECIALS,
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        show_progress=False,
    )
    tok.train([os.path.join(root, "data", "corpus_full.txt")], trainer)
    tok.save(os.path.join(root, "data", "tokenizer.json"))
    # sanity
    enc = tok.encode("<bos><user>yo twin wassup</user>\n<bot>yo gng stfu 😭</bot><eos>")
    print("vocab:", tok.get_vocab_size())
    print("roundtrip ok:", tok.decode(enc.ids) == "<bos><user>yo twin wassup</user>\n<bot>yo gng stfu 😭</bot><eos>")
    print("ids:", enc.ids[:20])

if __name__ == "__main__":
    main()
