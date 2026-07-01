#!/usr/bin/env python3
#
# clean_session.py
#   Reformat a Claude Code session log (.jsonl) into a human-readable file.
#
#   - prints a summary header as // comments
#   - drops noisy records/fields
#   - renders escaped \n as real line breaks
#
# Usage1: ./clean_session.py <input.jsonl>
# Usage2: RENDER_ONLY=1 ./clean_session.py <input.jsonl>
# 
#
#   Output goes to ./cleaned/<aiTitle>.jsonl by default.
#   Override the output directory with the OUTDIR environment variable.
#   
#   Set RENDER_ONLY=1 to skip all record/field removal (newline rendering only);
#   it writes a separate <aiTitle>.render-only.jsonl for comparison.
#
#   The output filename is derived from the session's aiTitle and is sanitized:
#   path separators and characters illegal on Windows/macOS/Linux are replaced
#   with "_", and the name is length-limited, so it always stays inside OUTDIR.
#
#   NOTE: the output keeps the .jsonl extension for convenience, but because
#   escaped newlines are rendered as real line breaks it is NOT valid JSON/JSONL
#   anymore — it is meant for humans to read, not for re-parsing.
#
# Dependencies: Python 3.8+ only.
#   Works on Linux, macOS, and Windows.

import json
import os
import re
import sys

# ── config ──────────────────────────────────────────
OUTDIR = os.environ.get("OUTDIR", "./cleaned")          # change this !
RENDER_ONLY = os.environ.get("RENDER_ONLY", "") != ""   # non-empty = render only

# top-level fields removed from every record during cleaning
DROP_TOP = (
    "uuid", "requestId", "entrypoint", "userType", "cwd", "gitBranch", "version",
    "origin", "promptId", "messageId", "sessionId", "timestamp", "parentUuid",
    "isSidechain", "promptSource", "permissionMode", "sourceToolAssistantUUID",
    "leafUuid",
)

ICONS = {"user": "👤", "assistant": "🤖", "system": "⚙️", "summary": "📝"}
DEFAULT_ICON = "🔹"

# keys whose string value is broken onto its own (indented) line for readability
WRAP_KEYS = ("content", "text")

# plain scalar stats shown in the header, as (label, Stats attribute).
# These are auto-printed; only the tool-use list and aiTitle lines are
# formatted by hand (they have special layout).
PLAIN_STATS = (
    ("message/assistant", "assistant"),
    ("message/user", "user"),
    ("message total", "message"),
    ("sessionId", "session"),
    ("toolUseResult", "tur"),
)


# ── stats (single pass over the original records) ───
class Stats:
    """All numbers shown in the summary header, collected in one place/one pass."""

    def __init__(self):
        self.assistant = 0
        self.user = 0
        self.message = 0
        self.session = 0
        self.tur = 0                 # toolUseResult present
        self.tools = {}              # tool_use name -> count
        self.titles = []             # aiTitle values, in file order

    def feed(self, rec):
        if not isinstance(rec, dict):
            return
        t = rec.get("type")
        if t == "assistant":
            self.assistant += 1
        elif t == "user":
            self.user += 1
        if rec.get("message") is not None:
            self.message += 1
        if rec.get("sessionId") is not None:
            self.session += 1
        if rec.get("toolUseResult") is not None:
            self.tur += 1
        title = rec.get("aiTitle")
        if title is not None:
            self.titles.append(title)

        msg = rec.get("message")
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = block.get("name")
                        if name is None:
                            name = "(unknown)"
                        self.tools[name] = self.tools.get(name, 0) + 1

    def tools_sorted(self):
        # match the original jq: group_by(name) -> sort_by(count) -> reverse,
        # i.e. descending count, ties broken by descending name.
        items = sorted(self.tools.items(), key=lambda kv: kv[0])  # name asc (stable base)
        items.sort(key=lambda kv: kv[1])                          # count asc (stable)
        items.reverse()                                           # -> count desc
        return items

    @property
    def tools_total(self):
        return sum(self.tools.values())


# ── cleaning transform (mirrors the jq `clean` definition) ──
def clean(rec):
    """Drop noisy fields in place and flatten single-text message content."""
    for key in DROP_TOP:
        rec.pop(key, None)

    msg = rec.get("message")
    if isinstance(msg, dict):
        for key in ("model", "id", "type"):
            msg.pop(key, None)
        content = msg.get("content")
        if (
            isinstance(content, list)
            and len(content) == 1
            and isinstance(content[0], dict)
            and content[0].get("type") == "text"
        ):
            msg["content"] = content[0].get("text")

    tur = rec.get("toolUseResult")
    if isinstance(tur, dict):
        tur.pop("sourceToolAssistantUUID", None)

    return rec


# ── rendering (mirrors the perl pretty-printer) ─────
def render_string(value, cont):
    """Quote a string but turn real newlines into line breaks + continuation
    indent, and drop carriage returns. Literal backslash-n stays as `\\n`."""
    pad = " " * cont
    body = value.replace("\r", "").replace("\n", "\n" + pad)
    return '"' + body + '"'


def emit_value(value, owner_indent):
    """Render a value that sits inline after `"key": ` or as an array element,
    where owner_indent is the indentation of the owning key/element line."""
    if isinstance(value, dict):
        return emit_dict(value, owner_indent)
    if isinstance(value, list):
        return emit_list(value, owner_indent)
    if isinstance(value, str):
        return render_string(value, owner_indent + 2)
    return json.dumps(value, ensure_ascii=False)  # numbers / bool / null


