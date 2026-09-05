#!/usr/bin/env python3
"""Re-apply the topic classification to an export already on disk.

Classification is a pure function of the title and categories, both of which the
manifest already records. When the rules are corrected there is therefore no reason
to re-fetch 387 pages: doing so would spend another ~880 requests on someone else's
server to recompute something derivable locally, which the ingestion brief's "do not
scrape" spirit argues against even though it is technically within the rate limit.

    python tools/kb_reclassify.py --out kb/raw/fandom

Rewrites the classification lines in each page's frontmatter, moves newly excluded
pages out of pages/ and html/, and rewrites manifest.json and excluded.json.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wiki_export import topic_check  # noqa: E402

_LINE = {
    "off_topic": re.compile(r"^off_topic:.*$", re.M),
    "mixed_scope": re.compile(r"^mixed_scope:.*$", re.M),
    "foreign_games": re.compile(r"^foreign_games:.*$", re.M),
}


def _rewrite_frontmatter(path, off_topic, mixed, foreign):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    values = {
        "off_topic": json.dumps(off_topic),
        "mixed_scope": json.dumps(mixed),
        "foreign_games": json.dumps(foreign),
    }
    for key, pattern in _LINE.items():
        line = "%s: %s" % (key, values[key])
        if pattern.search(text):
            text = pattern.sub(line, text, count=1)
        else:
            # The key is new; insert it before the categories line.
            text = re.sub(r"^categories:", line + "\ncategories:", text, count=1, flags=re.M)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out = args.out
    with open(os.path.join(out, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)

    kept, newly_excluded, mixed_titles = [], [], []

    for page in manifest["pages"]:
        off_topic, foreign, mixed = topic_check(
            {"title": page["title"], "categories": page.get("categories") or []}
        )
        md = os.path.join(out, "pages", page["slug"] + ".md")
        html = os.path.join(out, "html", page["slug"] + ".html")

        if off_topic:
            newly_excluded.append(
                {"title": page["title"], "url": page.get("url"),
                 "categories": page.get("categories") or [],
                 "foreign_games": foreign,
                 "reason": "reclassified: title or categories place it outside this game"}
            )
            if not args.dry_run:
                for victim in (md, html):
                    if os.path.exists(victim):
                        os.remove(victim)
            continue

        page["off_topic"] = False
        page["mixed_scope"] = mixed
        page["foreign_games"] = foreign
        if mixed:
            mixed_titles.append(page["title"])
        if not args.dry_run and os.path.exists(md):
            _rewrite_frontmatter(md, False, mixed, foreign)
        kept.append(page)

    print("kept %d pages, newly excluded %d, flagged mixed_scope %d"
          % (len(kept), len(newly_excluded), len(mixed_titles)))
    for item in newly_excluded:
        print("  excluded: %s  %s" % (item["title"], item["foreign_games"]))
    for title in mixed_titles:
        print("  mixed:    %s" % title)

    if args.dry_run:
        print("\ndry run: nothing written")
        return 0

    existing = manifest.get("excluded", [])
    seen = {e["title"] for e in existing}
    manifest["excluded"] = existing + [e for e in newly_excluded if e["title"] not in seen]
    manifest["pages"] = kept
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(out, "excluded.json"), "w", encoding="utf-8") as f:
        json.dump(manifest["excluded"], f, indent=2)
    print("\nmanifest and excluded.json rewritten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
