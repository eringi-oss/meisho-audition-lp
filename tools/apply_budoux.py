#!/usr/bin/env python3
"""Keep the audition LP on natural Japanese wrapping (idempotent).

Strips BudouX <wbr> and phrase nowrap (deadline dates stay two lines),
and keeps typography on word-break:normal + line-break:strict.
"""
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
        "目指せる人。",
        "目指せる人",
        "“本物”へ。",
        "“本物”へ",
        "“心を動かせる人”。",
        "“心を動かせる人”",
        "“上手い人”",
        "Anime Festival Asia",
        "Next Stage",
        "日本武道館",
        "在り来たりな",
        "名もない",
        "あしたの",
        "けせらせら！",
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
        "試合後ライブ",
        "スペシャルライブ",
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
    "Anime Festival Asia", "Next Stage",
    "“本物”へ。", "“本物”へ", "“心を動かせる人”。", "“心を動かせる人”", "“上手い人”",
    "『ここ俺』", "『モブせか2』",
}

MANUAL = {
    "Anime Festival Asia Indonesia 2026 Next Stage出演": [
        "Anime Festival Asia",
        " Indonesia 2026",
        " Next Stage",
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


OPEN_CHARS = "「『（([【［《〈“"
CLOSE_CHARS = "」』）)]】］〕》〉”"
# Characters that must not start a line (closing punct / kinsoku).
START_FORBIDDEN = CLOSE_CHARS + "、。,.!！?？…・：:；;"
HAS_JP = re.compile(r"[一-龠ぁ-んァ-ヶ]")
LEAD_PUNCT = re.compile("^[" + re.escape(OPEN_CHARS) + "]+$")
TRAIL_ATTACH = re.compile(
    "^(?:[”」』）)]*)(?:での|では|には|にも|のは|のが|のを|とは|とも|から|まで|より|など|って|という|といった|"
    "[はがをにのともへでやかも])?[、。,.!！?？』」］】〕）)”“…・：:；;]*$"
)


def _explode_brackets(text: str) -> list[str]:
    """Split so opening brackets leave the previous word and closing
    brackets do not stay glued to the following word.
    ワンマンライブ「拝啓… → ワンマンライブ / 「拝啓…
    なっていた。』EDテーマ → なっていた。』 / EDテーマ
    Quoted atoms such as “本物”へ。 must stay intact.
    """
    if not text:
        return []
    if text in ATOMS or text in NOWRAP_ATOMS or DATE_RE.fullmatch(text):
        return [text]
    parts: list[str] = []
    buf: list[str] = []
    for ch in text:
        if ch in OPEN_CHARS and buf and buf[-1] not in OPEN_CHARS:
            parts.append("".join(buf))
            buf = [ch]
        elif (
            buf
            and buf[-1] in CLOSE_CHARS
            and ch not in START_FORBIDDEN
        ):
            parts.append("".join(buf))
            buf = [ch]
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _fix_kinsoku(chunks: list[str]) -> list[str]:
    """Hard rule: no chunk ends with an opening bracket, none starts with
    closing punctuation. Opening punct joins the following unit; closing
    punct joins the preceding unit."""
    exploded: list[str] = []
    for c in chunks:
        if c:
            exploded.extend(_explode_brackets(c))
    merged: list[str] = []
    for ph in exploded:
        if not ph:
            continue
        if merged and ph[0] in START_FORBIDDEN:
            merged[-1] += ph
            continue
        if merged and merged[-1][-1] in OPEN_CHARS:
            merged[-1] += ph
            continue
        merged.append(ph)
    # leftover opening-only punct attaches to the next chunk
    out: list[str] = []
    i = 0
    while i < len(merged):
        if i + 1 < len(merged) and all(ch in OPEN_CHARS for ch in merged[i]):
            out.append(merged[i] + merged[i + 1])
            i += 2
        else:
            out.append(merged[i])
            i += 1
    return out


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
            # Do not glue での/では onto a long Japanese proper noun
            # (that forced earlier wraps). Latin tails like HOKKAIDOでの
            # should still stay together.
            if (
                re.fullmatch(r"^(?:での|では)[、。]*$", ph)
                and len(merged[-1]) >= 6
                and HAS_JP.search(merged[-1])
            ):
                merged.append(ph)
                continue
            merged[-1] += ph
            continue
        if ph[0] in START_FORBIDDEN and not LEAD_PUNCT.fullmatch(ph):
            merged[-1] += ph[0]
            ph = ph[1:]
            if not ph:
                continue
        merged.append(ph)
    return _fix_kinsoku(merged)


def _should_nowrap(ph: str) -> bool:
    if not ph:
        return False
    raw = ph.strip()
    if raw in NOWRAP_ATOMS or ph in NOWRAP_ATOMS or any(
        s == a or (s.startswith(a) and len(s) - len(a) <= 4)
        for a in NOWRAP_ATOMS
        for s in (ph, raw)
    ):
        return True
    # Keep short quoted fragments intact so WebKit cannot break after
    # 「 or before 」. Long complete titles are split at phrases instead.
    if ph[0] in OPEN_CHARS or ph[-1] in CLOSE_CHARS:
        return len(raw) <= 12
    return False


# Split Latin/Japanese at a space, or after a 4+ letter Latin word
# (HOKKAIDO / 試合後, Asia / にも). Do not split short prefixes
# (TVアニメ, EDテーマ) or digits (モブせか2).
SCRIPT_BOUND = re.compile(
    r"(?<=[A-Za-z]{4})(?=\s*[一-龠ぁ-んァ-ヶ])"
    r"|(?<=[一-龠ぁ-んァ-ヶ])(?=\s*[A-Za-z]{4})"
)


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
            continue
        for sub in SCRIPT_BOUND.split(part):
            if sub == "":
                continue
            if sub in ATOMS or DATE_RE.fullmatch(sub):
                chunks.append(sub)
            else:
                chunks.extend(PARSER.parse(sub))
    return _merge_chunks(chunks)


def phrases_to_html(phrases: list[str]) -> str:
    phrases = _fix_kinsoku(phrases)
    if len(phrases) <= 1 and not (phrases and _should_nowrap(phrases[0])):
        return phrases[0] if phrases else ""
    out = []
    for i, ph in enumerate(phrases):
        if i:
            # Defensive: never insert a wrap opportunity that would leave
            # an opening bracket at EOL or a closing mark at SOL.
            if phrases[i - 1][-1] in OPEN_CHARS or ph[0] in START_FORBIDDEN:
                pass
            else:
                out.append("<wbr>")
        if _should_nowrap(ph):
            out.append(f'<span class="nowrap">{ph}</span>')
        else:
            out.append(ph)
    return "".join(out)


def update_css(html: str) -> str:
    # Natural Japanese wrap: fill each line to the edge. Kinsoku only
    # via line-break:strict; long English may wrap via break-word.
    html = html.replace("overflow-wrap:anywhere", "overflow-wrap:break-word")
    html = html.replace("text-wrap:pretty", "text-wrap:wrap")
    html = html.replace("text-wrap:balance", "text-wrap:wrap")
    html = html.replace("word-break:keep-all", "word-break:normal")
    html = html.replace(".catch{margin:16px 0 0;", ".catch{margin:16px 0 14px;")
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
    """Drop BudouX <wbr> and phrase nowrap. Keep deadline date nowrap."""
    html = html.replace("<wbr>", "").replace("<wbr/>", "").replace("<wbr />", "")
    return _unwrap_nowrap_outside_deadline(html)


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
    if "word-break:keep-all" in dst or "text-wrap:pretty" in dst or "text-wrap:balance" in dst:
        raise SystemExit("phrase-wrap typography still present")
    if "<wbr>" in dst or "<wbr/>" in dst:
        raise SystemExit("wbr still present")
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
    print("sanity ok; wbr", dst.count("<wbr>"), "keep-all", "word-break:keep-all" in dst)


if __name__ == "__main__":
    main()
