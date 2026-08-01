#!/usr/bin/env python3
"""YouTube -> transcripción, por cascada de costo creciente.

Implementa el árbol de METODOLOGIA.md:

    Paso 1  captions de YouTube      ~30 seg,  0 instalación
    Paso 2a Whisper local en GPU     ~8 min/75min de audio
    Paso 2b Whisper local en CPU     ~55 min/75min de audio, misma calidad

No baja un escalón hasta que el anterior falla de verdad. El Paso 2 nunca se
activa solo: hay que pedirlo con --whisper, o dejar que --auto lo dispare cuando
no existan captions.

Uso:
    python yt_transcript.py "URL"                    # solo captions
    python yt_transcript.py "URL" --auto             # captions, y whisper si no hay
    python yt_transcript.py "URL" --whisper          # forzar whisper
    python yt_transcript.py "URL" --no-auto          # ignorar captions ASR
    python yt_transcript.py --doctor                 # verificar entorno
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Idiomas a buscar, en orden de preferencia.
DEFAULT_LANGS = ["es", "es-419", "es-ES", "en"]

# Whisper se queda sin VRAM en la GTX 1650 (4 GB) con modelos grandes.
GPU_SAFE_MODELS = {"tiny", "base", "small", "medium"}

# Estrategias de cliente de yt-dlp, en orden. YouTube rota qué cliente bloquea,
# así que un solo intento no alcanza.
#
# `android_sdkless` es el culpable habitual del 403 desde enero 2026: la
# extracción funciona, devuelve URLs de media, y esas URLs responden 403 al
# descargar. Por eso el primer intento lo excluye explícitamente.
# Ref: https://github.com/yt-dlp/yt-dlp/issues/15723
YTDLP_CLIENT_STRATEGIES = [
    ("default sin android_sdkless", "youtube:player_client=default,-android_sdkless"),
    ("web_safari", "youtube:player_client=default,web_safari"),
    ("ios", "youtube:player_client=default,ios,-android_sdkless"),
    ("default (sin args)", None),
]


# --------------------------------------------------------------------------
# Modelo de datos
# --------------------------------------------------------------------------


@dataclass
class Segment:
    start: float
    duration: float
    text: str

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class Transcript:
    video_id: str
    segments: list[Segment]
    source: str  # "captions:manual" | "captions:asr" | "whisper:cuda" | "whisper:cpu"
    language: str
    title: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return " ".join(s.text.replace("\n", " ").strip() for s in self.segments)

    @property
    def duration(self) -> float:
        return self.segments[-1].end if self.segments else 0.0

    @property
    def is_low_fidelity(self) -> bool:
        """Los captions ASR rompen vocabulario técnico. Whisper no."""
        return self.source == "captions:asr"


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------


def extract_video_id(url_or_id: str) -> str:
    """Acepta URL completa, youtu.be, shorts, o el ID pelado."""
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url_or_id):
        return url_or_id
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/|/live/)([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        match = re.search(pat, url_or_id)
        if match:
            return match.group(1)
    raise ValueError(f"No pude extraer un video ID de: {url_or_id!r}")


def log(msg: str) -> None:
    print(msg, flush=True)


def fmt_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace(".", ",")


def fmt_stamp(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


# --------------------------------------------------------------------------
# PASO 1 — captions de YouTube
# --------------------------------------------------------------------------


def fetch_captions(video_id: str, langs: list[str], allow_asr: bool = True) -> Transcript | None:
    """Baja captions. Prefiere pista manual sobre ASR.

    Devuelve None si no hay nada usable — el caller decide si baja al Paso 2.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        log("  ✗ falta youtube-transcript-api  ->  pip install youtube-transcript-api")
        return None

    api = YouTubeTranscriptApi()

    try:
        listing = api.list(video_id)
    except Exception as exc:
        log(f"  ✗ no hay captions: {type(exc).__name__}: {exc}")
        return None

    available = list(listing)
    if not available:
        log("  ✗ el video no declara ninguna pista")
        return None

    log("  pistas disponibles:")
    for track in available:
        kind = "ASR/auto" if track.is_generated else "MANUAL"
        log(f"    {track.language_code:8} | {kind:8} | {track.language}")

    # Manual primero: es lo único que respeta términos técnicos y puntuación.
    warnings: list[str] = []
    try:
        track = listing.find_manually_created_transcript(langs)
        source = "captions:manual"
        log(f"  ✓ pista MANUAL en '{track.language_code}'")
    except Exception:
        if not allow_asr:
            log("  ✗ no hay pista manual y --no-auto descarta las ASR")
            return None
        try:
            track = listing.find_generated_transcript(langs)
        except Exception as exc:
            log(f"  ✗ ninguna pista en {langs}: {type(exc).__name__}")
            return None
        source = "captions:asr"
        warnings.append(
            "Caption auto-generado (ASR): los términos técnicos y nombres propios "
            "salen rotos. Para citar textual, usá --whisper."
        )
        log(f"  ⚠ solo ASR en '{track.language_code}' — calidad media")

    fetched = track.fetch()
    segments = [Segment(s.start, s.duration, s.text) for s in fetched]

    return Transcript(
        video_id=video_id,
        segments=segments,
        source=source,
        language=fetched.language_code,
        warnings=warnings,
    )


