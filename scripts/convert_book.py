import re, zipfile, sys, html
from xml.etree import ElementTree as ET
from pathlib import Path

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
}

STOPWORDS = set("и в во на с со к ко от по о об обо за для чтобы что как но а же лишь только это еще уже был была были было быть есть нет да не ни же бы то ли либо либо же где когда тогда потом его ее их ему ей нам вам нами вами них у из при между над под перед после без про через во время тоже также уж лишь ведь словно будто разве лишь ли уж едва почти совсем вовсе крайне очень более менее снова опять также таки даже только лишь именно как будто словно вроде типа якобы будто бы".split())

CLICHE_PATTERNS = [
    re.compile(pat, re.I) for pat in [
        r"серые?\s+пустош",
        r"панорамн\w*\s+диспле",
        r"тускл\w*\s+свет",
        r"туман",
        r"вибраци",
        r"рёв\s+двигател|рев\s+двигател",
        r"тяжел\w*\s+снаряд",
        r"разрыв(ов|ы)\s+снаряд",
        r"мир\s+горел",
    ]
]

SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")
WHITESPACE = re.compile(r"\s+")


def read_docx_paragraphs(docx_path: Path):
    with zipfile.ZipFile(docx_path, 'r') as z:
        xml_bytes = z.read('word/document.xml')
    root = ET.fromstring(xml_bytes)
    paras = []
    for p in root.findall('.//w:p', NS):
        texts = []
        for t in p.findall('.//w:t', NS):
            texts.append(t.text or '')
        text = ''.join(texts)
        text = WHITESPACE.sub(' ', text).strip()
        if text:
            paras.append(text)
    return paras


def is_heading(text: str) -> bool:
    t = text.strip()
    return bool(re.match(r"^(Пролог|Эпилог|Часть\s+\d+|Глава\s+\d+)(\.|:)?$", t, re.I))


def heading_level(text: str) -> int:
    # Keep a simple scheme: top-level for Пролог/Эпилог/Часть, second-level for Глава
    t = text.strip()
    if re.match(r"^(Пролог|Эпилог|Часть\s+\d+)(?:\.|:)?$", t, re.I):
        return 1
    if re.match(r"^Глава\s+\d+(?:\.|:)?$", t, re.I):
        return 2
    return 2


def slugify(text: str) -> str:
    # Simple slug, keep Cyrillic for Markdown anchors (GitHub handles it)
    s = text.strip().lower()
    s = s.replace('.', '').replace(':', '')
    s = WHITESPACE.sub('-', s)
    return s


def analyze_sentence(sent: str):
    s = sent.strip()
    if not s:
        return []
    issues = []
    comma_count = s.count(',')
    if len(s) >= 200 or comma_count >= 3:
        issues.append(f"Перегруз: длина {len(s)} символов, запятых {comma_count}")
    # repetitions (excluding stopwords)
    tokens = [t for t in re.findall(r"[А-Яа-яA-Za-zЁё0-9-]+", s) if t]
    norm = [t.lower() for t in tokens]
    freq = {}
    for t in norm:
        if t in STOPWORDS:
            continue
        freq[t] = freq.get(t, 0) + 1
    reps = [w for w, c in freq.items() if c >= 3]
    if reps:
        issues.append("Повторы: " + ', '.join(sorted(reps)))
    # cliche patterns
    found_cliche = []
    for pat in CLICHE_PATTERNS:
        m = pat.search(s)
        if m:
            found_cliche.append(m.group(0))
    if found_cliche:
        issues.append("Возможные штампы: " + ', '.join(sorted(set(found_cliche))))
    return issues


def build_markdown(paragraphs):
    # Identify headings
    blocks = []
    headings = []
    for p in paragraphs:
        if is_heading(p):
            lvl = heading_level(p)
            title = re.sub(r"[.:]+$", '', p).strip()
            slug = slugify(title)
            blocks.append(('heading', lvl, title, slug))
            headings.append((lvl, title, slug))
        else:
            blocks.append(('para', p))

    # If no headings detected but first para looks like "Пролог.", promote it
    if not any(b[0] == 'heading' for b in blocks) and paragraphs:
        first = paragraphs[0]
        if re.match(r"^Пролог\.?$", first.strip(), re.I):
            title = re.sub(r"[.:]+$", '', first).strip()
            slug = slugify(title)
            blocks = [('heading', 1, title, slug)] + [('para', p) for p in paragraphs[1:]]
            headings = [(1, title, slug)]

    md_lines = []
    # TOC
    if headings:
        md_lines.append("## Оглавление")
        for lvl, title, slug in headings:
            indent = '  ' * (max(0, lvl - 1))
            md_lines.append(f"{indent}- [{title}](#{slug})")
        md_lines.append("")

    for b in blocks:
        if b[0] == 'heading':
            _, lvl, title, _ = b
            hashes = '#' * max(1, min(6, lvl))
            md_lines.append(f"{hashes} {title}")
            md_lines.append("")
        else:
            _, text = b
            md_lines.append(text)
            md_lines.append("")
    return '\n'.join(md_lines).rstrip() + '\n'


def build_markdown_annotated(paragraphs):
    # Reuse heading detection
    blocks = []
    headings = []
    for p in paragraphs:
        if is_heading(p):
            lvl = heading_level(p)
            title = re.sub(r"[.:]+$", '', p).strip()
            slug = slugify(title)
            blocks.append(('heading', lvl, title, slug))
            headings.append((lvl, title, slug))
        else:
            blocks.append(('para', p))

    if not any(b[0] == 'heading' for b in blocks) and paragraphs:
        first = paragraphs[0]
        if re.match(r"^Пролог\.?$", first.strip(), re.I):
            title = re.sub(r"[.:]+$", '', first).strip()
            slug = slugify(title)
            blocks = [('heading', 1, title, slug)] + [('para', p) for p in paragraphs[1:]]
            headings = [(1, title, slug)]

    md_lines = []
    if headings:
        md_lines.append("## Оглавление")
        for lvl, title, slug in headings:
            indent = '  ' * (max(0, lvl - 1))
            md_lines.append(f"{indent}- [{title}](#{slug})")
        md_lines.append("")

    for b in blocks:
        if b[0] == 'heading':
            _, lvl, title, _ = b
            hashes = '#' * max(1, min(6, lvl))
            md_lines.append(f"{hashes} {title}")
            md_lines.append("")
        else:
            _, text = b
            sents = SENTENCE_SPLIT.split(text)
            annotated_parts = []
            for s in sents:
                issues = analyze_sentence(s)
                if issues:
                    comment = "; ".join(issues)
                    annotated_parts.append(f"{s} <!-- REVIEW: {comment} -->")
                else:
                    annotated_parts.append(s)
            md_lines.append(' '.join(annotated_parts))
            md_lines.append("")
    return '\n'.join(md_lines).rstrip() + '\n'


def main():
    in_path = Path('Book/ALL.docx')
    if not in_path.exists():
        print('Input not found:', in_path, file=sys.stderr)
        sys.exit(1)
    paras = read_docx_paragraphs(in_path)
    out_clean = Path('Book/ALL.md')
    out_ann = Path('Book/ALL_annotated.md')
    out_clean.write_text(build_markdown(paras), encoding='utf-8')
    out_ann.write_text(build_markdown_annotated(paras), encoding='utf-8')
    print('Wrote:', out_clean)
    print('Wrote:', out_ann)

if __name__ == '__main__':
    main()
