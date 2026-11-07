# CLAUDE.md — PULSO

PULSO es un radar predictivo de sobrecarga académica (Hackathon ENEISOFT XVI, sub-eje Bienestar).
Extrae evaluaciones de sílabos PDF con IA, calcula la carga semanal por cohorte, detecta colisiones
y propone una reprogramación óptima con un solver CP-SAT. Stack: Python, Pydantic, OR-Tools, FastAPI + Jinja2/HTMX, pdfplumber, SDK de LLM.

## Despliegue: Vercel (monolito)

- Toda la app (UI + extracción + motor + optimizador) es **un solo proyecto FastAPI** desplegado en Vercel como una única Vercel Function.
- Entrypoint: `src/app.py` con una instancia `app = FastAPI()` (Vercel la detecta automáticamente). La UI se sirve con plantillas Jinja2 y archivos estáticos desde `src/ui/` (`templates/`, `static/`).
- No usar Streamlit: no se puede desplegar en Vercel.
- Local: `uvicorn src.app:app --reload`. Configuración en `vercel.json` (p. ej. `maxDuration` si el solver o el LLM tardan).
- El filesystem de Vercel es de solo lectura (salvo `/tmp`): `data/cohorte.json` se genera antes y se commitea; la demo no depende de llamar al LLM en vivo.
- Las peticiones a una Vercel Function tienen un límite de tamaño de body (~4.5 MB): los PDFs subidos deben ser pequeños.
- La API key del LLM va como variable de entorno en el proyecto de Vercel, nunca en el código.

## Planificación: `PULSO_Product_Backlog.xlsx`

- El Excel es **la fuente de verdad de la planificación** (backlog, responsables, sprints, dependencias, convenciones).
- **Nunca se sube al repo.** Está en `.gitignore`; no lo agregues con `git add -f`, no lo incluyas en commits ni PRs.
- Léelo antes de empezar una tarea para confirmar su `Estado`, `Rama`, `Depende de` y su criterio de aceptación (DoD).
- No lo modifiques salvo que el usuario lo pida (normalmente solo se actualiza la columna `Estado`).
- Hojas: `Product Backlog`, `Resumen`, `Plan por hora`, `Convenciones Git`, `Hoy (pre-evento)`.

## Estado de los PRs y de `main` (comprobar SIEMPRE antes de avanzar)

Antes de empezar una tarea, crear una rama o abrir un PR, comprueba el estado real de los PRs y de `main`:

```bash
git fetch --all --prune
gh pr list --state all --json number,title,state,baseRefName,headRefName,mergedAt
git log --oneline origin/main..origin/<rama-de-la-dependencia>   # debe salir vacío
```

1. Un PR cuenta como integrado **solo si está `MERGED` con base `main`**. Si se mergeó contra otra rama (PR apilado), su código **no está en `main`**.
2. Para cada dependencia, verifica que su rama no tenga commits fuera de `main` (el `git log origin/main..origin/<rama>` debe salir vacío).
3. Si `main` no está al día con un PR que figura como mergeado: **no avances**. Avisa al usuario y propón un PR de sincronización hacia `main`.
4. Si hay PRs abiertos de los que depende la tarea, no empieces: avisa cuáles faltan mergear.
5. Toda rama nueva sale de `main` actualizado: `git checkout main && git pull origin main && git checkout -b <rama>`.
6. Evita los PRs apilados (base distinta de `main`). Si no queda otra, antes de mergear el siguiente cambia su base a `main` (`gh pr edit <n> --base main`) y vuelve a comprobar el diff.

## Dependencias entre tareas (regla obligatoria)

**No empieces una tarea si alguna de sus dependencias (`Depende de`) no está en estado `Hecho`.**

Antes de trabajar en una tarea `PUL-XX`:
1. Busca la fila en el Excel y revisa la columna `Depende de`.
2. Verifica que cada dependencia esté `Hecho` **y** que su código ya esté mergeado en `main`.
3. Si alguna dependencia está `Pendiente`, `En curso` o `Bloqueado`: **detente**, no implementes ni “adelantes” la tarea,
   y avisa al usuario qué tarea la bloquea y quién es el responsable.
4. Tareas `Recortado` o `Won't` (PUL-26, PUL-27) no se implementan.
5. No mezcles varias tareas en una misma rama/PR: una tarea = una rama = un PR.

Grafo de dependencias (referencia rápida; si difiere del Excel, manda el Excel):

