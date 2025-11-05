import re
from pathlib import Path

COMMENT_RE = re.compile(r"<!--.*?-->")
EMDASH_SPACES = re.compile(r"(?<=\S) [-–—]{1,2} (?=\S)")
ELLIPSIS = re.compile(r"\.\.\.")

REPLACEMENTS = [
    # (pattern, replacement, flags)
    (r"серые\s+пустош[ьи]", "пепельные пустоши", re.IGNORECASE),
    (r"р[её]в\s+двигател[а-яё]*", "рокот двигателей", re.IGNORECASE),
    (r"монотонн[а-яё]*\s+гул", "ровный гул", re.IGNORECASE),
    (r"тяжелых\s+снарядов", "тяжёлых снарядов", 0),
]

DISPLAY_RE = re.compile(r"(панорамн[а-яё]*\s+)диспле(й|я|ю|е|ем|ям|ями|ях|ев|и|ь|у|а|ом|ами)?", re.IGNORECASE)

DISPLAY_ENDINGS = {
    None: "",
    "й": "",
    "ь": "",
    "я": "а",
    "ю": "у",
    "е": "е",
    "ем": "ом",
    "у": "у",
    "ом": "ом",
    "и": "ы",
    "ев": "ов",
    "ям": "ам",
    "ями": "ами",
    "ях": "ах",
    "ами": "ами",
}

def replace_display_forms(text: str) -> str:
    def _rep(m):
        pre = m.group(1)
        end = m.group(2)
        new_end = DISPLAY_ENDINGS.get(end, "")
        return f"{pre}экра{ 'н' + new_end }"
    return DISPLAY_RE.sub(_rep, text)


def polish_line(line: str) -> str:
    # Remove inline comments
    line = COMMENT_RE.sub("", line)
    # Typography
    line = ELLIPSIS.sub("…", line)
    line = EMDASH_SPACES.sub(" — ", line)
    # Lexical tweaks
    for pat, rep, flags in REPLACEMENTS:
        line = re.sub(pat, rep, line, flags=flags)
    line = replace_display_forms(line)
    # Compact spaces
    line = re.sub(r"\s+", " ", line).strip()
    return line


def extract_prologue(lines):
    start = None
    end = None
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith('#') and 'Пролог' in ln:
            start = i
            break
    if start is None:
        return []
    for j in range(start + 1, len(lines)):
        if lines[j].lstrip().startswith('#') and 'Пролог' not in lines[j]:
            end = j
            break
    if end is None:
        end = len(lines)
    return lines[start:end]


def main():
    src = Path('Book/ALL_edited.md')
    dst = Path('Book/ALL_polished.md')
    if not src.exists():
        raise SystemExit('Not found: ' + str(src))
    lines = src.read_text(encoding='utf-8').splitlines()
    prologue = extract_prologue(lines)
    if not prologue:
        raise SystemExit('Пролог не найден в ' + str(src))

    out_lines = []
    for i, ln in enumerate(prologue):
        if ln.strip() == '':
            out_lines.append('')
            continue
        if ln.lstrip().startswith('#'):
            # Keep heading as is
            out_lines.append(ln)
            out_lines.append('')
            continue
        out_lines.append(polish_line(ln))
        out_lines.append('')

    # Trim trailing blanks
    while out_lines and out_lines[-1] == '':
        out_lines.pop()
    dst.write_text('\n'.join(out_lines) + '\n', encoding='utf-8')
    print('Wrote:', dst)


if __name__ == '__main__':
    main()
