#!/usr/bin/env python3
"""Diff the 文稿-supplied text against a full vision read of the same cues.

Those cues were the only lines in the finished SRTs that nobody had looked
at -- the script supplied their wording and the first vision pass skipped
them on purpose. Reading them turns a 24-row spot check into a census.

Comparison is on normalised text (Han, digits and Latin only). Punctuation
is ignored because the 文稿 and the subtitler punctuate differently and that
is not an error worth reporting; a difference here means the *characters*
differ.

`--apply` writes the vision text over the 文稿 text in the plan-B work dir,
which is what the SRTs are built from.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import align as aligner                                  # noqa: E402

WORK = "/workspaces/Corpus-Cleanup/kithann/out/mxf"


def timestamp(seconds):
    return "%d:%02d" % (int(seconds) // 60, int(seconds) % 60)


def load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def compare(slug, name):
    plan_b = os.path.join(WORK, slug + ".B.work")
    plan_c = os.path.join(WORK, slug + ".C.work")
    marker = os.path.join(plan_b, "from_wenkao.json")
    if not (os.path.exists(marker) and os.path.isdir(plan_c)):
        return None

    wenkao_cues = load(marker)
    b_text = load(os.path.join(plan_b, "transcripts.json"))
    c_text = load(os.path.join(plan_c, "transcripts.json"))
    cues = load(os.path.join(plan_b, "cues.json")).get("cues", [])
    clock = {}
    for cue in cues:
        clock[cue["index"]] = cue["start"]

    same = diff = unread = 0
    both_blank = 0
    rows = []
    for index in wenkao_cues:
        key = str(index)
        if key not in c_text:
            unread += 1
            continue
        script = (b_text.get(key, {}) or {}).get("han", "") or ""
        seen = (c_text.get(key, {}) or {}).get("han", "") or ""
        a = aligner.normalise(script)
        b = aligner.normalise(seen)
        if not a and not b:
            both_blank += 1
            same += 1
            continue
        if a == b:
            same += 1
        else:
            diff += 1
            rows.append({
                "episode": name, "cue": index,
                "at": timestamp(clock.get(index, 0)),
                "wenkao": script.strip(), "vision": seen.strip(),
            })
    return {"episode": name, "slug": slug, "cues": len(wenkao_cues),
            "same": same, "diff": diff, "unread": unread,
            "blank_both": both_blank, "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the vision text into the plan-B work dir")
    ap.add_argument("--out", default="", help="write the full diff as JSON")
    args = ap.parse_args()

    entries = json.load(open(os.path.join(HERE, "inventory.json"),
                             encoding="utf-8"))
    results = []
    for entry in entries:
        if entry["truncated"]:
            continue
        got = compare(entry["slug"], entry["srt_name"])
        if got and got["cues"]:
            results.append(got)

    total = sum(r["cues"] for r in results)
    same = sum(r["same"] for r in results)
    diff = sum(r["diff"] for r in results)
    unread = sum(r["unread"] for r in results)
    checked = same + diff

    print("%-42s %6s %6s %6s %7s" % ("episode", "cues", "same", "diff", "agree"))
    for r in sorted(results, key=lambda x: -x["diff"]):
        done = r["same"] + r["diff"]
        pct = 100.0 * r["same"] / done if done else 0.0
        print("%-42s %6d %6d %6d %6.1f%%"
              % (r["episode"], r["cues"], r["same"], r["diff"], pct))
    print("-" * 70)
    print("%-42s %6d %6d %6d %6.1f%%"
          % ("TOTAL", total, same, diff,
             100.0 * same / checked if checked else 0.0))
    if unread:
        print("still unread: %d" % unread)

    if args.out:
        rows = []
        for r in results:
            rows.extend(r["rows"])
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump({"summary": [
                {k: r[k] for k in ("episode", "cues", "same", "diff")}
                for r in results], "diffs": rows},
                handle, ensure_ascii=False, indent=1)
        print("wrote", args.out)

    if args.apply:
        for r in results:
            plan_b = os.path.join(WORK, r["slug"] + ".B.work")
            plan_c = os.path.join(WORK, r["slug"] + ".C.work")
            b_text = load(os.path.join(plan_b, "transcripts.json"))
            c_text = load(os.path.join(plan_c, "transcripts.json"))
            marker = load(os.path.join(plan_b, "from_wenkao.json"))
            changed = 0
            for index in marker:
                key = str(index)
                if key in c_text:
                    b_text[key] = c_text[key]
                    changed += 1
            with open(os.path.join(plan_b, "transcripts.json"), "w",
                      encoding="utf-8") as handle:
                json.dump(b_text, handle, ensure_ascii=False, indent=1)
            print("applied %4d vision cue(s) to %s" % (changed, r["episode"]))


if __name__ == "__main__":
    main()