| Tarea | Resp. | Rama | Depende de |
|---|---|---|---|
| PUL-01 repo + estructura | A | main | — |
| PUL-02 modelo `Evaluacion` + mock | B | feat/data-schema | PUL-01 |
| PUL-03 requirements + .env | C | chore/setup-env | PUL-01 |
| PUL-04 PDF → texto | A | feat/extraction-pdf-reader | PUL-03 |
| PUL-05 prompt extracción LLM | A | feat/extraction-llm-parser | PUL-02, PUL-04 |
| PUL-06 normalizar fechas/tipo | A | feat/extraction-normalize | PUL-05 |
| PUL-07 lote + cohorte.json | A | feat/extraction-batch | PUL-06 |
| PUL-08 propuesta LLM coordinador | A | feat/extraction-proposal | PUL-12 |
| PUL-09 índice de carga | B | feat/engine-load-index | PUL-02 |
| PUL-10 detector de colisiones | B | feat/engine-collisions | PUL-09 |
| PUL-11 modelo CP-SAT | B | feat/optimizer-cpsat-model | PUL-09 |
| PUL-12 función objetivo + diff | B | feat/optimizer-objective | PUL-11 |
| PUL-13 simulador docente | B | feat/optimizer-simulator | PUL-10 |
| PUL-14 layout FastAPI + deploy Vercel | C | feat/ui-base | PUL-02 |
| PUL-15 vista carga semanal | C | feat/ui-load-view | PUL-14 |
| PUL-16 vista antes/después | C | feat/ui-before-after | PUL-14 |
| PUL-17 integración real | C | feat/ui-integration | PUL-07, PUL-12 |
| PUL-18 UI simulador | C | feat/ui-simulator | PUL-13 |
| PUL-19 checkpoint #1 | Todos | main | PUL-05, PUL-10, PUL-15 |
| PUL-20 congelar alcance | Todos | — | PUL-17 |
| PUL-21 tests mínimos | B | test/core | PUL-12 |
| PUL-22 README final | A | docs/readme | PUL-17 |
| PUL-23 diapositivas | B | — | PUL-12 |
| PUL-24 video demo | C | — | PUL-18 |
| PUL-25 tag v1.0-freeze | A | main | PUL-22, PUL-23, PUL-24 |

## Estructura y propiedad de carpetas

```
data/silabos/            PDFs de prueba
data/mock/evaluaciones_mock.json
src/models.py            esquema Evaluacion (compartido)
src/extraction/          A
src/engine/  src/optimizer/   B
src/app.py               C (entrypoint FastAPI / Vercel)
src/ui/                  C (templates/, static/)
vercel.json              C
tests/
```

Cada tarea toca solo la carpeta de su módulo. Si necesitas cambiar `src/models.py` u otra carpeta ajena, avísalo al usuario antes.

## Ramas y commits

- `main` siempre demostrable; solo recibe código vía PR.
- Ramas: `feat/<módulo>-<desc>`, `fix/<módulo>-<desc>`, `docs/<desc>`, `test/<desc>`, `chore/<desc>`. Usa el nombre exacto de la columna `Rama` del Excel.
- Conventional Commits en español e imperativo: `tipo(scope): descripción`.
  Tipos: feat, fix, refactor, docs, test, chore, style. Scopes: extraction · engine · optimizer · ui · data · setup · readme.
- Commits pequeños cada 30–45 min. Nunca subir `.env` ni API keys (usar `.env.example` con valores vacíos).
- Code freeze 16:00 exacto. 15:50: commit final + `git tag v1.0-freeze` + push.

## Pull Requests

1. Una PR por tarea del backlog, desde su rama hacia `main`.
2. Antes de abrirla: `git pull origin main` en la rama, resolver conflictos y verificar que la app/código corre.
3. Título: `PUL-XX tipo(scope): descripción` — ej. `PUL-11 feat(optimizer): modelo CP-SAT con fechas bloqueadas`.
4. Cuerpo: usar la plantilla de abajo (también en `.github/pull_request_template.md`). Siempre completa las dependencias y el DoD.
5. No abras la PR si alguna dependencia no está `Hecho` y mergeada en `main` (ver "Estado de los PRs y de `main`").
   La base del PR siempre es `main`.
6. Merge a `main` solo en checkpoints (11:00, 12:40, 15:30) o con aviso al equipo. Quien mergea avisa en el chat.
7. Nunca incluir el Excel, `.env`, claves ni archivos generados grandes.
8. Usa `gh pr create` para crearla; no la mergees sin que el usuario lo pida.

### Plantilla de PR

```markdown
## Tarea
PUL-XX — <nombre de la tarea del backlog>

## Dependencias
- [ ] PUL-YY — Hecho y mergeado en main
- (o "Ninguna")

## Qué cambia
- ...

## Criterio de aceptación (DoD)
<copiar el DoD del Excel>
- [ ] Cumplido

## Cómo probar
```bash
# comandos para verificar
```

## Checklist
- [ ] `git pull origin main` hecho y sin conflictos
- [ ] La app / el código corre localmente (y el preview de Vercel funciona)
- [ ] Solo toqué la carpeta de mi módulo (o lo avisé)
- [ ] Sin `.env`, API keys ni el Excel de planificación
- [ ] Commits en formato Conventional Commits

## Rúbrica
<Funcionamiento / Problema e impacto / Innovación / Calidad técnica / Pitch>
```
