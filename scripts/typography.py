import re
from pathlib import Path

WHITESPACE = re.compile(r"\s+")
ELLIPSIS = re.compile(r"\.\.\.")
# Em dash normalization only for literal spaces (avoid crossing newlines)
# Em dash only when surrounded by non-space characters (avoid list markers)
NDASH = re.compile(r"(?<=\S) [-–—]{1,2} (?=\S)")
SPACE_BEFORE_PUNCT = re.compile(r"\s+([,;:!?])")
DOUBLE_QUOTES_SEGMENTS = re.compile(r'"([^"]+)"')
PERCENT = re.compile(r"(\d)\s+%")


def typograph(text: str) -> str:
    # Normalize whitespace
    text = text.replace('\r\n', '\n')
    # Ellipsis
    text = ELLIPSIS.sub('…', text)
    # Normalize dashes between words/spaces to em dash with spaces
    text = NDASH.sub(' — ', text)
    # Remove spaces before punctuation
    text = SPACE_BEFORE_PUNCT.sub(r"\1", text)
    # Replace straight quotes with Russian «» (naive, per segment)
    def _q(m):
        inner = m.group(1)
        return f'«{inner}»'
    text = DOUBLE_QUOTES_SEGMENTS.sub(_q, text)
    # Narrow no-break space before %
    text = PERCENT.sub(r"\1 %", text)
    return text


def main():
    src = Path('Book/ALL.md')
    dst = Path('Book/ALL_typo.md')
    if not src.exists():
        raise SystemExit('Not found: ' + str(src))
    data = src.read_text(encoding='utf-8')
    out = typograph(data)
    dst.write_text(out, encoding='utf-8')
    print('Wrote:', dst)

if __name__ == '__main__':
    main()
