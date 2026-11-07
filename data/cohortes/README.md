# Cohortes por ciclo — para "Comparar ciclos"

Cada `ciclo-NN.json` es la cohorte de un ciclo de la carrera, extraída de sus sílabos en
`data/silabos/ciclo-NN/`. La app los registra solos: aparecen en **Comparar ciclos** y en el
selector de datos de todas las vistas. El ciclo 7 es `data/cohorte.json` (no se duplica aquí).

Hoy hay un ciclo además del 7:

| Archivo | Periodo | Lunes de la semana 1 | Cursos | Evaluaciones |
|---|---|---|---|---|
| `ciclo-06.json` | 2025-II | 2025-08-18 | 5 | 35 |

**La fecha de inicio es de referencia.** Los sílabos no traen la fecha de inicio del semestre,
así que se usó la regla con la que cae el ciclo 7 real (2026-I empieza el primer lunes de marzo):
semestre I = primer lunes de marzo, semestre II = tercer lunes de agosto. Las métricas por semana
(carga, colisiones de 72 h) no dependen de la fecha exacta; solo las fechas que se muestran.

## Agregar o regenerar un ciclo

La extracción de cada PDF queda en `data/cache/extraccion/`: regenerar un ciclo ya extraído
(por ejemplo, con la fecha oficial) **no llama al LLM** y es instantáneo.

```bash
python scripts/procesar_cohorte.py data/silabos/ciclo-06 --ciclo 2025-II --inicio 2025-08-18 --salida data/cohortes/ciclo-06.json
```

Para otro ciclo, cambia la carpeta, el periodo y el lunes de inicio (referencia: 2023-I 2023-03-06,
2023-II 2023-08-21, 2024-I 2024-03-04, 2024-II 2024-08-19, 2025-I 2025-03-03) y commitea el JSON
y los archivos nuevos de `data/cache/extraccion/`. Si la key de OpenRouter no tiene saldo, el modelo
gratuito `nvidia/nemotron-3.5-super-vl:free` funciona con `LLM_MAX_TOKENS=20000` (≈90 s por sílabo).

## Cómo se extrajo el ciclo 6 (2026-11-07)

- Ingeniería de Costos, Ingeniería de Software I e Investigación Operativa I: `google/gemini-3.8-flash`.
- Programación I y Teoría General de Sistemas: `nvidia/nemotron-3.5-super-vl:free`.

Cada extracción pasa la validación de PULSO (esquema de `Evaluacion` y pesos del curso que suman
~100 %). Revisión: los 5 cursos suman 100 % y todas las fechas caen dentro del semestre.
