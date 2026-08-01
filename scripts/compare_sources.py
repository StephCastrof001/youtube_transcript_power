#!/usr/bin/env python3
"""Comparar dos transcripciones del mismo video y escribir un análisis en Markdown.

Responde una sola pregunta: ¿el escalón caro se justifica?

    python compare_sources.py A.json B.json -o ANALISIS.md

Cuatro mediciones:
  1. Volumen — cuánto texto produjo cada uno
  2. Términos técnicos — el test que decide
  3. Divergencia de vocabulario — qué oyó uno que el otro no
  4. Muletillas — cuánto ruido trae cada fuente

El análisis va a un archivo aparte, nunca sobre las transcripciones.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

# Términos que un reconocedor genérico suele romper y uno con contexto técnico no.
# Cada entrada: (término canónico, [variantes que cuentan como acierto])
TECH_TERMS = [
    ("worktree", ["worktree", "work tree", "git worktree"]),
    ("Google Form", ["google form", "google forms"]),
    ("vibe coding", ["vibe coding", "vibe code", "vibecoding", "vibe codear"]),
    ("subagente", ["subagente", "subagentes", "sub agente", "subagent"]),
    ("MCP", ["mcp"]),
    ("Claude Code", ["claude code"]),
    ("prompt", ["prompt", "prompts"]),
    ("commit", ["commit", "commits", "commitear"]),
    ("repo", ["repo", "repositorio"]),
    ("endpoint", ["endpoint", "endpoints"]),
    ("deploy", ["deploy", "deployar"]),
    ("token", ["token", "tokens"]),
    ("persona sintética", ["persona sintetica", "personas sinteticas"]),
    ("backlog", ["backlog"]),
    ("framework", ["framework", "frameworks"]),
    ("markdown", ["markdown"]),
    ("API", ["api"]),
    ("brief", ["brief", "briefing"]),
]

FILLERS = ["eh", "este", "okay", "ok", "digamos", "o sea", "basicamente", "nada"]


def norm(text: str) -> str:
    """Minúsculas sin tildes — un acento no debe contar como error de término."""
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text)


def load(path: Path) -> tuple[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    text = " ".join(s["text"].replace("\n", " ") for s in data["segments"])
    return text, data


def count_term(haystack: str, variants: list[str]) -> int:
    return sum(len(re.findall(rf"\b{re.escape(v)}\b", haystack)) for v in variants)


def build_report(path_a: Path, path_b: Path) -> tuple[str, int, int]:
    raw_a, data_a = load(path_a)
    raw_b, data_b = load(path_b)
    a, b = norm(raw_a), norm(raw_b)

    label_a = data_a.get("source", path_a.stem)
    label_b = data_b.get("source", path_b.stem)
    words_a, words_b = a.split(), b.split()

    out: list[str] = []
    w = out.append

    w("# Análisis — Método 1 vs Método 2")
    w("")
    w(f"Generado: {datetime.now():%Y-%m-%d %H:%M}")
    w("")
    w("| | Método A | Método B |")
    w("|---|---|---|")
    w(f"| Fuente | `{label_a}` | `{label_b}` |")
    w(f"| Archivo | `{path_a}` | `{path_b}` |")
    w(f"| Idioma | {data_a.get('language', '?')} | {data_b.get('language', '?')} |")
    w("")
    w("---")
    w("")

    # --- 1. Volumen ---
    w("## 1. Volumen")
    w("")
    w("| Métrica | A | B | Δ |")
    w("|---|---:|---:|---:|")
    for name, va, vb in [
        ("Segmentos", len(data_a["segments"]), len(data_b["segments"])),
        ("Palabras", len(words_a), len(words_b)),
        ("Vocabulario único", len(set(words_a)), len(set(words_b))),
        ("Caracteres", len(a), len(b)),
    ]:
        delta = f"{(vb - va) / va * 100:+.1f}%" if va else "n/a"
        w(f"| {name} | {va:,} | {vb:,} | {delta} |")
    w("")

    # --- 2. Términos técnicos ---
    w("## 2. Términos técnicos — el test que decide")
    w("")
    w("| Término | A | B | Veredicto |")
    w("|---|---:|---:|---|")

    recovered, lost, tied = [], [], []
    for canonical, variants in TECH_TERMS:
        ca, cb = count_term(a, variants), count_term(b, variants)
        if cb > 0 and ca == 0:
            verdict, bucket = "**B lo recupera**", recovered
        elif ca > 0 and cb == 0:
            verdict, bucket = "B lo pierde", lost
        elif ca == cb == 0:
            verdict, bucket = "ausente en ambos", None
        else:
            verdict, bucket = "empate", tied
        if bucket is not None:
            bucket.append(canonical)
        w(f"| {canonical} | {ca} | {cb} | {verdict} |")
    w("")

    # --- 3. Divergencia ---
    set_a, set_b = set(words_a), set(words_b)
    only_b = Counter(x for x in words_b if x not in set_a and len(x) > 4)
    only_a = Counter(x for x in words_a if x not in set_b and len(x) > 4)
    overlap = len(set_a & set_b) / len(set_a | set_b) * 100 if (set_a | set_b) else 0

    w("## 3. Divergencia de vocabulario")
    w("")
    w(f"**Solapamiento (Jaccard): {overlap:.1f}%**")
    w("")
    w("| Solo en B (B lo oyó, A no) | n | Solo en A (A lo oyó, B no) | n |")
    w("|---|---:|---|---:|")
    top_b, top_a = only_b.most_common(20), only_a.most_common(20)
    for i in range(max(len(top_b), len(top_a))):
        wb, nb = top_b[i] if i < len(top_b) else ("", "")
        wa, na = top_a[i] if i < len(top_a) else ("", "")
        w(f"| {wb} | {nb} | {wa} | {na} |")
    w("")

    # --- 4. Muletillas ---
    w("## 4. Densidad de muletillas (por 1000 palabras)")
    w("")
    w("| Muletilla | A | B |")
    w("|---|---:|---:|")
    for filler in FILLERS:
        da = count_term(a, [filler]) / len(words_a) * 1000 if words_a else 0
        db = count_term(b, [filler]) / len(words_b) * 1000 if words_b else 0
        w(f"| {filler} | {da:.1f} | {db:.1f} |")
    w("")

    # --- Veredicto ---
    w("---")
    w("")
    w("## Veredicto")
    w("")
    w(f"- Términos que **B recupera** y A rompe: **{len(recovered)}**")
    if recovered:
        w(f"  - {', '.join(recovered)}")
    w(f"- Términos que **B pierde** y A tiene: **{len(lost)}**")
    if lost:
        w(f"  - {', '.join(lost)}")
    w("")
    if len(recovered) >= 5:
        w("> **Diferencia SIGNIFICATIVA.** El Método 2 se justifica para cualquier uso")
        w("> que cite textual o liste herramientas. El costo en tiempo se paga solo.")
    elif len(recovered) >= 3:
        w("> **Diferencia MODERADA.** El Método 2 se justifica solo si vas a citar")
        w("> textual. Para entender el contenido, el Método 1 alcanza.")
    else:
        w("> **Diferencia MENOR.** El Método 1 alcanza. El Método 2 es lujo para")
        w("> este tipo de contenido — el costo en tiempo no se paga.")
    w("")
    w("### Criterio usado")
    w("")
    w("Definido **antes** de correr el experimento, no después de ver los números:")
    w("")
    w("| Términos recuperados | Lectura |")
    w("|---|---|")
    w("| ≥ 5 | significativa — el Paso 2 se justifica |")
    w("| 3-4 | moderada — solo si citás textual |")
    w("| < 3 | menor — el ASR alcanza |")
    w("")

    return "\n".join(out), len(recovered), len(lost)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_a", type=Path, help="JSON del método A (ej. captions)")
    parser.add_argument("json_b", type=Path, help="JSON del método B (ej. whisper)")
    parser.add_argument(
        "-o", "--out", type=Path, default=Path("ANALISIS_metodo1_vs_metodo2.md")
    )
    args = parser.parse_args()

    for path in (args.json_a, args.json_b):
        if not path.exists():
            print(f"✗ no existe: {path}")
            return 1

    report, recovered, lost = build_report(args.json_a, args.json_b)
    args.out.write_text(report, encoding="utf-8")

    print(f"✓ análisis escrito -> {args.out}")
    print(f"  términos recuperados por B: {recovered}")
    print(f"  términos perdidos por B   : {lost}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
