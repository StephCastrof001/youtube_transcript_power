# Cómo resumir una transcripción — y qué parte es crítica

La transcripción es la parte fácil. El resumen es donde se pierde el valor.

Este documento no es una lista de trucos de prompt. Es un orden de decisiones:
qué preguntar antes de resumir, qué técnica corresponde según el tamaño, y cuál
es el único riesgo que realmente importa en una transcripción.

---

## Primero: la pregunta que casi todos se saltan

> **¿Para qué es el resumen?**

Sin eso, "resumir" no tiene definición. Un mismo video de 72 minutos produce
cuatro resúmenes incompatibles según el uso:

| Uso | Qué conserva | Qué tira |
|---|---|---|
| Decidir si vale mirarlo | tesis, duración, a quién le sirve | todo lo demás |
| Aprender el método que enseña | la secuencia de pasos, en orden | anécdotas, chat |
| Citarlo en algo propio | frases textuales + timestamp | paráfrasis |
| Alimentar otro agente | entidades, decisiones, datos duros | narrativa |

**Un resumen sin uso declarado no se puede evaluar.** Si no podés decir qué
tendría que poder hacer el lector después de leerlo, todavía no estás listo
para escribir el prompt. Este es el equivalente, en resumen, de pedir métrica
antes de codear.

---

## Segundo: elegir estrategia por tamaño — y el error de 2023

La literatura de resumen con LLM está dominada por tres técnicas de LangChain:

| Técnica | Cómo funciona | Cuándo nació |
|---|---|---|
| **Stuff** | metés todo el texto en un prompt | siempre |
| **Map-reduce** | partís en trozos, resumís cada uno en paralelo, resumís los resúmenes | contexto de 4k tokens |
| **Refine** | resumís el trozo 1, y vas refinando ese resumen con cada trozo siguiente | contexto de 4k tokens |

**Map-reduce y refine existen porque el texto no entraba.** Ese problema en
2026 casi no existe. Aplicarlos igual tiene un costo real:

- **Map-reduce pierde relaciones entre trozos.** Si el minuto 12 explica algo
  que recién cobra sentido en el minuto 60, ningún trozo lo ve junto.
- **Refine arrastra los errores.** Es secuencial: un error en el trozo 2 se
  propaga hasta el final, y además no se puede paralelizar.

### Regla de decisión

| Largo | Estrategia |
|---|---|
| **< 100k tokens** | **Stuff.** Texto entero, un solo prompt |
| 100k – 500k tokens | Stuff con modelo de contexto largo, o map-reduce por temas (no por conteo de tokens) |
| > 500k tokens | Map-reduce jerárquico, o RAG si la pregunta es puntual |

**Este transcript: 9.742 palabras ≈ 13.600 tokens. Stuff.** Sin chunking, sin
map-reduce, sin vector store. Cualquier pipeline más complejo acá es
sobreingeniería que agrega puntos de falla sin agregar calidad.

> Si vas a partir igual, **partí por temas, no por conteo de tokens.** Un corte
> a los 512 tokens cae en la mitad de una idea. Un corte en el cambio de tema
> no. En una clase grabada, los cambios de tema suelen coincidir con frases
> como "bueno, ahora vamos a...".

---

## Tercero: lo crítico de verdad

Elegida la estrategia, quedan tres cosas que sí mueven la aguja. En orden de
impacto.

### 1. Densidad de entidades — la técnica con evidencia

