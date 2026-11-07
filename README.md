# Pulso

**Radar predictivo de sobrecarga académica.** Hackathon ENEISOFT XVI (FISI-UNMSM), sub-eje Bienestar.

## Problema

Cada docente fija las fechas de sus evaluaciones por separado. Nadie mira el calendario completo de la cohorte,
así que los estudiantes de un mismo ciclo terminan con varios exámenes y entregas fuertes en la misma semana
(típicamente en parciales y finales). Esa sobrecarga se puede prever desde el primer día, porque ya está escrita en los sílabos.

## Solución

Pulso lee los sílabos del ciclo, arma el calendario de evaluaciones de la cohorte y propone cómo redistribuirlas.

1. **Extracción con IA:** convierte cada sílabo PDF en texto y un LLM extrae las evaluaciones con salida estructurada
   (curso, tipo, fecha o semana, peso). La salida se valida con Pydantic y se reintenta si falla.
2. **Motor de carga:** calcula un índice de carga semanal, `Σ(peso × factor de tipo)`, y detecta colisiones:
   3 o más evaluaciones fuertes en una ventana de 72 h.
3. **Optimizador CP-SAT (OR-Tools):** mueve evaluaciones dentro de una ventana de ±k días para minimizar el pico de carga.
   Respeta las fechas bloqueadas por el docente, los feriados y la semana de exámenes. Devuelve qué se movió y cuánto bajó el pico.
4. **Propuesta para el coordinador:** el LLM redacta la reprogramación con los datos del solver.
5. **Simulador docente:** antes de fijar una fecha, el docente ve qué % de la cohorte tendría colisión y qué fecha alternativa conviene.

## Arquitectura

Monolito en Python: una sola app FastAPI sirve la interfaz web (Jinja2 + HTMX) y la lógica, y se despliega en Vercel como una única función.

```
PDF sílabos ──► extraction (pdfplumber + LLM) ──► data/cohorte.json
                                                        │
                                                        ▼
                          engine (carga + colisiones) ──► optimizer (CP-SAT, simulador)
                                                        │
                                                        ▼
                                  src/app.py (FastAPI) ──► src/ui (Jinja2 + HTMX) ──► Vercel
```

| Capa | Tecnología |
|---|---|
| Modelo de datos | Pydantic v2 |
| Extracción | pdfplumber + SDK de LLM |
| Optimización | Google OR-Tools (CP-SAT) |
| Web | FastAPI + Jinja2 + HTMX |
| Despliegue | Vercel (Python runtime) |

## Modelo de datos

Definido en [`src/models.py`](src/models.py).

**`Evaluacion`**

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `str` | Se genera desde curso + nombre si no viene |
| `curso` | `str` | Nombre del curso |
| `nombre` | `str` | Nombre en el sílabo, p. ej. "Práctica calificada 2" |
| `tipo` | `TipoEvaluacion` | `examen_parcial`, `examen_final`, `practica_calificada`, `laboratorio`, `proyecto`, `exposicion`, `tarea`, `control_lectura`, `otro` |
| `fecha` | `date` (opcional) | Fecha ISO. Se exige `fecha` **o** `semana` |
| `peso` | `float` | % de la nota final del curso, (0–100] |
| `semana` | `int` (opcional) | Semana del ciclo, 1–17 |
| `bloqueada` | `bool` | `true` si el docente no permite moverla |

**`Cohorte`**: `nombre`, `ciclo`, `fecha_inicio` (lunes de la semana 1) y `evaluaciones`. Valida que los IDs no se repitan.

### Datos mock

[`data/mock/evaluaciones_mock.json`](data/mock/evaluaciones_mock.json) es una cohorte del ciclo 2026-II con 6 cursos y 30 evaluaciones.
Trae colisiones a propósito para la demo:
- semana 8: 4 parciales de lunes a jueves;
- semana 12: 5 evaluaciones;
- semana 16: finales bloqueados.

```python
from src.models import cargar_cohorte

cohorte = cargar_cohorte("data/mock/evaluaciones_mock.json")
print(len(cohorte.evaluaciones), cohorte.cursos)  # 30 evaluaciones, 6 cursos
```

## Estructura

```
.
├── data/
│   ├── silabos/              PDFs de sílabos de prueba
│   └── mock/                 evaluaciones_mock.json
├── src/
│   ├── models.py             esquema Evaluacion / Cohorte
│   ├── extraction/           extracción con IA
│   ├── engine/               índice de carga y colisiones
│   ├── optimizer/            modelo CP-SAT y simulador docente
│   ├── app.py                entrypoint FastAPI (Vercel)
│   └── ui/                   templates/ y static/
├── tests/
├── .env.example
└── vercel.json
```

## Ejecutar en local

Requiere Python 3.12 o superior.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt   # app + pytest (Vercel solo instala requirements.txt)
cp .env.example .env               # completar LLM_API_KEY y LLM_MODEL (OpenRouter)
python scripts/verificar_entorno.py  # dependencias + llamada de prueba al LLM
uvicorn src.app:app --reload       # http://127.0.0.1:8000
```

## Despliegue en Vercel

```bash
npm i -g vercel
vercel link                        # vincular el repo al proyecto de Vercel
vercel env add LLM_API_KEY         # la API key va como variable de entorno, nunca en el código
vercel --prod
```

Vercel detecta `src/app.py` como entrypoint FastAPI. Hay que tener en cuenta:
- El filesystem es de solo lectura, así que `data/cohorte.json` se genera antes y se commitea.
- El body de cada petición tiene un límite de unos 4.5 MB, así que los PDFs subidos deben ser pequeños.

## Estado

| Módulo | Estado |
|---|---|
| Estructura del repo (PUL-01) | ✅ |
| Modelo de datos + mock (PUL-02) | ✅ |
| Entorno y dependencias (PUL-03) | ⏳ |
| Extracción con IA (PUL-04 a PUL-08) | ⏳ |
| Motor de carga (PUL-09, PUL-10) | ⏳ |
| Optimizador y simulador (PUL-11 a PUL-13) | ⏳ |
| Interfaz web + Vercel (PUL-14 a PUL-18) | ⏳ |

## Viabilidad

Pulso se piensa para la FIA de la USMP. El Reglamento de Evaluación del Aprendizaje permite reprogramar **fechas**
(parciales y finales: Departamento Académico al inicio del semestre; el resto: cada docente, art. 7), pero no el tipo
ni el número de evaluaciones (art. 6). Pulso solo propone fechas. Análisis completo, stakeholders y fuentes en
[`docs/viabilidad.md`](docs/viabilidad.md).

## Equipo y flujo de trabajo

**SpookyTech** (USMP): Emily Peralta Cenepo · Viviana Flores Montes · Sergio Ascurra Perez.


| Integrante | Módulo |
|---|---|
| A | Extracción con IA, README, entrega final |
| B | Motor de carga, optimizador CP-SAT, diapositivas |
| C | Interfaz web + Vercel, simulador docente, video demo |

Ramas `feat/<módulo>-<descripción>`, commits [Conventional Commits](https://www.conventionalcommits.org/) en español
y un PR por tarea hacia `main`. Las reglas completas están en [`CLAUDE.md`](CLAUDE.md).
