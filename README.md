# youtube_transcript_power

De una URL de YouTube a texto usable, gastando lo mínimo posible.

No es otro wrapper de Whisper. La idea central es una **cascada de costo creciente**:
el 90% de los videos ya tienen subtítulos publicados, así que bajarlos toma 30 segundos
y no instala nada. Whisper es el plan B, no el plan A.

```bash
python scripts/yt_transcript.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

Salidas en `transcripts/`: `.md` (timestamps enlazables a YouTube), `.txt` (texto corrido
para pegar en un LLM), `.srt` (subtítulos), `.json` (estructurado).

---

## La cascada

| Paso | Qué hace | Costo | Cuándo |
|---|---|---|---|
| **1** | captions de YouTube | ~30 seg, 0 instalación | siempre primero |
| **2a** | yt-dlp + faster-whisper GPU | ~8 min / 75 min de audio | sin captions, o hace falta fidelidad |
| **2b** | faster-whisper CPU | ~55 min / 75 min de audio | la GPU falló — misma calidad de texto |

El árbol de decisión completo, con los tiempos medidos y las trampas de cada escalón,
está en **[METODOLOGIA.md](METODOLOGIA.md)**.

**Después de transcribir viene resumir**, que es donde se pierde el valor:
**[RESUMEN_METODOLOGIA.md](RESUMEN_METODOLOGIA.md)** — por qué el chunking casi
siempre sobra, por qué Chain of Density va en 2-3 pasos y no 5, y cuál es el
riesgo que ninguna guía de resumen menciona (el LLM repara los errores del ASR
en silencio, y con confianza).

---

## Instalación

```bash
pip install -r requirements.txt        # Paso 1 + Whisper
pip install yt-dlp                     # Paso 2 — solo si te hace falta
```

`ffmpeg` tiene que estar en el PATH (`winget install Gyan.FFmpeg` en Windows).

Verificá que todo esté en su lugar:

```bash
python scripts/yt_transcript.py --doctor
```

---

## Uso

```bash
# Solo captions. Si no hay, te avisa y no descarga nada.
python scripts/yt_transcript.py "URL"

# Captions, y si no hay, cae a Whisper sin preguntar.
python scripts/yt_transcript.py "URL" --auto

# Saltear captions, ir directo a Whisper.
python scripts/yt_transcript.py "URL" --whisper

# Descartar captions auto-generados: solo acepta manuales, si no usa Whisper.
python scripts/yt_transcript.py "URL" --no-auto

# Otro idioma, otro modelo, forzar CPU.
python scripts/yt_transcript.py "URL" --lang en --model small --cpu
```

---

## El hallazgo: los dos motores fallan, en lugares distintos

Se corrieron ambos métodos sobre el mismo video de 71 minutos en español y se
compararon los mismos tramos temporales. La hipótesis de partida era *"Whisper
recupera los términos que el ASR rompe"*. **Es falsa.**

| | Método 1 — captions ASR | Método 2 — Whisper GPU |
|---|---|---|
| **Tiempo** | **30 seg** | 12,9 min |
| **Instalación** | ninguna | `yt-dlp` + 190 MB temporal |
| **Palabras** | 10.851 | 9.742 |
| **Segmentos** | 1.754 fragmentos | **815 oraciones** |
| **Muletilla "eh" /1000** | 28,7 | **1,0** |
| **Términos en inglés** | rotos | **correctos** |
| **Morfología española** | **correcta** | rota |

Ejemplos del mismo tramo, minuto 22 y 51:

| Captions ASR | Whisper medium | Cuál acertó |
|---|---|---|
| "**Te baja**, WhatsApp con audios" | "**Tech baja**, WhatsApp con audios" | Whisper |
| "**jubilada** docente" | "**cubilada** docente" | ASR |
| "**Learning go**" | "**learning goals**" | Whisper |
| "no es una **creencia**" | "no es una **credencia**" | ASR |
| "los **distribuidores** pagarían" | "los **distribuyores** pagarían" | ASR |

Whisper `medium` es multilingüe pero sesgado al inglés; el ASR de YouTube está
afinado para el español de la región. Cada uno rompe lo que el otro acierta.

**Qué usar:**

| Uso | Método |
|---|---|
| Entender de qué va el video | **1** — 30 segundos y listo |
| Alimentar un resumen con LLM | **2** — prosa limpia, sin muletillas |
| Citar textual | **ambos**, contrastando el pasaje |

El experimento completo, con las cuatro mediciones y el criterio fijado de
antemano, está en **[ANALISIS_metodo1_vs_metodo2.md](ANALISIS_metodo1_vs_metodo2.md)**.
Las dos transcripciones que lo sostienen están en [`samples/`](samples/) para que
cualquiera pueda verificarlo.

---

## Por qué existe `--no-auto`

YouTube distingue dos tipos de subtítulo, y la diferencia importa más de lo que parece:

- **MANUAL** — los subió el creador. Puntuación real, términos correctos.
- **ASR / auto-generated** — los generó el reconocedor de YouTube. Destroza vocabulario técnico.

Medido en un video real de 72 minutos en español, el ASR escribió:

| ASR | Era |
|---|---|
| "work tre" / "word tre" | worktree |
| "Google Phone" | Google Form |
| "multiginacional" | multigeneracional |
| "cortura del set" | cobertura del set |

Para **entender** el video, alcanza. Para **citarlo**, no. `--no-auto` descarta las pistas
ASR y va a Whisper, que sí reconoce esos términos.

Por defecto el script acepta ASR pero lo marca: `low_fidelity: true` en el JSON y un
bloque de advertencia en el `.md`.

---

## Trampa conocida: `youtube-transcript-api` cambió de API

La versión 1.x rompió la 0.6.x. Cualquier tutorial anterior a 2025 usa la forma muerta:

```python
# ❌ AttributeError en 1.x
YouTubeTranscriptApi.get_transcript(video_id)

# ✅ 1.x — instancia, y devuelve objetos, no dicts
api = YouTubeTranscriptApi()
for snippet in api.fetch(video_id, languages=["es", "en"]):
    print(snippet.text, snippet.start)
```

---

## Estado

Verificado el 2026-07-31 en Windows 11 + Python 3.11.9 + GTX 1650 (4 GB).

- Paso 1 — probado contra un video real de 72 min, 1754 segmentos ✅
- Paso 2 — implementado; requiere `pip install yt-dlp` para activarse

Detalle del entorno y tabla de errores conocidos en [METODOLOGIA.md](METODOLOGIA.md).
