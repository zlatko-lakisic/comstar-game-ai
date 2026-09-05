#!/usr/bin/env python3
"""
Export Rome-related pages and images from the Total War Wiki on Fandom.

Uses the official MediaWiki API. Polite by default: one request per second,
identifying User-Agent, resumable, and it records the attribution data that
CC BY-SA requires.

Usage:
    python wiki_export.py --out ./kb/raw/fandom --contact you@example.com
    python wiki_export.py --out ./kb/raw/fandom --contact you@example.com --no-images
    python wiki_export.py --out ./kb/raw/fandom --contact you@example.com --discover-only

Output layout:
    <out>/pages/<slug>.md          wikitext + YAML frontmatter with provenance
    <out>/html/<slug>.html         parsed HTML, kept for table extraction
    <out>/images/<filename>        downloaded files
    <out>/manifest.json            every page and image with metadata
    <out>/attribution.md           contributor list per page, for CC BY-SA
    <out>/.state.json              resume state
"""

import argparse, json, os, re, sys, time, hashlib
from urllib.parse import quote
import urllib.request, urllib.error

API = "https://totalwar.fandom.com/api.php"

# Seed categories. The script walks subcategories from these. Names are a
# starting guess: run with --discover-only first and check what actually exists.
SEED_CATEGORIES = [
    "Category:Rome: Total War",
    "Category:Total War: Rome Remastered",
    "Category:Rome: Total War - Barbarian Invasion",
    "Category:Rome: Total War - Alexander",
]

# Namespaces worth keeping. 0 = article, 14 = category (for structure only).
KEEP_NS = {0}
SKIP_TITLE_PREFIXES = ("User:", "User blog:", "Talk:", "Thread:", "Board:",
                       "Blog:", "Forum:", "Template:", "Special:")

RATE = 1.0          # seconds between requests
MAX_DEPTH = 3       # subcategory recursion depth


def slugify(title):
    """Filesystem-safe name for a page title.

    Lossy by design, which is why `unique_slug` exists: stripping punctuation maps
    "Rome: Total War" and "Rome Total War" onto the same string, and two pages
    writing to one file means the second silently overwrites the first.
    """
    s = re.sub(r"[^A-Za-z0-9._ -]", "", title).strip().replace(" ", "_")
    return s[:120] or hashlib.sha1(title.encode()).hexdigest()[:16]


def unique_slug(title, taken):
    """`slugify` plus a title-derived suffix when the slug is already claimed.

    Keyed on the title's hash rather than a counter so the same title always gets
    the same file, which is what makes a re-run overwrite cleanly instead of
    shuffling pages between files.
    """
    base = slugify(title)
    if base not in taken:
        taken[base] = title
        return base
    if taken[base] == title:
        return base
    suffixed = "%s-%s" % (base[:110], hashlib.sha1(title.encode()).hexdigest()[:8])
    taken[suffixed] = title
    return suffixed


