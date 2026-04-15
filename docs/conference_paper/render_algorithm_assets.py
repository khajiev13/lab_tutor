#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / "conference_paper_algorithm_drafts.md"
DEFAULT_OUTPUT_DIR = ROOT / "generated" / "algorithms"
COMMON_BIN_DIRS = (
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/Library/TeX/texbin"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render the LaTeX algorithm blocks from the conference-paper draft "
            "into tight publication-quality assets for Word insertion."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Markdown file containing fenced LaTeX algorithm blocks.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated .tex, .log, .pdf, .png, and .svg files.",
    )
    parser.add_argument(
        "--algorithms",
        type=int,
        nargs="+",
        default=[1, 2],
        help="1-based algorithm block indices to render.",
    )
    parser.add_argument(
        "--width-in",
        type=float,
        default=8.25,
        help="Minipage width, in inches, used for the tight algorithm box.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=600,
        help="Raster DPI for PNG export.",
    )
    parser.add_argument(
        "--engine",
        choices=["xelatex", "pdflatex", "auto"],
        default="auto",
        help="LaTeX engine. 'auto' prefers xelatex, then falls back to pdflatex.",
    )
    return parser.parse_args()


def require_command(name: str) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    for directory in COMMON_BIN_DIRS:
        candidate = directory / name
        if candidate.exists():
            return str(candidate)
    raise SystemExit(f"Required command not found: {name}")


def choose_engine(preference: str) -> str:
    if preference != "auto":
        return require_command(preference)

    for candidate in ("xelatex", "pdflatex"):
        try:
            return require_command(candidate)
        except SystemExit:
            continue
    raise SystemExit("Neither xelatex nor pdflatex is available.")


def extract_algorithm_blocks(markdown: str) -> list[str]:
    return re.findall(r"```latex\n(.*?)```", markdown, flags=re.S)


def normalize_block(block: str) -> str:
    normalized = block.strip()
    normalized = normalized.replace(r"\begin{algorithm}[t]", "")
    normalized = normalized.replace(r"\end{algorithm}", "")
    normalized = re.sub(r"^\s*\\label\{[^}]+\}\s*$", "", normalized, flags=re.M)
    normalized = re.sub(
        r"\\caption\{",
        r"\\captionof{algorithm}{",
        normalized,
        count=1,
    )
    normalized = re.sub(
        r"\s*\\Comment\{([^{}]*)\}",
        lambda m: (
            "\n"
            "\\Statex \\hspace*{2.0em}"
            "\\parbox[t]{0.90\\linewidth}{\\raggedright\\scriptsize\\itshape "
            + m.group(1).strip()
            + "}"
        ),
        normalized,
    )
    return normalized.strip()


def build_tex(block: str, width_in: float, engine: str, algorithm_number: int) -> str:
    font_bits = (
        "\\usepackage{fontspec}\n"
        "\\setmainfont{Times New Roman}\n"
        "\\setmonofont{Menlo}\n"
        if engine == "xelatex"
        else "\\usepackage[T1]{fontenc}\n"
    )
    return (
        "\\documentclass[11pt]{article}\n"
        "\\usepackage{amsmath,amssymb}\n"
        "\\usepackage{algpseudocode}\n"
        "\\usepackage{caption}\n"
        f"{font_bits}"
        "\\DeclareCaptionType{algorithm}[Algorithm][List of Algorithms]\n"
        "\\captionsetup[algorithm]{font=small,labelfont=bf,textfont=bf}\n"
        "\\newsavebox{\\algbox}\n"
        "\\begin{document}\n"
        "\\thispagestyle{empty}\n"
        f"\\setcounter{{algorithm}}{{{algorithm_number - 1}}}\n"
        "\\small\n"
        "\\begin{lrbox}{\\algbox}\n"
        f"\\begin{{minipage}}{{{width_in:.2f}in}}\n"
        f"{block}\n"
        "\\end{minipage}\n"
        "\\end{lrbox}\n"
        "\\pdfpagewidth=\\wd\\algbox\n"
        "\\pdfpageheight=\\dimexpr\\ht\\algbox+\\dp\\algbox\\relax\n"
        "\\shipout\\vbox{\\offinterlineskip\\box\\algbox}\n"
        "\\end{document}\n"
    )


def run_checked(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode == 0:
        return
    raise RuntimeError(
        "Command failed:\n"
        + " ".join(cmd)
        + "\n\nSTDOUT:\n"
        + result.stdout
        + "\n\nSTDERR:\n"
        + result.stderr
    )


def render_one(
    block: str,
    output_dir: Path,
    stem: str,
    width_in: float,
    dpi: int,
    engine: str,
    algorithm_number: int,
) -> None:
    tex_source = build_tex(
        normalize_block(block),
        width_in=width_in,
        engine=engine,
        algorithm_number=algorithm_number,
    )

    with tempfile.TemporaryDirectory(prefix="alg-render-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        tex_path = tmp_dir / f"{stem}.tex"
        tex_path.write_text(tex_source)

        run_checked(
            [engine, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=tmp_dir,
        )
        pdf_path = tmp_dir / f"{stem}.pdf"
        log_path = tmp_dir / f"{stem}.log"

        shutil.copy2(tex_path, output_dir / tex_path.name)
        shutil.copy2(log_path, output_dir / log_path.name)
        shutil.copy2(pdf_path, output_dir / pdf_path.name)

        run_checked(
            [require_command("pdftocairo"), "-png", "-r", str(dpi), "-singlefile", str(pdf_path), str(output_dir / stem)],
            cwd=tmp_dir,
        )
        run_checked(
            [require_command("pdftocairo"), "-svg", str(pdf_path), str(output_dir / f"{stem}.svg")],
            cwd=tmp_dir,
        )


def main() -> None:
    args = parse_args()
    require_command("pdftocairo")
    engine = choose_engine(args.engine)

    markdown = args.source.read_text()
    blocks = extract_algorithm_blocks(markdown)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    for index in args.algorithms:
        if index < 1 or index > len(blocks):
            raise SystemExit(f"Algorithm index {index} is out of range. Found {len(blocks)} blocks.")
        stem = f"algorithm_{index}"
        render_one(
            blocks[index - 1],
            output_dir=output_dir,
            stem=stem,
            width_in=args.width_in,
            dpi=args.dpi,
            engine=engine,
            algorithm_number=index,
        )
        print(f"Rendered {stem} with {engine} into {output_dir}")


if __name__ == "__main__":
    main()