**Chain of Density (CoD)**, Adams et al. 2023 ([arXiv:2309.04269](https://arxiv.org/abs/2309.04269)),
citado 128+ veces. Es el método mejor medido que hay para resumen con LLM.

**Cómo funciona:**

1. Generá un resumen inicial deliberadamente vago, pobre en entidades
2. Identificá entidades importantes que faltaron
3. Reescribí incorporando 1-3 entidades más — **sin alargar el texto**
4. Repetí

El paso 3 es el truco entero: al no poder crecer, el modelo está obligado a
sacar relleno para meter contenido. Frases como "el instructor habla sobre
varios temas" se van solas.

**El hallazgo que importa, y que casi nadie cita bien:** el paper corre 5
iteraciones, **pero los humanos prefieren la 2 o la 3**. La 1 es demasiado
vaga; la 4 y la 5 son tan densas que se vuelven ilegibles.

> **Usá 2-3 pasos, no 5.** Más denso no es mejor — hay un óptimo, y está antes
> del final.

**Beneficio secundario, valioso en video:** CoD reduce el *lead bias* — la
tendencia del modelo a sobre-representar el principio del texto. En una clase
de 72 minutos donde la conclusión llega al minuto 68, eso es la diferencia
entre un resumen útil y uno que describe los saludos iniciales.

### 2. Anclaje a timestamps — lo que hace verificable el resumen

Un resumen sin anclaje es una afirmación que hay que creer. Con anclaje, es
una afirmación que se puede chequear en 5 segundos.

```markdown
- Diseña las personas sintéticas antes del research de mercado, no después —
  [22:14](https://youtu.be/py59r7BL2Ys?t=1334)
```

Por eso el `.md` que genera `yt_transcript.py` trae cada segmento con su link.
**Pedí explícitamente en el prompt que cada afirmación cite su timestamp.** Sin
pedirlo, no lo hace.

Esto también es la mejor defensa contra la alucinación: una afirmación
inventada no tiene dónde anclarse, y el timestamp falso se detecta al primer
click.

### 3. El riesgo específico de una transcripción: el LLM "arregla" el ASR

**Este es el punto que no aparece en ninguna guía de resumen**, porque casi
todas asumen texto limpio.

Una transcripción trae errores de reconocimiento. Un LLM es extremadamente
bueno reparando texto degradado — y ese es justamente el problema: **repara con
confianza y sin avisar.**

Casos reales de este video ([ANALISIS_metodo1_vs_metodo2.md](ANALISIS_metodo1_vs_metodo2.md)):

| El transcript dice | El LLM probablemente escriba | ¿Era? |
|---|---|---|
| "Google Phone" | "Google Phone" o "Google Home" | **Google Form** |
| "work tre" | "work tree" | worktree |
| "credencia" | "credencial" | **creencia** |
| "white combinator" | "Y Combinator" | (probable, sin verificar) |

"Google Home" y "credencial" son palabras perfectamente plausibles que
**cambian el significado**. Y el resumen las va a presentar con la misma
seguridad que los datos correctos.

**Las tres defensas, en orden de facilidad:**

1. **Instruí la incertidumbre explícitamente.** "Si un término parece mal
   transcripto, marcalo `[sic?]` en vez de corregirlo en silencio."
2. **Pasá las dos transcripciones** cuando tengas ambas. Donde difieren, hay
   un error de alguna de las dos — el modelo puede señalarlo en vez de elegir.
3. **Verificá contra el video** los nombres propios, cifras y herramientas
   antes de citar. Es la única defensa real para algo que vas a publicar.

---

## Cómo saber si el resumen salió bien

Tres chequeos, de más barato a más caro:

| Chequeo | Cómo | Detecta |
|---|---|---|
| **Densidad** | ¿cuántas entidades concretas por párrafo? | relleno, vaguedad |
| **Anclaje** | ¿cada afirmación tiene timestamp? ¿un click al azar lo confirma? | invención |
| **Cobertura** | ¿el último tercio del video está representado? | lead bias |

**El test de una línea, si solo hacés uno:** tomá tres afirmaciones al azar del
resumen y abrí sus timestamps. Si las tres se sostienen, el resumen sirve. Si
una no, el resumen entero es sospechoso — el error nunca viene solo.

---

## Plantilla de prompt

Adaptá el bloque `USO` y el bloque `FORMATO`. El resto queda igual.

````markdown
Sos un analista que extrae método operativo de clases grabadas.

# USO
Este resumen es para: [DECILO EXPLÍCITAMENTE].
Después de leerlo, el lector tiene que poder: [QUÉ ACCIÓN].

# FUENTE
Transcripción de un video de {DURACIÓN} min.
Origen: {captions ASR | whisper local}.
ADVERTENCIA: contiene errores de reconocimiento de voz.

# REGLAS DE FIDELIDAD
1. No corrijas términos que parezcan mal transcriptos. Marcalos `[sic?]`
   con tu mejor hipótesis entre paréntesis.
   Ejemplo: "Google Phone [sic? probablemente Google Form]"
2. Toda afirmación lleva su timestamp en formato [MM:SS].
3. Si algo no está en la transcripción, no lo pongas. No completes con
   conocimiento general del tema.
4. Distinguí lo que el orador HIZO de lo que MENCIONÓ que se puede hacer.

# MÉTODO — Chain of Density, 3 pasos
Paso 1: resumen inicial en {N} palabras, deliberadamente general.
Paso 2: listá 5 entidades importantes que faltaron (herramientas, cifras,
        nombres, decisiones concretas).
Paso 3: reescribí en las MISMAS {N} palabras incorporando 3 de esas
        entidades. Sacá relleno para que entren.
Repetí los pasos 2-3 una vez más. Devolveme solo el último resumen.

# FORMATO
[TU ESTRUCTURA]

# TRANSCRIPCIÓN
{TEXTO}
````

---

## Resumen del resumen

| Decisión | Respuesta |
|---|---|
| ¿Chunking? | **No**, si entra en contexto. Casi siempre entra |
| ¿Qué técnica? | **Chain of Density, 2-3 pasos** — no 5 |
| ¿Qué es crítico? | **Declarar el uso** antes de escribir el prompt |
| ¿Cuál es el riesgo real? | el LLM **repara errores de ASR en silencio** |
| ¿Cómo se verifica? | **timestamps** — tres al azar, un click cada uno |

---

## Fuentes

- Adams et al., *From Sparse to Dense: GPT-4 Summarization with Chain of
  Density Prompting* — [arXiv:2309.04269](https://arxiv.org/abs/2309.04269).
  El hallazgo de que el óptimo humano está en el paso 2-3, no en el 5, está en
  la sección de evaluación humana.
- Google Cloud, *Long document summarization with Workflows and Gemini* —
  map-reduce vs refinamiento iterativo, y por qué map-reduce paraleliza.
- Arize, *LLM Summarization: Getting to Production* — problemas de recursión en
  map-reduce y pérdida de coherencia entre trozos.
