#!/bin/sh
# Compile every figure in docs/tikz to an SVG in docs/source/_static/schematics.
# Requires pdflatex (TeX Live) and pdftocairo (poppler). Text is converted to paths, so the
# SVGs render identically everywhere (glyphs become vector paths). Run from anywhere:  sh docs/tikz/build.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$HERE/../source/_static/schematics"
TMP=$(mktemp -d)
mkdir -p "$OUT"
for tex in "$HERE"/fig_*.tex; do
    name=$(basename "$tex" .tex); name=${name#fig_}
    ( cd "$TMP" && TEXINPUTS="$HERE:" pdflatex -interaction=nonstopmode "$tex" > "$name.log" 2>&1 \
        || { echo "FAILED: $name (see $TMP/$name.log)"; exit 1; } )
    pdftocairo -svg "$TMP/$(basename "$tex" .tex).pdf" "$OUT/$name.svg"
    echo "built $name.svg"
done
