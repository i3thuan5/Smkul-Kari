#!/usr/bin/env python3
"""Whole-episode vosk decode: audio in, the word record out.

Never per-entry audio cutting -- the corpus' entries sit back to back in
running speech, so cutting there beheads words. The episode is decoded
once, 16 kHz mono via ffmpeg, fed in ~0.125 s chunks; every recogniser
segment (its natural pause boundary) becomes one speech sentence, and
each word keeps its timestamps and confidence exactly as the model said
it -- no capitalisation, no character swaps, no punctuation.

vosk is imported inside the function: the unit-test environments never
load it, the field run (asrmt venv) does. This layer is covered by the
real-model smoke test, faithfulness downstream by the projection tests.
"""
import json
import subprocess
from scripts.errors import PipelineError

SAMPLE_RATE = 16000
CHUNK_BYTES = 4000  # 0.125 s of s16le mono at 16 kHz


def decode(audio_path, model_dir, srt_name, model_label=""):
    """Run the recogniser over the whole file; return the word record."""
    from vosk import Model, KaldiRecognizer, SetLogLevel
    SetLogLevel(-1)

    recognizer = KaldiRecognizer(Model(model_path=model_dir), SAMPLE_RATE)
    recognizer.SetWords(True)

    command = ["ffmpeg", "-v", "error", "-i", audio_path,
               "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"]
    words = []
    sents = []

    def take(result):
        got = result.get("result") or []
        if not got:
            return
        first = len(words)
        for item in got:
            words.append({"w": item["word"], "start": item["start"],
                          "end": item["end"], "conf": item["conf"]})
        sents.append({"start": got[0]["start"], "end": got[-1]["end"],
                      "i0": first, "i1": len(words)})

    proc = subprocess.Popen(command, stdout=subprocess.PIPE)
    try:
        while True:
            chunk = proc.stdout.read(CHUNK_BYTES)
            if not chunk:
                break
            if recognizer.AcceptWaveform(chunk):
                take(json.loads(recognizer.Result()))
        take(json.loads(recognizer.FinalResult()))
    finally:
        proc.stdout.close()
        proc.wait()
    if proc.returncode:
        raise PipelineError("ffmpeg failed decoding %s" % audio_path)

    return {"srt_name": srt_name, "model": model_label or model_dir,
            "sample_rate": SAMPLE_RATE, "words": words, "sents": sents}


def write_record(record, path):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2,
                  sort_keys=True)
