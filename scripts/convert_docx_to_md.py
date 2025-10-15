import argparse
import os
from pathlib import Path

import mammoth  # type: ignore
from markdownify import markdownify as md  # type: ignore


def convert_docx_to_markdown(input_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    images_dir = output_path.parent / f"{output_path.stem}_assets"
    images_dir.mkdir(parents=True, exist_ok=True)

    def convert_image(image):  # mammoth image handler
        image_bytes = image.open().read()
        ext = image.content_type.split("/")[-1]
        idx = len(list(images_dir.glob("*"))) + 1
        img_name = f"image_{idx}.{ext}"
        img_path = images_dir / img_name
        with open(img_path, "wb") as f:
            f.write(image_bytes)
        return {"src": str(os.path.relpath(img_path, output_path.parent))}

    with open(input_path, "rb") as f:
        result = mammoth.convert_to_html(f, convert_image=mammoth.images.inline(convert_image))
    html = result.value  # type: ignore

    markdown = md(html, heading_style="ATX")

    # Ensure top-level header exists
    first_non_empty = next((line for line in markdown.splitlines() if line.strip()), "")
    if not first_non_empty.startswith("# "):
        title = input_path.stem
        markdown = f"# {title}\n\n" + markdown

    output_path.write_text(markdown, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Convert .docx to Markdown with images extracted")
    parser.add_argument("input", type=Path, help="Path to .docx file")
    parser.add_argument("output", type=Path, help="Path to output .md file")
    args = parser.parse_args()

    convert_docx_to_markdown(args.input, args.output)


if __name__ == "__main__":
    main()

