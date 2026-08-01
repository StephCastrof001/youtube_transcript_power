# Metodología — YouTube a transcripción

Cómo sacar texto de un video de YouTube en **esta máquina**, de lo más barato a lo más caro.

La regla que ordena todo: **no instales nada hasta que el escalón anterior falle.**
Cada escalón cuesta más que el anterior en tiempo, disco y batería. Bajás un escalón solo
cuando el de arriba te dijo que no, no cuando sospechás que va a decir que no.

---

## El árbol de decisión

```
                    ┌─────────────────────────┐
                    │  URL de YouTube          │
                    └───────────┬─────────────┘
                                │
                                ▼
              ┌──────────────────────────────────┐
              │ PASO 1 — ¿Tiene captions?        │
              │ youtube-transcript-api           │
              │ ~30 seg · 0 instalación · 0 disco│
              └────────┬──────────────┬──────────┘
                       │              │
              ¿pista MANUAL?    ¿solo ASR/auto?
                       │              │
                       ▼              ▼
              ┌────────────┐   ┌──────────────────────────┐
              │  LISTO ✅   │   │ ¿Para qué lo necesitás?  │
              │ Máxima      │   └────┬────────────────┬────┘
              │ calidad     │        │                │
              └────────────┘   ENTENDER          CITAR / técnico
                                     │                │
                                     ▼                ▼
                              ┌───────────┐    ┌─────────────┐
                              │ LISTO ✅   │    │  bajá a     │
                              │ Sirve, con │    │  PASO 2     │
                              │ términos   │    └──────┬──────┘
                              │ rotos      │           │
                              └───────────┘            │
                                                       │
              ┌────────────────────────────────────────┘
              ▼
    ┌────────────────────────────────────────┐
    │ PASO 2 — Whisper local                 │
    │ yt-dlp (audio) + faster-whisper        │
    │ REQUIERE: pip install yt-dlp           │
    └────────┬───────────────────────────────┘
             │
             ▼
    ┌────────────────────┐      falla en load o decode
    │ 2a · GPU cuda      │─────────────────────────────┐
    │ int8_float16       │                             │
    │ ~4-8x tiempo real  │                             ▼
    └────────┬───────────┘                    ┌──────────────────┐
             │ ok                             │ 2b · CPU int8    │
             ▼                                │ ~1.3x tiempo real│
        ┌─────────┐                           │ MISMA calidad    │
        │ LISTO ✅ │◄──────────────────────────┤ 0 descarga extra │
        └─────────┘                           └──────────────────┘
```

---

## Paso 1 — Captions de YouTube

**Costo:** ~30 segundos. Cero instalación. Cero disco.
**Sirve para:** entender de qué va el video, buscar un tema, alimentar un resumen.
**No sirve para:** citar textual, nombres de herramientas, comandos, jerga técnica.

```bash
python scripts/yt_transcript.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Las dos calidades de caption, y por qué importa la diferencia

| Tipo | Origen | Calidad |
|---|---|---|
| **MANUAL** | subida por el creador | alta — puntuación real, términos correctos |
| **ASR / auto-generated** | reconocedor de YouTube | media — destroza vocabulario técnico |

El script prefiere MANUAL sobre ASR automáticamente. Si solo hay ASR, te avisa.

**Daño típico del ASR en español técnico** (medido en un video real de 72 min):

| ASR escribió | Era |
|---|---|
| "work tre" / "word tre" | worktree |
| "Google Phone" | Google Form |
| "Orquestador de agentes vi" | ...vibe |
| "multiginacional" | multigeneracional |
| "cortura del set" | cobertura del set |

Si tu uso tolera eso → terminaste. Si no → Paso 2.

### Trampa conocida: la API cambió

`youtube-transcript-api` 1.x **rompió** la API de 0.6.x. El método estático murió:

```python
# ❌ MUERTO en 1.x — AttributeError
YouTubeTranscriptApi.get_transcript(video_id)

# ✅ 1.x — instancia, y devuelve objetos, no dicts
api = YouTubeTranscriptApi()
fetched = api.fetch(video_id, languages=["es", "en"])
for snippet in fetched:
    print(snippet.text, snippet.start, snippet.duration)