class Api:
    def __init__(self, contact, rate=RATE):
        self.ua = ("ComstarGameAI-KB-Export/1.0 "
                   "(https://github.com/zlatko-lakisic/comstar-game-ai; %s)" % contact)
        self.rate = rate
        self.last = 0.0
        self.calls = 0

    def _wait(self):
        dt = time.time() - self.last
        if dt < self.rate:
            time.sleep(self.rate - dt)
        self.last = time.time()

    def get(self, params, retries=4):
        params = dict(params)
        params.setdefault("format", "json")
        params.setdefault("formatversion", "2")
        url = API + "?" + "&".join("%s=%s" % (k, quote(str(v), safe="|:")) for k, v in params.items())
        for attempt in range(retries):
            self._wait()
            req = urllib.request.Request(url, headers={"User-Agent": self.ua,
                                                       "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=45) as r:
                    self.calls += 1
                    return json.loads(r.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 503, 502, 500) and attempt < retries - 1:
                    back = 4 * (attempt + 1)
                    print("  http %d, backing off %ds" % (e.code, back), file=sys.stderr)
                    time.sleep(back)
                    continue
                raise
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise
        raise RuntimeError("gave up on " + url)

    def paged(self, params, listkey):
        params = dict(params)
        while True:
            data = self.get(params)
            for item in data.get("query", {}).get(listkey, []):
                yield item
            cont = data.get("continue")
            if not cont:
                return
            params.update(cont)

    def pages_merged(self, params):
        """Run a `prop=` query to completion and merge continuations per page.

        `prop=categories|images|contributors` are all capped per request, and the
        overflow comes back behind a `continue` token. A single `get` therefore
        returns a *truncated* list with no error: a page with 60 categories reports
        whichever the first response happened to include. That silently
        under-reports categories, which is what the version classifier keys on.

        Returns title -> page dict, with list-valued props concatenated.
        """
        params = dict(params)
        merged = {}
        while True:
            data = self.get(params)
            for page in data.get("query", {}).get("pages", []):
                title = page.get("title")
                if title is None:
                    continue
                if title not in merged:
                    merged[title] = page
                    continue
                existing = merged[title]
                for key, value in page.items():
                    if isinstance(value, list):
                        existing[key] = existing.get(key, []) + value
                    else:
                        existing.setdefault(key, value)
            cont = data.get("continue")
            if not cont:
                return merged
            params.update(cont)

    def download(self, url, dest):
        self._wait()
        req = urllib.request.Request(url, headers={"User-Agent": self.ua})
        with urllib.request.urlopen(req, timeout=90) as r, open(dest, "wb") as f:
            f.write(r.read())
        self.calls += 1


# ------------------------------------------------------------- topic guarding
# Recursion has to be fenced or it leaves the game entirely. Observed: the seed
# `Category:Rome: Total War gameplay mechanics` contains the subcategory
# `Category:Religion`, which is shared across the whole franchise, so a depth-3 walk
# collected Catholicism, Islam, Orthodoxy and Buddhism -- none of which exist in this
# game. Barbarian Invasion does have Christianity and Paganism, which is what makes
# the leak plausible enough to survive a glance at the file list.
ROME_PATTERNS = (
    r"rome:\s*total\s*war",          # Rome: Total War and its expansions
    r"total\s*war:\s*rome\s*remastered",
    r"\(rome:\s*total\s*war\)",      # e.g. Units (Rome: Total War)
    r"\(total\s*war:\s*rome\s*remastered\)",
    r"barbarian\s*invasion",
    r"alexander",
)

# Other games in the franchise. Their pages would read as authoritative and be wrong
# for every purpose here, Rome II most dangerously of all because it shares unit names.
#
# These must name a *game*, not merely contain a word another game uses. Bare tokens
# fail in both directions and the failures look reasonable: `pharaoh` excluded
# "Pharaoh's Guards" and "Pharaoh's Bowmen", which are Egyptian units in this game;
# `attila` would exclude Attila the Hun, who is in Barbarian Invasion; `arena` would
# exclude the Roman arena; `troy` would exclude the city. So anything that doubles as
# ordinary Rome vocabulary is required to appear in its full game-title form.
NOT_ROME_PATTERNS = (
    r"rome\s*(ii|2)\b",
    r"medieval",
    r"shogun",
    r"empire:\s*total\s*war",
    r"napoleon",
    r"warhammer",
    r"three\s*kingdoms",
    r"thrones\s*of\s*britannia",
    r"total\s*war\s*saga",
    r"total\s*war:\s*attila",
    r"total\s*war:\s*troy",
    r"total\s*war:\s*pharaoh",
    r"total\s*war:\s*arena",
)


# Categories with no prose value: wiki housekeeping, and image collections whose
# members are files rather than articles. Walking these costs requests and returns
# nothing usable.
NOISE_PATTERNS = (
    r"articles?\s",
    r"needing",
    r"\bstub",
    r"candidates?\s+for",
    r"disambiguation",
    r"pages\s+with",
    r"navbox",
    r"imagery",
    r"screenshots",
    r"unit\s*cards",
    r"unit\s*portraits",
    r"icons",
    r"images",
    r"browse",
)


def _matches(name, patterns):
    low = name.lower()
    return any(re.search(p, low) for p in patterns)


def is_rome_scoped(name):
    """True when a category or page name belongs to Rome 1 / Remastered / BI / Alexander."""
    if _matches(name, NOT_ROME_PATTERNS):
        return False
    return _matches(name, ROME_PATTERNS)


def should_walk(cat):
    """Whether to recurse into a subcategory found under a Rome-scoped parent.

    A denylist, not an allowlist. Requiring the *name* to say Rome looked safer but
    was wrong in both directions: it fenced off `Category:Celtic Units`,
    `Category:Berber Units` and `Category:Romano-British Units`, which are genuine
    Barbarian Invasion content, while a name-based rule can never reliably separate
    those from `Category:Religion`. The membership settles it — every page under the
    faction categories carries a real Barbarian Invasion category and every page
    under `Category:Religion` carries none — so the walk is left broad and each page
    is validated on its own categories by `topic_check`.
    """
    if _matches(cat, NOT_ROME_PATTERNS):
        return False
    return not _matches(cat, NOISE_PATTERNS)


# ------------------------------------------------------------------ discovery
def discover_categories(api, pattern="rome"):
    """List every category on the wiki whose name mentions Rome."""
    found = []
    for c in api.paged({"action": "query", "list": "allcategories",
                        "aclimit": "500"}, "allcategories"):
        name = c["category"] if isinstance(c, dict) else c
        if pattern.lower() in name.lower():
            found.append("Category:" + name)
    return sorted(found)


def category_members(api, cat, depth=0, seen=None, skipped=None):
    """Recursively collect article titles under a category, staying inside Rome.

    A subcategory is only followed when its own name is Rome-scoped. Seeds are
    trusted as given, so an explicitly passed category is always read.
    """
    seen = seen if seen is not None else set()
    skipped = skipped if skipped is not None else set()
    if cat in seen or depth > MAX_DEPTH:
        return []
    seen.add(cat)
    titles, subcats = [], []
    for m in api.paged({"action": "query", "list": "categorymembers",
                        "cmtitle": cat, "cmlimit": "500",
                        "cmtype": "page|subcat"}, "categorymembers"):
        if m["ns"] == 14:
            subcats.append(m["title"])
        elif m["ns"] in KEEP_NS and not m["title"].startswith(SKIP_TITLE_PREFIXES):
            titles.append(m["title"])
    for sc in subcats:
        if not should_walk(sc):
            if sc not in skipped:
                skipped.add(sc)
                print("    not walked: %s" % sc)
            continue
        titles.extend(category_members(api, sc, depth + 1, seen, skipped))
    return titles


# ------------------------------------------------------------------ content
def fetch_pages(api, titles, batch=20):
    """Yield dicts with wikitext, revision info and categories."""
    for i in range(0, len(titles), batch):
        chunk = titles[i:i + batch]
        pages = api.pages_merged({"action": "query", "titles": "|".join(chunk),
                                  "prop": "revisions|categories|info",
                                  "rvprop": "content|timestamp|ids|user",
                                  "rvslots": "main", "cllimit": "max",
                                  "inprop": "url"})
        for p in pages.values():
            if "missing" in p:
                continue
            rev = (p.get("revisions") or [{}])[0]
            yield {
                "title": p["title"],
                "pageid": p.get("pageid"),
                "url": p.get("fullurl"),
                "revid": rev.get("revid"),
                "touched": rev.get("timestamp"),
                "last_editor": rev.get("user"),
                "categories": [c["title"] for c in p.get("categories", [])],
                "wikitext": (rev.get("slots", {}).get("main", {}) or {}).get("content", ""),
            }


def fetch_html(api, title):
    d = api.get({"action": "parse", "page": title, "prop": "text"})
    return d.get("parse", {}).get("text", "")


def fetch_contributors(api, title):
    # Merged: a page with many editors returns them across several responses, and a
    # truncated contributor list is an incomplete CC BY-SA credit.
    pages = api.pages_merged({"action": "query", "titles": title,
                              "prop": "contributors", "pclimit": "max"})
    for page in pages.values():
        return [c["name"] for c in page.get("contributors", [])]
    return []


def fetch_page_images(api, titles, batch=20):
    """Map page title -> list of File: titles used on it."""
    out = {}
    for i in range(0, len(titles), batch):
        chunk = titles[i:i + batch]
        pages = api.pages_merged({"action": "query", "titles": "|".join(chunk),
                                  "prop": "images", "imlimit": "max"})
        for title, p in pages.items():
            out[title] = [im["title"] for im in p.get("images", [])]
    return out


def fetch_image_info(api, file_titles, batch=20):
    """File: title -> {url, mime, size, license, author}."""
    info = {}
    for i in range(0, len(file_titles), batch):
        chunk = file_titles[i:i + batch]
        pages = api.pages_merged({"action": "query", "titles": "|".join(chunk),
                                  "prop": "imageinfo",
                                  "iiprop": "url|mime|size|extmetadata"})
        for p in pages.values():
            ii = (p.get("imageinfo") or [{}])[0]
            ex = ii.get("extmetadata", {}) or {}
            def meta(k):
                v = ex.get(k, {})
                return re.sub(r"<[^>]+>", "", str(v.get("value", ""))).strip()
            info[p["title"]] = {
                "url": ii.get("url"),
                "mime": ii.get("mime"),
                "width": ii.get("width"),
                "height": ii.get("height"),
                "size": ii.get("size"),
                "license": meta("LicenseShortName") or meta("License"),
                "author": meta("Artist"),
                "description": meta("ImageDescription")[:400],
            }
    return info


# ------------------------------------------------------------------ writing
FRONTMATTER = """---
source: Total War Wiki (Fandom)
source_url: {url}
title: {title}
pageid: {pageid}
revid: {revid}
revision_date: {touched}
retrieved: {retrieved}
license: CC BY-SA (confirm the exact version on the wiki footer before redistributing)
game_version: UNVERIFIED
mod: UNVERIFIED
confidence: unrated
off_topic: {off_topic}
mixed_scope: {mixed_scope}
foreign_games: {foreign_games}
categories: {categories}
---

"""


def topic_check(rec):
    """Classify a page as (off_topic, foreign_games, mixed_scope).

    Three cases, and an earlier version collapsed the last two:

    * **Off topic.** No Rome category and no Rome-scoped title. Franchise-wide
      articles like Catholicism and Buddhism land here and are excluded.
    * **Named for another game.** A title such as "Ilyrian Levies (Total War:
      Rome II)" is a Rome II unit that the wiki also filed under a Rome 1 category.
      Accepting a page because *some* category matches let it through with a title
      that says outright it is a different game, so the title now vetoes.
    * **Mixed scope.** Genuinely shared pages — Rebels, Siege, Melee Infantry — that
      cover Rome alongside other titles. Kept, because dropping them would lose real
      Rome content, but flagged: a reader must not treat their numbers as Rome's.
    """
    cats = [c.replace("Category:", "") for c in rec.get("categories") or []]
    foreign = sorted({c for c in cats if _matches(c, NOT_ROME_PATTERNS)})
    title = rec["title"]

    # A title naming another game overrides any category evidence.
    if _matches(title, NOT_ROME_PATTERNS):
        return True, foreign, False

    on_topic = any(is_rome_scoped(c) for c in cats) or is_rome_scoped(title)
    mixed = bool(foreign) and on_topic
    return (not on_topic), foreign, mixed


def load_state(out):
    """Resume state: which titles are already written, and the slugs they claimed.

    The docstring promised `.state.json` but nothing wrote or read it, so an
    interrupted export restarted from zero and re-spent the whole request budget.
    """
    path = os.path.join(out, ".state.json")
    if not os.path.exists(path):
        return {"done": {}, "slugs": {}}
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        return {"done": {}, "slugs": {}}
    state.setdefault("done", {})
    state.setdefault("slugs", {})
    return state


def save_state(out, state):
    tmp = os.path.join(out, ".state.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, os.path.join(out, ".state.json"))


def write_page(outdir, rec, retrieved, slug):
    path = os.path.join(outdir, "pages", slug + ".md")
    off_topic, foreign, mixed = topic_check(rec)
    fm = FRONTMATTER.format(
        url=rec.get("url", ""), title=rec["title"].replace(":", " -"),
        pageid=rec.get("pageid"), revid=rec.get("revid"),
        touched=rec.get("touched"), retrieved=retrieved,
        off_topic=json.dumps(off_topic), mixed_scope=json.dumps(mixed),
        foreign_games=json.dumps(foreign),
        categories=json.dumps([c.replace("Category:", "") for c in rec["categories"]]),
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(fm)
        f.write(rec["wikitext"])
    return slug, path


def _load_manifest(out):
    path = os.path.join(out, "manifest.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--contact", default="https://github.com/zlatko-lakisic/comstar-game-ai",
                    help="contact string for the User-Agent header. Not a login and not "
                         "sent to Fandom as credentials; it identifies the client so an "
                         "operator can reach you instead of blocking you. A repo URL is "
                         "fine, an email is fine. Defaults to the project repo URL.")
    ap.add_argument("--rate", type=float, default=RATE)
    # Images are opt-in, not opt-out. The wiki's text is CC BY-SA but its uploaded
    # screenshots and unit cards are the publisher's assets under the wiki's own fair
    # use claim, this repo is public, and the game install has better copies anyway.
    # A default that downloads them makes the risky choice the easy one.
    ap.add_argument("--images", action="store_true",
                    help="also download referenced files (off by default; see the "
                         "ingestion brief section 6 before turning this on)")
    ap.add_argument("--no-images", action="store_true",
                    help="accepted for compatibility; images are already off by default")
    ap.add_argument("--no-html", action="store_true")
    ap.add_argument("--discover-only", action="store_true")
    ap.add_argument("--restart", action="store_true",
                    help="ignore .state.json and export every page again")
    ap.add_argument("--max-image-mb", type=float, default=8.0)
    ap.add_argument("--categories", nargs="*", default=None,
                    help="override the seed categories")
    args = ap.parse_args()

    api = Api(args.contact, args.rate)
    out = args.out
    for sub in ("pages", "html", "images"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)

    if args.discover_only:
        print("Categories on the wiki mentioning 'rome':\n")
        for c in discover_categories(api):
            print("  " + c)
        print("\nPass the ones you want with --categories, then rerun without "
              "--discover-only.")
        return

    seeds = args.categories or SEED_CATEGORIES
    print("Collecting page titles from %d seed categories" % len(seeds))
    titles, seen = [], set()
    for cat in seeds:
        got = category_members(api, cat)
        print("  %-52s %4d pages" % (cat, len(got)))
        for t in got:
            if t not in seen:
                seen.add(t); titles.append(t)
    print("total unique pages: %d\n" % len(titles))

    retrieved = time.strftime("%Y-%m-%d")

    state = {"done": {}, "slugs": {}} if args.restart else load_state(out)
    previous = _load_manifest(out) or {}
    manifest = {"source": "totalwar.fandom.com", "retrieved": retrieved,
                "seed_categories": seeds, "pages": [], "images": []}
    attribution = []
    flagged = []
    excluded = []

    if state["done"]:
        # Carry forward manifest and attribution for pages already on disk, or a
        # resumed run would finish with a manifest describing only the tail.
        by_title = {p["title"]: p for p in previous.get("pages", [])}
        for title in state["done"]:
            if title in by_title:
                manifest["pages"].append(by_title[title])
        remaining = [t for t in titles if t not in state["done"]]
        print("resuming: %d of %d pages already exported, %d to go"
              % (len(state["done"]), len(titles), len(remaining)))
        titles = remaining
        if not titles:
            print("nothing left to export; use --restart to force a full re-run")

    for n, rec in enumerate(fetch_pages(api, titles), 1):
        off_topic, foreign, mixed = topic_check(rec)
        if off_topic:
            # Not written to pages/. The walk is deliberately broad, so it reaches
            # franchise-wide articles like Catholicism and Buddhism whose categories
            # place them in no Rome game at all. Recorded rather than dropped so the
            # exclusion is auditable and a mis-fenced page is visible.
            excluded.append({"title": rec["title"], "url": rec.get("url"),
                             "categories": rec.get("categories") or [],
                             "foreign_games": foreign})
            state["done"][rec["title"]] = None
            print("[%4d/%4d] excluded (not this game): %s" % (n, len(titles), rec["title"]))
            continue
        slug = unique_slug(rec["title"], state["slugs"])
        slug, path = write_page(out, rec, retrieved, slug)
        entry = {"title": rec["title"], "slug": slug, "url": rec["url"],
                 "revid": rec["revid"], "revision_date": rec["touched"],
                 "categories": rec["categories"],
                 "off_topic": off_topic, "mixed_scope": mixed,
                 "foreign_games": foreign,
                 "bytes": len(rec["wikitext"])}
        if mixed:
            flagged.append(rec["title"])
        if not args.no_html:
            try:
                html = fetch_html(api, rec["title"])
                with open(os.path.join(out, "html", slug + ".html"), "w",
                          encoding="utf-8") as f:
                    f.write(html)
                entry["html"] = "html/%s.html" % slug
            except Exception as e:
                print("  html failed for %s: %s" % (rec["title"], e), file=sys.stderr)
        try:
            contribs = fetch_contributors(api, rec["title"])
            attribution.append((rec["title"], rec["url"], contribs))
        except Exception:
            pass
        manifest["pages"].append(entry)
        state["done"][rec["title"]] = slug
        if n % 10 == 0:
            save_state(out, state)
        print("[%4d/%4d] %s" % (n, len(titles), rec["title"]))

    save_state(out, state)

    if args.images and not args.no_images:
        print("\nCollecting images")
        page_imgs = fetch_page_images(api, titles)
        wanted = sorted({f for files in page_imgs.values() for f in files})
        print("  %d distinct files referenced" % len(wanted))
        info = fetch_image_info(api, wanted)
        for n, (ftitle, meta) in enumerate(info.items(), 1):
            url = meta.get("url")
            if not url:
                continue
            if meta.get("size") and meta["size"] > args.max_image_mb * 1024 * 1024:
                print("  skip oversized %s" % ftitle); continue
            fname = slugify(ftitle.replace("File:", ""))
            ext = os.path.splitext(url.split("?")[0])[1][:6] or ".bin"
            if not fname.lower().endswith(ext.lower()):
                fname += ext
            dest = os.path.join(out, "images", fname)
            if not os.path.exists(dest):
                try:
                    api.download(url, dest)
                except Exception as e:
                    print("  failed %s: %s" % (ftitle, e), file=sys.stderr); continue
            meta.update({"file": "images/%s" % fname, "title": ftitle,
                         "used_on": [p for p, fs in page_imgs.items() if ftitle in fs]})
            manifest["images"].append(meta)
            print("[%4d/%4d] %s" % (n, len(info), ftitle))

    manifest["excluded"] = excluded
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    with open(os.path.join(out, "excluded.json"), "w", encoding="utf-8") as f:
        json.dump(excluded, f, indent=2)

    with open(os.path.join(out, "attribution.md"), "w", encoding="utf-8") as f:
        f.write("# Attribution\n\nText from the Total War Wiki on Fandom, "
                "reused under its CC BY-SA licence. Retrieved %s.\n\n" % retrieved)
        for title, url, contribs in attribution:
            f.write("## %s\n\n%s\n\nContributors: %s\n\n"
                    % (title, url, ", ".join(contribs) if contribs else "see page history"))

    print("\nDone. %d pages, %d images, %d API calls."
          % (len(manifest["pages"]), len(manifest["images"]), api.calls))
    if excluded:
        print("%d pages excluded as not belonging to this game (see excluded.json):"
              % len(excluded))
        for item in excluded[:25]:
            print("  " + item["title"])
    if flagged:
        print("%d pages kept but mixed_scope: they cover Rome alongside other titles, "
              "so their numbers are not necessarily Rome's:" % len(flagged))
        for title in flagged[:25]:
            print("  " + title)
    if not args.images:
        print("Images not downloaded (default). Pass --images only after reading "
              "section 6 of the ingestion brief.")
    print("Output in %s" % os.path.abspath(out))


if __name__ == "__main__":
    main()