# --------------------------------------------------------------------------
# PASO 2 — Whisper local
# --------------------------------------------------------------------------


def _setup_cuda_dlls() -> bool:
    """Pone los DLL de cuBLAS/cuDNN donde el loader de Windows los encuentre.

    Esto DEBE correr antes de importar faster_whisper. Los paquetes `nvidia.*`
    son namespace packages: su `__file__` es None, así que hay que resolver el
    directorio vía `__path__`. Si importás faster_whisper primero, el loader ya
    buscó, ya falló, y no hay vuelta atrás en el mismo proceso.
    """
    if sys.platform != "win32":
        return True

    found_any = False
    for mod_name in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            mod = __import__(mod_name, fromlist=["__path__"])
            bin_path = os.path.join(list(mod.__path__)[0], "bin")
        except Exception:
            continue
        if not os.path.isdir(bin_path):
            continue
        os.add_dll_directory(bin_path)
        os.environ["PATH"] = bin_path + os.pathsep + os.environ.get("PATH", "")
        found_any = True

    return found_any


def download_audio(video_id: str, workdir: Path) -> Path:
    """Baja el audio con yt-dlp y lo normaliza a WAV 16 kHz mono para Whisper."""
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "El Paso 2 necesita yt-dlp y no está instalado.\n"
            "  Instalalo con:  pip install yt-dlp\n"
            "  (~3 MB. Solo hace falta para videos sin captions o cuando "
            "necesitás fidelidad técnica.)"
        )

    workdir.mkdir(parents=True, exist_ok=True)
    wav_path = workdir / f"{video_id}.wav"
    if wav_path.exists():
        log(f"  ✓ audio ya descargado: {wav_path.name}")
        return wav_path

    if not shutil.which("ffmpeg"):
        raise RuntimeError("Falta ffmpeg en el PATH. Instalalo: winget install Gyan.FFmpeg")

    log("  descargando audio con yt-dlp...")

    errors: list[str] = []
    for label, extractor_args in YTDLP_CLIENT_STRATEGIES:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-f", "bestaudio/best",
            "--extract-audio",
            "--audio-format", "wav",
            "--postprocessor-args", "-ar 16000 -ac 1",
            "-o", str(workdir / f"{video_id}.%(ext)s"),
            "--no-playlist",
            "--quiet", "--no-warnings", "--progress",
        ]
        if extractor_args:
            cmd += ["--extractor-args", extractor_args]
        cmd.append(f"https://www.youtube.com/watch?v={video_id}")

        log(f"    cliente: {label}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and wav_path.exists():
            break

        tail = (result.stderr or "").strip()[-300:]
        errors.append(f"[{label}] {tail}")
        log(f"    ✗ {tail.splitlines()[-1] if tail else 'sin stderr'}")
    else:
        joined = "\n".join(errors)
        raise RuntimeError(
            f"yt-dlp falló con todas las estrategias de cliente:\n{joined}\n\n"
            "Si todas dieron 403, actualizá a nightly:\n"
            '  pip install -U --pre "yt-dlp[default]"'
        )

    size_mb = wav_path.stat().st_size / 1e6
    log(f"  ✓ audio listo: {wav_path.name} ({size_mb:.0f} MB)")
    return wav_path


def _run_whisper(wav_path: Path, model_size: str, lang: str | None, device: str):
    """Una pasada de faster-whisper. Devuelve (segments, info, compute_type)."""
    from faster_whisper import WhisperModel

    compute_type = "int8_float16" if device == "cuda" else "int8"
    kwargs = {"device": device, "compute_type": compute_type}
    if device == "cpu":
        kwargs["cpu_threads"] = os.cpu_count() or 4

    model = WhisperModel(model_size, **kwargs)
    segments, info = model.transcribe(
        str(wav_path),
        language=lang,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        beam_size=5,
    )
    # `segments` es un generador perezoso: la GPU todavía no decodificó nada.
    # Forzamos la lista acá para que un fallo de decode explote DENTRO del
    # try/except del caller, no después de que creímos que salió bien.
    return list(segments), info, compute_type


def transcribe_whisper(
    wav_path: Path, model_size: str = "medium", lang: str | None = "es", force_cpu: bool = False
) -> tuple[list[Segment], str, str]:
    """Whisper local con cascada GPU -> CPU.

    El try/except envuelve la transcripción COMPLETA, no solo la carga del
    modelo: con 4 GB de VRAM la GPU carga bien y revienta a mitad del decode.
    """
    if model_size not in GPU_SAFE_MODELS and not force_cpu:
        log(f"  ⚠ modelo '{model_size}' es grande para 4 GB de VRAM — puede caer a CPU")

    devices = ["cpu"] if force_cpu else ["cuda", "cpu"]

    for device in devices:
        if device == "cuda":
            if not _setup_cuda_dlls():
                log("  ⚠ DLLs de CUDA no encontradas — salteando GPU")
                continue
            log(f"  intentando GPU (modelo {model_size}, int8_float16)...")
        else:
            log(f"  usando CPU (modelo {model_size}, int8) — más lento, misma calidad")

        started = time.time()
        try:
            raw_segments, info, compute_type = _run_whisper(wav_path, model_size, lang, device)
        except Exception as exc:
            log(f"  ✗ {device} falló: {type(exc).__name__}: {str(exc)[:200]}")
            if device == "cpu":
                raise
            log("  -> cayendo a CPU")
            continue

        elapsed = (time.time() - started) / 60
        segments = [
            Segment(seg.start, seg.end - seg.start, seg.text.strip()) for seg in raw_segments
        ]
        log(f"  ✓ {len(segments)} segmentos en {elapsed:.1f} min ({device}/{compute_type})")
        return segments, f"whisper:{device}", info.language

    raise RuntimeError("Whisper falló en GPU y en CPU")


# --------------------------------------------------------------------------
# Salidas
# --------------------------------------------------------------------------


def write_outputs(tr: Transcript, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # .txt — texto corrido, para pegar en un LLM
    txt = out_dir / f"{tr.video_id}.txt"
    txt.write_text(tr.full_text, encoding="utf-8")
    written.append(txt)

    # .srt — subtítulos
    srt = out_dir / f"{tr.video_id}.srt"
    with srt.open("w", encoding="utf-8") as fh:
        for i, seg in enumerate(tr.segments, 1):
            fh.write(f"{i}\n{fmt_srt_time(seg.start)} --> {fmt_srt_time(seg.end)}\n{seg.text}\n\n")
    written.append(srt)

    # .json — estructurado, para procesar
    js = out_dir / f"{tr.video_id}.json"
    js.write_text(
        json.dumps(
            {
                "video_id": tr.video_id,
                "url": f"https://www.youtube.com/watch?v={tr.video_id}",
                "source": tr.source,
                "language": tr.language,
                "duration_sec": round(tr.duration, 2),
                "low_fidelity": tr.is_low_fidelity,
                "warnings": tr.warnings,
                "segments": [
                    {"start": round(s.start, 2), "duration": round(s.duration, 2), "text": s.text}
                    for s in tr.segments
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    written.append(js)

    # .md — legible, con timestamps enlazables a YouTube
    md = out_dir / f"{tr.video_id}.md"
    lines = [
        f"# Transcripción — {tr.video_id}",
        "",
        f"- **URL:** https://www.youtube.com/watch?v={tr.video_id}",
        f"- **Fuente:** `{tr.source}`",
        f"- **Idioma:** {tr.language}",
        f"- **Duración:** {tr.duration / 60:.1f} min",
        f"- **Palabras:** {len(tr.full_text.split()):,}",
        "",
    ]
    if tr.warnings:
        lines.append("> [!WARNING]")
        for w in tr.warnings:
            lines.append(f"> {w}")
        lines.append("")
    lines += ["---", "", "## Texto", ""]
    for seg in tr.segments:
        stamp = fmt_stamp(seg.start)
        link = f"https://youtu.be/{tr.video_id}?t={int(seg.start)}"
        lines.append(f"**[{stamp}]({link})** {seg.text}")
        lines.append("")
    md.write_text("\n".join(lines), encoding="utf-8")
    written.append(md)

    return written


# --------------------------------------------------------------------------
# Doctor
# --------------------------------------------------------------------------


def doctor() -> int:
    log("=== Entorno ===\n")
    ok = True

    log(f"  python           {sys.version.split()[0]}")

    ffmpeg = shutil.which("ffmpeg")
    log(f"  ffmpeg           {'✓ ' + ffmpeg if ffmpeg else '✗ FALTA (winget install Gyan.FFmpeg)'}")
    ok &= bool(ffmpeg)

    log("\n--- Paso 1 (captions) ---")
    for pkg in ["youtube_transcript_api"]:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "?")
            log(f"  {pkg:24} ✓ {ver}")
        except ImportError:
            log(f"  {pkg:24} ✗ FALTA  ->  pip install youtube-transcript-api")
            ok = False

    log("\n--- Paso 2 (whisper) ---")
    for pkg, hint in [
        ("faster_whisper", "pip install faster-whisper"),
        ("yt_dlp", "pip install yt-dlp   (opcional — solo si no hay captions)"),
    ]:
        try:
            __import__(pkg)
            log(f"  {pkg:24} ✓")
        except ImportError:
            log(f"  {pkg:24} ✗ FALTA  ->  {hint}")

    log("\n--- GPU ---")
    if _setup_cuda_dlls():
        log("  DLLs CUDA                ✓ localizadas")
        try:
            from faster_whisper import WhisperModel

            WhisperModel("tiny", device="cuda", compute_type="int8_float16")
            log("  carga en GPU             ✓ funciona")
        except Exception as exc:
            log(f"  carga en GPU             ✗ {type(exc).__name__}: {str(exc)[:120]}")
            log("                             -> el Paso 2 va a usar CPU (más lento, igual calidad)")
    else:
        log("  DLLs CUDA                ✗ no encontradas")
        log("                             -> pip install nvidia-cublas-cu12 nvidia-cudnn-cu12")

    log("\n" + ("=== Paso 1 listo para usar ===" if ok else "=== Faltan dependencias del Paso 1 ==="))
    return 0 if ok else 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="YouTube -> transcripción, por cascada de costo creciente.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("url", nargs="?", help="URL de YouTube o video ID")
    parser.add_argument("--out", default="transcripts", help="carpeta de salida")
    parser.add_argument("--lang", default=None, help="idioma preferido (default: es, luego en)")
    parser.add_argument(
        "--auto", action="store_true", help="si no hay captions, caer a Whisper automáticamente"
    )
    parser.add_argument("--whisper", action="store_true", help="forzar Paso 2, saltear captions")
    parser.add_argument(
        "--no-auto", action="store_true", help="descartar captions ASR (fuerza Whisper si no hay manual)"
    )
    parser.add_argument("--model", default="medium", help="modelo Whisper (default: medium)")
    parser.add_argument("--cpu", action="store_true", help="forzar CPU, saltear GPU")
    parser.add_argument("--doctor", action="store_true", help="verificar entorno y salir")
    args = parser.parse_args()

    if args.doctor:
        return doctor()

    if not args.url:
        parser.error("falta la URL (o usá --doctor)")

    video_id = extract_video_id(args.url)
    langs = [args.lang] + DEFAULT_LANGS if args.lang else DEFAULT_LANGS
    out_dir = Path(args.out)
    tr: Transcript | None = None

    # --- Paso 1 ---
    if not args.whisper:
        log(f"\n[PASO 1] captions de YouTube — {video_id}")
        tr = fetch_captions(video_id, langs, allow_asr=not args.no_auto)

    # --- Paso 2 ---
    if tr is None:
        needs_step2 = args.whisper or args.auto or args.no_auto
        if not needs_step2:
            log("\n" + "─" * 68)
            log("Sin captions usables. El Paso 2 (Whisper local) puede resolverlo,")
            log("pero descarga el audio y consume cómputo — no lo hago sin que lo pidas.")
            log("")
            log(f"  python {Path(__file__).name} \"{args.url}\" --whisper")
            log("─" * 68)
            return 1

        log(f"\n[PASO 2] Whisper local — {video_id}")
        wav = download_audio(video_id, out_dir / ".audio")
        segments, source, detected = transcribe_whisper(
            wav, model_size=args.model, lang=args.lang or "es", force_cpu=args.cpu
        )
        tr = Transcript(
            video_id=video_id, segments=segments, source=source, language=detected
        )

    # --- Salidas ---
    written = write_outputs(tr, out_dir)

    log("\n=== LISTO ===")
    log(f"  fuente     {tr.source}")
    log(f"  idioma     {tr.language}")
    log(f"  duración   {tr.duration / 60:.1f} min")
    log(f"  segmentos  {len(tr.segments):,}")
    log(f"  palabras   {len(tr.full_text.split()):,}")
    for path in written:
        log(f"  -> {path}")

    if tr.is_low_fidelity:
        log("\n  ⚠ Caption ASR. Sirve para entender, no para citar textual.")
        log(f"    Para fidelidad técnica:  --whisper --model {args.model}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