```

Cualquier script o tutorial de antes de 2025 usa la forma muerta. Ojo al copiar.

---

## Paso 2 — Whisper local (solo si el Paso 1 no alcanza)

**Costo:** `pip install yt-dlp` (~3 MB) + tiempo de cómputo.
**Sirve para:** videos sin captions, o cuando necesitás términos técnicos correctos.

```bash
pip install yt-dlp
python scripts/yt_transcript.py "URL" --whisper --model medium
```

### 2a — GPU (el camino rápido)

**Ya está resuelto en esta máquina.** Las dependencias CUDA están instaladas:
`nvidia-cublas-cu12` + `nvidia-cudnn-cu12`.

**El detalle que hace fallar a todo el mundo en Windows:** los paquetes `nvidia.*` son
*namespace packages*, así que `módulo.__file__` es `None` y no podés ubicar los DLL de la
forma habitual. Hay que:

1. Resolver el path con `list(mod.__path__)[0]`
2. Llamar `os.add_dll_directory(bin_path)` **ANTES** de `from faster_whisper import WhisperModel`

Si importás faster-whisper primero, ya perdiste — el loader de DLL de Windows ya buscó y falló.
`scripts/yt_transcript.py` hace esto correctamente en `_setup_cuda_dlls()`.

### 2b — CPU (el fallback que siempre funciona)

`device="cpu", compute_type="int8"`. **Misma calidad de texto**, ~6x más lento.
No descarga nada extra. Es el escalón final: si esto falla, el problema no es el entorno.

**Importante:** el fallback envuelve el `transcribe` completo, no solo el `load`. La GPU a veces
carga bien y revienta en decode a mitad de camino — un try/except solo alrededor del load
no te salva de eso.

---

## Rendimiento real medido en esta máquina

Audio de 75 minutos, modelo `medium`, español:

| Camino | Tiempo | Disco extra | Calidad |
|---|---|---|---|
| Paso 1 — captions | **~30 seg** | 0 | media (si es ASR) |
| Paso 2a — GPU int8_float16 | ~8-9 min | ~1 GB (CUDA, ya instalado) | alta |
| Paso 2b — CPU int8 | ~55 min | 0 | alta (idéntica a GPU) |

**Aviso de disco:** esta PC vive cerca del 100% de capacidad. Verificá espacio antes de
instalar CUDA en una máquina nueva. En ésta ya está pago, no vuelve a descargar.

---

## Entorno verificado

Fecha de verificación: 2026-07-31.

| Componente | Versión | Estado |
|---|---|---|
| Windows | 11 Home Single Language | — |
| Python | 3.11.9 (Microsoft Store) | ✅ |
| GPU | GTX 1650 (4 GB VRAM) | ✅ |
| `ffmpeg` | 8.1.2 (winget Gyan.FFmpeg) | ✅ en PATH |
| `youtube-transcript-api` | 1.2.4 | ✅ |
| `faster-whisper` | 1.2.1 | ✅ |
| `ctranslate2` | 4.8.1 | ✅ |
| `nvidia-cublas-cu12` | 12.9.2.10 | ✅ |
| `nvidia-cudnn-cu12` | 9.25.0.15 | ✅ |
| `yt-dlp` | — | ❌ instalar solo si hace falta el Paso 2 |

Modelo `medium` cacheado en `~/.cache/huggingface/hub` — no se vuelve a descargar.

Verificá el entorno vos mismo con:

```bash
python scripts/yt_transcript.py --doctor
```

---

## Cuando algo falla

| Síntoma | Causa | Qué hacer |
|---|---|---|
| `AttributeError: get_transcript` | script escrito para la API 0.6.x | usar `.fetch()` de instancia |
| `TranscriptsDisabled` | el creador desactivó captions | Paso 2 |
| `NoTranscriptFound` | no hay pista en ese idioma | probar `--lang en`, o Paso 2 |
| `IpBlocked` / `RequestBlocked` | YouTube bloqueó la IP | Paso 2 (no depende de la API) |
| `Could not load cublas64_12.dll` | DLL de CUDA no está en el path del loader | ver 2a — orden de `add_dll_directory` |
| GPU carga pero muere a mitad | VRAM insuficiente (4 GB es justo) | cae solo a 2b, o usá `--model small` |
| Términos técnicos rotos | caption ASR | Paso 2 con `--whisper` |

---

## Por qué esta metodología existe

Se construyó al revés de como suele hacerse, a propósito.

El primer intento fue armar la herramienta antes de transcribir un solo video. Error: se
diagnosticó un entorno, se instalaron cosas, se buscaron repos — y no había ni una línea de
texto para mostrar. La corrección fue invertir el orden:

1. Sacá el resultado con lo mínimo que ya tenés instalado
2. Solo si eso falla, pedí instalar algo — y decí explícitamente por qué
3. Recién ahí codificá lo que **comprobaste** que funciona, no lo que suponés

Este documento es el paso 3. Cada escalón acá está medido, no estimado.
