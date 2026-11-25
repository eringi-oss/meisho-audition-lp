#!/usr/bin/env python3
"""Insert BudouX phrase-boundary <wbr> into the audition LP HTML (idempotent)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import budoux

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = ROOT / "index.html"

PARSER = budoux.load_default_japanese_parser()

# Never split these internally. Long titles are intentionally omitted so they
# can wrap at phrase boundaries when they exceed the viewport.
ATOMS = sorted(
    {
        "ヒューリックホール東京",
        "品川インターシティホール",
        "エスコンフィールドHOKKAIDO",
        "Anime Festival Asia",
        "Next Stage",
        "NOAH HAKONE（箱根）",
        "日本武道館",
        "在り来たりな日常と幸運な日々へ",
        "在り来たりな",
        "あしたはあしたのけせらせら！",
        "拝啓、名もない私たちへ。",
        "モブせか2",
        "ここ俺",
        "世界です2",
        "地縛少年花子くん",
        "ボクらの最終定理",
        "ゴシック＆ロリータ",
        "心を動かせる人",
        "心を動かせる",
        "心を動かす",
        "上手い人",
        "エンディングテーマ",
        "インドネシア",
        "タイアップ",
        "ワンマンライブデビュー",
        "ワンマンライブ",
        "ホールワンマン",
        "試合後スペシャルライブ出演",
        "試合後ライブ",
        "名称非公開",
        "新メンバーオーディション",
        "公式LINE",
        "応募フォーム",
        "オリコンウィークリーチャート",
        "オリコン週間",
        "プロフィールを見る",
        "よくある質問",
        "本格始動します",
        "本格始動",
        "友だち追加して応募する",
        "『ここ俺』",
        "『モブせか2』",
    },
    key=len,
    reverse=True,
)

# Multi-word Latin units must not wrap at their internal spaces.
NOWRAP_ATOMS = {
    "Anime Festival Asia", "Next Stage", "NOAH HAKONE（箱根）",
    "“本物”へ。", "“本物”へ", "“心を動かせる人”。", "“心を動かせる人”", "“上手い人”",
    "『ここ俺』", "『モブせか2』",
}

MANUAL = {
    "Anime Festival Asia Indonesia 2026 Next Stage出演": [
        "Anime Festival Asia",
        " Indonesia 2026 ",
        "Next Stage",
        "出演",
    ],
}

DATE_RE = re.compile(
    r"(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\([^)]+\)|（[^）]+）)?"
    r"(?:〜\d{1,2}日(?:\([^)]+\)|（[^）]+）)?)?"
    r"(?:\s*[0-9:.]+)?"
    r"|20\d{2}年(?:\d{1,2}月(?:下旬|中旬|上旬)?|夏|春|秋|冬)(?:には|は|に)?"
    r"|\d{1,2}月(?:下旬|中旬|上旬)"
)

ATOM_RE = re.compile(
    "("
    + "|".join(re.escape(a) for a in ATOMS)
    + "|"
    + DATE_RE.pattern
    + ")"
)

TOKEN_RE = re.compile(
    r"<!--.*?-->"
    r"|<script\b[^>]*>.*?</script>"
    r"|<style\b[^>]*>.*?</style>"
    r"|<svg\b[^>]*>.*?</svg>"
    r"|</[a-zA-Z][\w:-]*\s*>"
    r"|<[a-zA-Z][\w:-]*\b[^>]*?/?>"
    r"|[^<]+",
    re.I | re.S,
)

SKIP_TAGS = {"script", "style", "svg", "code", "pre", "textarea"}
KEEP_NOWRAP_IN = {"deadline", "dl-range", "dl-label"}
SKIP_PROCESS_IN = {"deadline", "dl-range", "dl-label", "nowrap"}

JUDGE_BLURBS = [
    '<p>1人で何役も演じ分ける、<span class="nowrap">独特な歌声。</span></p>\n',
    '<p>ZOCの振付師兼メンバーとして3年半活動。<span class="nowrap">「名称非公開」はじめ、</span>様々なアイドルグループに振付を提供。</p>\n',
]


def tag_name(tok: str) -> str:
    m = re.match(r"</?([a-zA-Z][\w:-]*)", tok)
    return m.group(1).lower() if m else ""


def tag_classes(tok: str) -> list[str]:
    m = re.search(r'\bclass="([^"]*)"', tok)
    return m.group(1).split() if m else []


def is_void_or_selfclose(tok: str, name: str) -> bool:
    if tok.startswith("</"):
        return False
    if tok.rstrip().endswith("/>"):
        return True
    return name in {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }


def split_phrases(text: str) -> list[str]:
    for src, parts in MANUAL.items():
        if src in text:
            out: list[str] = []
            for piece in text.split(src):
                if out or text.startswith(src):
                    # The split pieces around src; handle via regex walk instead
                    pass
            # Use a general walk:
            chunks: list[str] = []
            i = 0
            while i < len(text):
                hit = None
                for k, v in MANUAL.items():
                    if text.startswith(k, i):
                        hit = (k, v)
                        break
                if hit:
                    chunks.extend(hit[1])
                    i += len(hit[0])
                    continue
                nxt = len(text)
                for k in MANUAL:
                    j = text.find(k, i)
                    if j != -1:
                        nxt = min(nxt, j)
                segment = text[i:nxt]
                chunks.extend(_split_segment(segment))
                i = nxt
            return [c for c in chunks if c != ""]
    return _split_segment(text)


LEAD_PUNCT = re.compile("^[「『（(\x5b【［《〈“]+$")
TRAIL_ATTACH = re.compile(
    "^(?:[”」』）)]*)(?:での|では|には|にも|のは|のが|のを|とは|とも|から|まで|より|など|って|という|といった|"
    "[はがをにのともへでやかも])?[、。,.!！?？』」］】〕）)”“…・：:；;]*$"
)

def _merge_chunks(chunks: list[str]) -> list[str]:
    merged: list[str] = []
    for ph in chunks:
        if ph == "":
            continue
        if not merged:
            merged.append(ph)
            continue
        if LEAD_PUNCT.fullmatch(merged[-1]):
            merged[-1] += ph
            continue
        if LEAD_PUNCT.fullmatch(ph):
            merged.append(ph)
            continue
        if TRAIL_ATTACH.fullmatch(ph) and ph != "":
            # Keep a break after a long proper noun rather than gluing
            # での/では onto it (that forced earlier wraps on narrow screens).
            if re.fullmatch(r"^(?:での|では)[、。]*$", ph) and len(merged[-1]) >= 6:
                merged.append(ph)
                continue
            merged[-1] += ph
            continue
        if ph[0] in "”」』）)]" and not LEAD_PUNCT.fullmatch(ph):
            merged[-1] += ph[0]
            ph = ph[1:]
            if not ph:
                continue
        merged.append(ph)
    # attach a leftover opening punct to the following chunk if it is last-but dangling
    i = 0
    out: list[str] = []
    while i < len(merged):
        if i + 1 < len(merged) and LEAD_PUNCT.fullmatch(merged[i]):
            out.append(merged[i] + merged[i + 1])
            i += 2
        else:
            out.append(merged[i])
            i += 1
    return out

def _split_segment(text: str) -> list[str]:
    if not text:
        return []
    parts = ATOM_RE.split(text)
    chunks: list[str] = []
    for part in parts:
        if part == "" or part is None:
            continue
        if part in ATOMS or DATE_RE.fullmatch(part):
            chunks.append(part)
        else:
            chunks.extend(PARSER.parse(part))
    return _merge_chunks(chunks)


def phrases_to_html(phrases: list[str]) -> str:
    if len(phrases) <= 1 and not (phrases and phrases[0] in NOWRAP_ATOMS):
        return phrases[0] if phrases else ""
    out = []
    for i, ph in enumerate(phrases):
        if i:
            out.append("<wbr>")
        if ph in NOWRAP_ATOMS or any(ph == a or (ph.startswith(a) and len(ph) - len(a) <= 4) for a in NOWRAP_ATOMS):
            out.append(f'<span class="nowrap">{ph}</span>')
        else:
            out.append(ph)
    return "".join(out)


def update_css(html: str) -> str:
    html = html.replace(
        "word-break:normal;overflow-wrap:break-word;line-break:strict",
        "word-break:keep-all;overflow-wrap:anywhere;line-break:strict",
    )
    html = html.replace(
        "line-break:strict;word-break:normal;overflow-wrap:break-word",
        "line-break:strict;word-break:keep-all;overflow-wrap:anywhere",
    )
    html = html.replace("p,li,dd{", "p,li,dd,dt{", 1)
    html = html.replace(".bio{margin-top:4px}", ".bio{margin-top:10px}")
    html = html.replace(
        ".sns{display:flex;flex-wrap:wrap;gap:2px;margin-top:4px}",
        ".sns{display:flex;flex-wrap:wrap;gap:2px;margin-top:8px}",
    )
    return html


def remove_judge_blurbs(html: str) -> str:
    for blurb in JUDGE_BLURBS:
        if blurb in html:
            html = html.replace(blurb, "", 1)
            continue
        alt = blurb.rstrip("\n")
        if alt in html:
            html = html.replace(alt, "", 1)
    return html


def _unwrap_nowrap_outside_deadline(html: str) -> str:
    parts = re.split(r'(<p class="deadline">.*?</p>)', html, flags=re.S)
    out = []
    for part in parts:
        if part.startswith('<p class="deadline"'):
            out.append(part)
        else:
            out.append(re.sub(r'<span class="nowrap">([^<]*)</span>', r"\1", part))
    return "".join(out)


def transform_markup(html: str) -> str:
    """Unwrap leftover nowrap (except deadline), drop old wbr, insert new wbr."""
    # Re-join text nodes before tokenizing so the pass is idempotent.
    html = html.replace("<wbr>", "").replace("<wbr/>", "").replace("<wbr />", "")
    html = _unwrap_nowrap_outside_deadline(html)
    out: list[str] = []
    stack: list[tuple[str, list[str]]] = []
    unwrap_depth = 0  # number of nowrap spans we are stripping

    def in_classes(wanted: set[str]) -> bool:
        for _, cls in stack:
            if any(c in wanted for c in cls):
                return True
        return False

    for tok in TOKEN_RE.findall(html):
        if tok.startswith("<") and not tok.startswith("<!--"):
            name = tag_name(tok)
            closing = tok.startswith("</")
            classes = tag_classes(tok)

            if not closing and name == "wbr":
                # drop existing wbr; new ones are inserted in text
                continue

            if not closing and name == "span" and "nowrap" in classes:
                if in_classes(KEEP_NOWRAP_IN) or "deadline" in classes:
                    stack.append((name, classes))
                    out.append(tok)
                    continue
                # unwrap this nowrap span
                unwrap_depth += 1
                stack.append((name, classes + ["__unwrap__"]))
                continue

            if closing and name == "span" and stack and stack[-1][0] == "span" and "__unwrap__" in stack[-1][1]:
                stack.pop()
                unwrap_depth = max(0, unwrap_depth - 1)
                continue

            if closing:
                # pop matching opening
                for i in range(len(stack) - 1, -1, -1):
                    if stack[i][0] == name:
                        stack.pop(i)
                        break
                out.append(tok)
                continue

            if name not in SKIP_TAGS and not is_void_or_selfclose(tok, name):
                stack.append((name, classes))
            out.append(tok)
            continue

        # comments or skipped raw blocks
        if tok.startswith("<!--") or tok.startswith("<script") or tok.startswith("<style") or tok.startswith("<svg"):
            out.append(tok)
            continue

        # text node
        if in_classes(SKIP_PROCESS_IN) or any(n in SKIP_TAGS for n, _ in stack):
            out.append(tok)
            continue
        # Don't touch text that is only whitespace, or clearly non-prose (pure ASCII short)
        if not tok or tok.isspace():
            out.append(tok)
            continue
        phrases = split_phrases(tok)
        out.append(phrases_to_html(phrases))

    return "".join(out)


def apply(html: str) -> str:
    html = remove_judge_blurbs(html)
    html = update_css(html)
    html = transform_markup(html)
    return html


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TARGET
    src = path.read_text()
    dst = apply(src)
    path.write_text(dst)
    print(f"wrote {path} ({len(src)} -> {len(dst)} bytes)")
    # sanity
    if "word-break:keep-all" not in dst:
        raise SystemExit("keep-all not applied")
    if "1人で何役も演じ分ける、独特な歌声。" in dst or "ZOCの振付師兼メンバーとして3年半活動。" in dst.split("プロフィールを見る")[0]:
        # The short blurbs should be gone from the card teaser; bio may still mention similar wording after the summary.
        head, _, rest = dst.partition('id="judges"')
        judges, _, after = (rest if rest else dst).partition('id="member"')
        teasers = re.sub(r"<details class=\"bio\">.*?</details>", "", judges, flags=re.S)
        if "1人で何役も演じ分ける、" in teasers or "ZOCの振付師兼メンバーとして3年半活動。" in teasers:
            raise SystemExit("judge teaser blurbs still present")
    plain = dst.replace("<wbr>", "")
    if "プロフィールを見る" not in plain or "多摩美術大学演劇舞踊デザイン学科卒業" not in plain:
        raise SystemExit("yamanokuchi full profile missing")
    print("sanity ok; wbr count", dst.count("<wbr>"))


if __name__ == "__main__":
    main()
