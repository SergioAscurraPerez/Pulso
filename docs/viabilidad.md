# Viabilidad y stakeholders de PULSO (USMP · FIA)

Pulso se piensa para la **Facultad de Ingeniería y Arquitectura (FIA) de la USMP**, de donde son el equipo y los sílabos de prueba.
Este documento responde a la pregunta del jurado/mentores: **¿se puede aplicar de verdad?** y **¿quiénes intervienen?**

## 1. Resumen

| Pregunta | Respuesta | Base |
|---|---|---|
| ¿Se pueden cambiar las fechas de las evaluaciones? | **Sí, dentro de reglas.** Parciales y finales los programa el **Director del Departamento Académico** con aprobación del decano, al inicio del semestre; el resto de evaluaciones (PC, laboratorios, trabajos) quedan **a criterio del docente**. | Reglamento de Evaluación del Aprendizaje, art. 7 |
| ¿Qué NO se puede cambiar? | El **tipo y número** de evaluaciones del sílabo no se modifica durante el semestre. | Art. 6 |
| ¿Qué pasa hoy con los choques? | Solo se atienden **después**, alumno por alumno, y solo si coinciden **día y hora**: el profesor del curso de nivel superior, con autorización del Director de Escuela, toma la prueba otro día dentro de 72 h. | Art. 20 |
| ¿Cuándo se definen las fechas de examen? | En 2026-I figuran como **"Por definir"**, responsables: **Departamento Académico y Coordinación Académica**. Clases del 02/03/2026; fin de semestre 27/06/2026. | Calendario FIA 2026-I (ed. 01, 24/11/2025) |

**Conclusión: es viable.** Pulso no cambia nada que el reglamento prohíba: **solo propone fechas**, nunca el tipo, número ni peso de las evaluaciones (art. 6).
Llega en el momento en que la universidad ya decide fechas (inicio de semestre, art. 7) y convierte una corrección reactiva y caso por caso (art. 20) en una **planificación preventiva para toda la cohorte**.

## 2. Marco normativo (USMP)

Reglamento de Evaluación del Aprendizaje, actualizado al 01/09/2015:

- **Art. 6.** El sílabo indica "el tipo y el número de evaluaciones"; "esos procedimientos no podrán ser modificados a lo largo del período lectivo".
  → Pulso nunca toca tipo, número ni pesos; solo fechas.
- **Art. 7.** "El director del departamento académico o quien haga sus veces, con aprobación del decano […], al inicio del semestre […], deberá programar el calendario de exámenes parciales, exámenes finales y de aplazados". "No se programarán dentro de este calendario todas las demás evaluaciones […], las que quedarán a criterio del docente."
  → Dos usuarios con poder de decisión: el **departamento** (exámenes) y cada **docente** (lo demás).
- **Art. 16.** Si el profesor no asiste, la nueva fecha va en la semana posterior a la época de exámenes.
- **Art. 18 y 25.** Rendir en otra fecha (rezagados) exige causa justificada y autorización (Director del Departamento / Director de Escuela), pedida en 48 h.
- **Art. 20.** Coincidencia de día y hora de exámenes de distintas asignaturas: el alumno puede rendir la de nivel superior otro día, dentro de 72 h, con autorización del Director de Escuela.
  → El reglamento ya reconoce el problema, pero solo el choque exacto y a pedido del alumno. **Tres evaluaciones fuertes en 72 h no tienen ningún mecanismo**: eso es lo que Pulso detecta.

Calendario de actividades FIA 2026-I (ed. 01, publicado 24/11/2025):

- Inicio de clases: **02/03/2026**. Fin del semestre: **27/06/2026** (17 semanas). Entrega de actas: 24–26/06/2026.
- Exámenes parcial y final: **"Por definir"**; responsables: **Dpto. Académico y Coordinación Académica**.
- Matrícula de regulares **"por horarios, según promedio semestral"** (prioridad por rendimiento).

Otros reglamentos FIA citados en su web: Reglamento de Registros Académicos (art. 8 "De la distribución de aulas", art. 72 "Del cambio de turno o aula").