def emit_dict(obj, indent):
    if not obj:
        return "{}"
    inner = indent + 2
    pad = " " * inner
    lines = ["{"]
    items = list(obj.items())
    for i, (key, value) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        key_str = json.dumps(key, ensure_ascii=False)
        if isinstance(value, str) and key in WRAP_KEYS:
            vpad = " " * (inner + 2)
            lines.append(f"{pad}{key_str}:\n{vpad}{render_string(value, inner + 2)}{comma}")
        else:
            lines.append(f"{pad}{key_str}: {emit_value(value, inner)}{comma}")
    lines.append(" " * indent + "}")
    return "\n".join(lines)


def emit_list(arr, indent):
    if not arr:
        return "[]"
    inner = indent + 2
    pad = " " * inner
    lines = ["["]
    for i, value in enumerate(arr):
        comma = "," if i < len(arr) - 1 else ""
        lines.append(f"{pad}{emit_value(value, inner)}{comma}")
    lines.append(" " * indent + "]")
    return "\n".join(lines)


# ── filename handling ───────────────────────────────
def sanitize_filename(name):
    """Make an arbitrary (AI-generated) title safe to use as a single filename."""
    name = name.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    name = re.sub(r'[\\/:*?"<>|]', "_", name)   # path separators + illegal chars
    name = re.sub(r"[\x00-\x1f]", "", name)     # other control chars
    name = name.strip().strip(".").strip()      # no leading/trailing dots/spaces -> no "..", no traversal
    return name[:120].strip()


def read_records(path):
    """Parse a .jsonl file into a list of (lineno, record) pairs, where lineno is
    the 1-based line number in the original file. Blank/invalid lines are skipped."""
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append((lineno, json.loads(line)))
            except json.JSONDecodeError as exc:
                print(f"warning: skipping invalid JSON on line {lineno}: {exc}", file=sys.stderr)
    return records


# ── header ──────────────────────────────────────────
def build_header(stats):
    # plain scalar stats: auto-generated from PLAIN_STATS (no per-line hardcoding)
    lines = ["// ── session raw stats ─────────────────────────"]
    width = max(len(label) for label, _ in PLAIN_STATS)
    for label, attr in PLAIN_STATS:
        lines.append(f"// {label:<{width}} : {getattr(stats, attr)}")

    # tool-use block (hardcoded special layout)
    lines.append(f"// tools used (tool_use total {stats.tools_total})")
    tools = stats.tools_sorted()
    if tools:
        for name, count in tools:
            lines.append(f"//   {name:<16} : {count}")
    else:
        lines.append("//   (none)")

    first_title = stats.titles[0] if stats.titles else None
    if first_title:
        uniq = sorted(set(stats.titles))
        if len(uniq) > 1:
            lines.append(f'// aiTitle : "{first_title}" (changed: {"  →  ".join(uniq)})')
        else:
            lines.append(f'// aiTitle : "{first_title}" (unchanged during session)')
    else:
        lines.append("// aiTitle : (none — using input filename)")

    if RENDER_ONLY:
        lines.append("// (render-only: no records/fields removed)")
    lines.append("// ────────────────────────────────────────────")
    lines.append("")  # blank line between header and body
    return "\n".join(lines) + "\n"


def choose_filename(stats, input_path):
    first_title = stats.titles[0] if stats.titles else None
    fname = sanitize_filename(first_title) if first_title else ""
    if not fname:
        fname = sanitize_filename(os.path.basename(input_path)) or "session"
    if not fname.endswith(".jsonl"):
        fname += ".jsonl"
    if RENDER_ONLY:
        fname = fname[: -len(".jsonl")] + ".render-only.jsonl"
    return fname


# ── main ────────────────────────────────────────────
def main(argv):
    if len(argv) < 2:
        print(f"Usage: {argv[0]} <input.jsonl>", file=sys.stderr)
        return 1
    input_path = argv[1]
    if not os.path.isfile(input_path):
        print(f"error: input file not found: {input_path}", file=sys.stderr)
        return 1

    records = read_records(input_path)  # list of (lineno, record)

    # 1) stats from the original records (before any cleaning)
    stats = Stats()
    for _lineno, rec in records:
        stats.feed(rec)

    # 2) output path
    os.makedirs(OUTDIR, exist_ok=True)
    outpath = os.path.join(OUTDIR, choose_filename(stats, input_path))

    # 3) write header + body
    with open(outpath, "w", encoding="utf-8", newline="\n") as out:
        out.write(build_header(stats))

        for lineno, rec in records:
            is_dict = isinstance(rec, dict)
            rec_type = rec.get("type") if is_dict else None

            if not RENDER_ONLY and rec_type in ("mode", "permission-mode"):
                continue
            if not RENDER_ONLY and is_dict:
                clean(rec)

            # number records by their original line number in the input file,
            # so it stays stable even when records are dropped.
            if is_dict:
                role = rec_type if isinstance(rec_type, str) else "?"
                tag = " · tool result" if "toolUseResult" in rec else ""
            else:
                role, tag = "?", ""
            icon = ICONS.get(role, DEFAULT_ICON)

            out.write(f"// ───────── #{lineno}  {icon} {role}{tag} ─────────\n")
            out.write(emit_value(rec, 0))
            out.write("\n")

    print(f"saved: {outpath}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
