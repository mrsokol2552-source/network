import re
from pathlib import Path

SENTENCE_SPLIT = re.compile(r"\s*(.+?[.!?…])\s*(?:<!--\s*REVIEW:\s*(.*?)\s*-->)?\s*")

# Heuristics

def uppercase_first(s: str) -> str:
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.upper() + s[i+1:]
    return s


def split_long(s: str) -> str:
    # Split only on em dash (safe semantic pause)
    if ' — ' in s:
        a, b = s.split(' — ', 1)
        b = uppercase_first(b.strip())
        return f"{a.strip()}. {b}"
    return s

SYNONYMS = {
    'туман': ['мгла', 'пелена', 'дымка'],
    'свет': ['отсвет', 'сияние', 'блеск'],
    'серый': ['пепельный', 'свинцовый', 'стальной'],
    'рев': ['рокот', 'вой', 'гул'],
    'гул': ['рокот', 'гудение', 'грохот'],
    'вибрация': ['дрожь', 'тряска', 'дребезг'],
    'пустош': ['пепелище', 'безжизненные равнины'],
}


def suggest_repeats(words_line: str):
    # Extract after 'Повторы:' token
    m = re.search(r"Повторы:\s*(.*)$", words_line)
    if not m:
        return []
    raw = m.group(1)
    items = [x.strip().strip('.,;') for x in raw.split(',') if x.strip()]
    sug = []
    for w in items:
        base = w.lower()
        alts = SYNONYMS.get(base, [])
        if alts:
            sug.append(f"заменить одно повторение «{w}» на: {', '.join(alts)}")
        else:
            sug.append(f"сократить или конкретизировать одно повторение «{w}»")
    return sug


def suggest_cliche(line: str):
    if 'Возможные штампы' not in line:
        return []
    return [
        'конкретизировать образ (предмет, действие, источник)',
        'заменить общую метафору на деталь среды/действия',
    ]


def process_paragraph(line: str) -> str:
    if '<!--' not in line:
        return line
    out_sents = []
    pos = 0
    while pos < len(line):
        m = SENTENCE_SPLIT.match(line, pos)
        if not m:
            # append tail and break
            out_sents.append(line[pos:].strip())
            break
        sent, review = m.group(1), (m.group(2) or '')
        new_sent = sent
        notes = []
        if 'Перегруз:' in review:
            splitted = split_long(new_sent)
            if splitted != new_sent:
                new_sent = splitted
                notes.append('разбил длинное предложение')
        if 'Повторы:' in review:
            notes.extend(suggest_repeats(review))
        if 'Возможные штампы:' in review:
            notes.extend(suggest_cliche(review))
        if notes:
            out_sents.append(new_sent + f" <!-- REWRITE: {'; '.join(notes)} -->")
        else:
            out_sents.append(new_sent)
        pos = m.end()
    # Rejoin, keeping single space between sentences
    text = ' '.join([s for s in out_sents if s])
    return text


def main():
    src = Path('Book/ALL_annotated.md')
    dst = Path('Book/ALL_edited.md')
    if not src.exists():
        raise SystemExit('Not found: ' + str(src))
    lines = src.read_text(encoding='utf-8').splitlines()
    out_lines = []
    for line in lines:
        if not line.strip():
            out_lines.append('')
            continue
        if line.lstrip().startswith('#') or line.lstrip().startswith('- '):
            out_lines.append(line)
            continue
        out_lines.append(process_paragraph(line))
    dst.write_text('\n'.join(out_lines) + '\n', encoding='utf-8')
    print('Wrote:', dst)

if __name__ == '__main__':
    main()