## 3. Stakeholders

| Actor | Qué decide hoy | Qué le duele | Qué le da Pulso |
|---|---|---|---|
| **Estudiante** | Nada sobre fechas; elige horario en la matrícula según su promedio | Semanas con varias evaluaciones fuertes; solo puede pedir excepción si el choque es exacto (art. 20) | Ve su carga semanal y las colisiones con anticipación |
| **Docente** | Fechas de PC, laboratorios y trabajos (art. 7) | No ve las fechas de los otros cursos de la misma cohorte | **Simulador**: antes de fijar una fecha, % de sus alumnos que chocarían y mejor fecha alternativa |
| **Director del Departamento Académico** | Calendario de parciales y finales al inicio del semestre (art. 7) | Arma el calendario sin una medida de la carga real de cada cohorte | Calendario optimizado (CP-SAT) con reducción del pico y diff de cambios |
| **Coordinación Académica (FIA)** | Responsable, con el departamento, de los exámenes en el calendario 2026-I | Coordinar a muchos docentes y cursos | **Propuesta redactada** con datos para enviar a los docentes |
| **Director de Escuela** | Autoriza excepciones por choque (art. 20) y rezagados (art. 25) | Atiende casos uno por uno, tarde | Menos solicitudes: los choques se evitan antes de que ocurran |
| **Decano** | Aprueba el calendario de exámenes (art. 7) | — | Indicadores de carga por cohorte para aprobar con datos |
| **Oficina de Registros Académicos** | Matrícula por horarios, distribución de aulas (Reg. Registros, art. 8 y 72) | — | (Futuro) matrícula y aulas: ver §5 |

## 4. Cómo encaja en el proceso real

1. **Antes del inicio de clases**: la coordinación carga los sílabos de cada ciclo → Pulso extrae las evaluaciones y mide la carga.
2. **Programación del calendario de exámenes (art. 7)**: el Director del Departamento usa el optimizador; las fechas que la facultad fija se marcan como **bloqueadas** y Pulso no las mueve.
3. **Durante el semestre**: cada docente usa el **simulador** antes de fijar PC, laboratorios o trabajos (su decisión, art. 7).
4. **Resultado**: menos coincidencias que terminan en excepciones del art. 20 o rezagados del art. 25.

## 5. Siguientes pasos sugeridos por los mentores

- **Sílabo + horario personal**: el horario del alumno da el día y hora real de cada curso (hoy Pulso lo estima) y su combinación exacta de cursos.
- **Matrícula**: la matrícula es "por horarios, según promedio"; con los grupos de matrícula reales, la carga se mide por combinación de cursos (el modelo ya soporta `Cohorte.grupos`).
- **Balanceador de salones**: con el n.º de alumnos por sección y la capacidad de las aulas, distribuir los exámenes en aulas (Reg. de Registros Académicos, art. 8).

## 6. Riesgos y supuestos

- El reglamento consultado es la versión **actualizada al 01/09/2015** (copia publicada por la Facultad de Ciencias Contables, Económicas y Financieras); falta confirmar si hay una versión posterior vigente para la FIA.
- El calendario FIA 2026-I es la **edición 01** y dice "sujeto a cambios".
- Los sílabos no siempre indican la semana de cada evaluación (p. ej. P1–P4); Pulso las **estima y lo advierte**.
- El día de la semana de cada evaluación se estima por curso hasta tener el horario real (§5).

## Fuentes

- Reglamento de Evaluación del Aprendizaje USMP (actualizado al 01/09/2015): https://fcctp.usmp.edu.pe/documentos/transparencia/2022/reglamento_evaluacion_aprendizaje.pdf (también en https://usmp.edu.pe/pdf/reglamentos/reglamentoevaluacionaprendizaje.pdf)
- Calendario de actividades FIA 2026-I, edición 01 (24/11/2025): https://fia.usmp.edu.pe/wp-content/uploads/2025/11/CALENDARIO-DE-ACTIVIDADES-2026-I_edicion-01-1.pdf
- Reglamentos generales FIA: https://fia.usmp.edu.pe/reglamento/
