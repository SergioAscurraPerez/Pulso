# Pulso

**Radar predictivo de sobrecarga académica.** Hackathon ENEISOFT XVI (FISI-UNMSM), sub-eje Bienestar.

## Problema

Las evaluaciones de los cursos de un mismo ciclo se programan por separado, así que los estudiantes de una cohorte
terminan con varios exámenes y entregas fuertes en la misma semana.

## Solución

1. **Extracción con IA:** lee los sílabos en PDF y extrae cada evaluación (curso, tipo, fecha, peso).
2. **Motor de carga:** calcula la carga semanal de la cohorte y detecta colisiones (≥3 evaluaciones fuertes en 72 h).
3. **Optimizador CP-SAT:** propone una reprogramación que baja el pico de carga respetando las fechas bloqueadas.
4. **Simulador docente:** antes de fijar una fecha, muestra el riesgo de colisión y una fecha alternativa.

## Estructura

```
data/silabos/                 PDFs de sílabos de prueba
data/mock/                    datos mock (evaluaciones_mock.json)
src/models.py                 esquema Evaluacion (Pydantic)
src/extraction/               extracción con IA
src/engine/                   índice de carga y colisiones
src/optimizer/                modelo CP-SAT y simulador
src/app.py                    entrypoint FastAPI (Vercel)
src/ui/templates, src/ui/static   interfaz web
tests/
```

## Ejecutar

> En construcción: los pasos se completan con la configuración del entorno (`requirements.txt`) y la app FastAPI.

```bash
cp .env.example .env    # completar LLM_API_KEY
pip install -r requirements.txt
uvicorn src.app:app --reload
```

## Despliegue

Monolito FastAPI desplegado en Vercel.
