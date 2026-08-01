# Análisis — Método 1 vs Método 2

Generado: 2026-08-01 00:33

| | Método A | Método B |
|---|---|---|
| Fuente | `captions:asr` | `whisper:cuda` |
| Archivo | `transcripts\py59r7BL2Ys.json` | `transcripts_whisper\py59r7BL2Ys.json` |
| Idioma | es | es |

---

## 1. Volumen

| Métrica | A | B | Δ |
|---|---:|---:|---:|
| Segmentos | 1,754 | 815 | -53.5% |
| Palabras | 10,851 | 9,742 | -10.2% |
| Vocabulario único | 2,665 | 2,546 | -4.5% |
| Caracteres | 61,079 | 55,760 | -8.7% |

## 2. Términos técnicos — el test que decide

| Término | A | B | Veredicto |
|---|---:|---:|---|
| worktree | 0 | 2 | **B lo recupera** |
| Google Form | 4 | 0 | B lo pierde |
| vibe coding | 0 | 0 | ausente en ambos |
| subagente | 5 | 6 | empate |
| MCP | 2 | 3 | empate |
| Claude Code | 0 | 0 | ausente en ambos |
| prompt | 1 | 1 | empate |
| commit | 0 | 0 | ausente en ambos |
| repo | 4 | 3 | empate |
| endpoint | 0 | 0 | ausente en ambos |
| deploy | 0 | 0 | ausente en ambos |
| token | 6 | 6 | empate |
| persona sintética | 6 | 6 | empate |
| backlog | 0 | 0 | ausente en ambos |
| framework | 0 | 0 | ausente en ambos |
| markdown | 0 | 2 | **B lo recupera** |
| API | 4 | 5 | empate |
| brief | 0 | 0 | ausente en ambos |

## 3. Divergencia de vocabulario

**Solapamiento (Jaccard): 57.4%**

| Solo en B (B lo oyó, A no) | n | Solo en A (A lo oyó, B no) | n |
|---|---:|---|---:|
| perfecto, | 11 | okay. | 86 |
| acuerdo, | 10 | okay, | 48 |
| excelente, | 6 | entrevista. | 15 |
| manana, | 6 | ¿okay? | 13 |
| dias, | 5 | ¿quien | 8 |
| indice, | 5 | manana. | 7 |
| buenisimo, | 4 | [carraspeo] | 5 |
| exactamente, | 4 | ¿donde | 5 |
| respuestas, | 4 | hola, | 4 |
| genial, | 3 | dias. | 4 |
| todavia, | 3 | genial. | 4 |
| subagentes, | 3 | chat. | 4 |
| sqlite, | 3 | contexto. | 4 |
| market, | 3 | hecho. | 4 |
| estamos, | 3 | exactamente. | 4 |
| hora, | 3 | obviamente | 4 |
| sonnet | 3 | hora. | 4 |
| fecha, | 3 | respuestas. | 4 |
| credencia | 3 | abrazo | 4 |
| exacto, | 3 | todo, | 3 |

## 4. Densidad de muletillas (por 1000 palabras)

| Muletilla | A | B |
|---|---:|---:|
| eh | 28.7 | 1.0 |
| este | 1.8 | 2.0 |
| okay | 13.9 | 0.0 |
| ok | 0.0 | 17.7 |
| digamos | 0.6 | 0.2 |
| o sea | 0.5 | 0.6 |
| basicamente | 0.3 | 0.3 |
| nada | 0.9 | 1.0 |

---

## Veredicto

- Términos que **B recupera** y A rompe: **2**
  - worktree, markdown
- Términos que **B pierde** y A tiene: **1**
  - Google Form

> **Diferencia MENOR.** El Método 1 alcanza. El Método 2 es lujo para
> este tipo de contenido — el costo en tiempo no se paga.

### Criterio usado

Definido **antes** de correr el experimento, no después de ver los números:

| Términos recuperados | Lectura |
|---|---|
| ≥ 5 | significativa — el Paso 2 se justifica |
| 3-4 | moderada — solo si citás textual |
| < 3 | menor — el ASR alcanza |

---

## 5. Inspección manual — mismo tramo, ambas fuentes

El conteo automático de términos es una medición pobre: la lista de términos
es fija, y la mitad no aparece en el video. La inspección del **mismo tramo
temporal** en ambas fuentes muestra algo que el conteo no captura.

### Minuto 22:00

| A — captions ASR | B — whisper medium | Correcto |
|---|---|---|
| "**Te baja**, WhatsApp con audios" | "**Tech baja**, WhatsApp con audios" | **B** |
| "**jubilada** docente" | "**cubilada** docente" | **A** |
| "foody" | "**foodie**" | **B** |
| "edades 21 baje horizontal" | "**edad de 21 años, tech baja, horizontal**" | **B** |
| "no es otro target" | "no es nuestra tarea" | ninguno |

### Minuto 51:00

| A — captions ASR | B — whisper medium | Correcto |
|---|---|---|
| "no es una **creencia**" | "no es una **credencia**" | **A** |
| "si los **distribuidores** pagarían" | "si los **distribuyores** pagarían" | **A** |
| "**Learning go**" | "**learning goals**" | **B** |
| "crea el **Google Form**" | (perdido) | **A** |

### El patrón

**No son mejor y peor. Son errores complementarios.**

- **B / Whisper gana en préstamos del inglés** — tech, foodie, learning goals,
  worktree, markdown.
- **A / ASR de YouTube gana en morfología española** — jubilada, creencia,
  distribuidores, Google Form.

Explicación probable: `medium` de Whisper es multilingüe pero está pesadamente
sesgado al inglés, mientras que el ASR de YouTube está afinado para español
rioplatense. Cada uno falla donde el otro tiene ventaja de entrenamiento.

### Donde B sí gana sin discusión: ruido

| | A | B |
|---|---:|---:|
| "eh" por 1000 palabras | 28.7 | **1.0** |
| `[carraspeo]`, saludos al chat | presentes | ausentes |
| Segmentos | 1,754 fragmentos | **815 oraciones** |

B produce prosa; A produce esquirlas. Para pasarle el texto a un LLM o para
leerlo, B es netamente mejor aunque tenga errores léxicos propios.

---

## Recomendación operativa

| Uso | Método |
|---|---|
| Entender de qué va el video | **1** — captions, 30 seg |
| Alimentar un resumen con LLM | **2** — Whisper, texto limpio sin muletillas |
| Citar textual con precisión | **ambos**, y contrastar el pasaje |
| Términos técnicos en inglés | **2** |
| Nombres y morfología en español | **1** |

**Lo que este experimento refuta:** la hipótesis de partida era "Whisper recupera
los términos que el ASR rompe". Falsa. Whisper rompe otros. La ganancia real de
Whisper está en la limpieza del texto, no en la fidelidad léxica.

**Timebox y costo:** Whisper `medium` en GTX 1650, 71 min de audio → **12.9 min**
de GPU (5.5x tiempo real), 1880/4096 MiB de VRAM. Más ~190 MB de disco temporal.
