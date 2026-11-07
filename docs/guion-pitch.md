# Guion del pitch y de la demo — PULSO · SpookyTech

Formato del evento: **5 min de pitch + 5 min de preguntas**. El pitch son 6 láminas cortas (≈3 min) y una demo en vivo (≈2 min).
Lenguaje **no técnico**: no se dice "LLM", "CP-SAT" ni "API" salvo que el jurado pregunte.

Voces: **Voz 1**, **Voz 2** y **Voz 3**. Repártanlas según quién habla mejor. Sugerencia: Voz 1 abre y cierra, Voz 2 cuenta el problema, Voz 3 hace la demo.

---

## 1. Pitch (láminas) — 3:00

### Lámina 1 · Portada — 0:00–0:10 · Voz 1
> Buenas tardes. Somos SpookyTech, de la USMP.

### Lámina 2 · "Mi sistema es…" — 0:10–0:45 · Voz 1
> **Mi sistema es PULSO**, un radar que lee los sílabos y mide la carga académica de cada semana.
> **Va a ayudar a** la coordinación y a los docentes a repartir las evaluaciones para que ningún estudiante tenga tres exámenes fuertes en 72 horas.
>
> ¿Por qué la coordinación? Porque al inicio de cada semestre son ellos, junto con el departamento, los que programan los exámenes, y cada docente pone sus prácticas.
> Lo hacen con buena intención, pero **nadie ve la semana completa del estudiante**.

### Lámina 3 · El problema — 0:45–1:30 · Voz 2
> Esto no es un ejemplo inventado. Son los **sílabos reales del ciclo 7** de nuestra carrera, semestre 2026-I.
> Miren la semana 8: **los seis cursos toman su parcial en la misma semana**. Y en la 16, lo mismo con los finales.
> Encontramos **tres momentos** en que un alumno tiene tres o más evaluaciones fuertes en 72 horas.
> El estudiante se entera cuando ya está encima… y ahí ya no hay nada que hacer.

### Lámina 4 · La solución — 1:30–2:05 · Voz 2
> PULSO hace cuatro cosas:
> **Lee** los sílabos y saca cada evaluación con su semana y su peso.
> **Mide** la carga de cada semana y marca los choques.
> **Optimiza**: busca el cambio de fechas más pequeño posible para bajar el pico, sin tocar lo que la facultad fija.
> Y **propone**: le entrega a la coordinación una propuesta lista para enviar, y al docente un simulador antes de fijar una fecha.

### Lámina 5 · Viabilidad — 2:05–2:40 · Voz 3
> ¿Se puede hacer de verdad? Lo revisamos en el **reglamento de evaluación de la USMP**.
> El **artículo 7** dice que parciales y finales los programa el departamento al inicio del semestre, y que las demás evaluaciones las decide cada docente. Esos son nuestros usuarios.
> El **artículo 6** dice que no se puede cambiar el tipo ni el número de evaluaciones. Por eso PULSO **solo mueve fechas**.
> Y el **artículo 20** muestra el vacío: hoy solo se atiende un choque exacto de día y hora, después de que pasa. **PULSO lo previene.**

### Lámina 6 · Impacto — 2:40–3:00 · Voz 1
> Para el estudiante: menos semanas imposibles. Para el docente: saber antes de fijar una fecha cuántos de sus alumnos chocarían. Para la coordinación: una propuesta lista, con datos.
> **Ahora, veámoslo funcionar.**

---

## 2. Demo en vivo — 3:00–4:50 · Voz 3 maneja, Voz 2 narra

Antes de empezar, tener la app abierta en la pestaña **Cohorte** con **"Cohorte extraída de los sílabos"** ya elegida en el selector **Datos** (botón **Cargar**).

| # | Pantalla y acción | Qué decir |
|---|---|---|
| 1 | **Cohorte** (ya abierta) | "Estos son los seis sílabos reales del ciclo 7. PULSO los leyó y encontró **38 evaluaciones**, cada una con su fecha y su peso en la nota." |
| 2 | Clic en **Carga semanal** | "Cada columna es una semana del ciclo; mientras más intensa, más carga. Ahí está la semana 8, la de parciales, y la 16, la de finales." |
| 3 | Clic en **Antes / después** | "Le pedimos a PULSO que reparta mejor. Moviendo **solo 4 evaluaciones**, las colisiones bajan de **3 a 1** y el pico baja un 13 %. Sin cambiar ningún examen de tipo ni de peso." |
| 4 | Señalar la colisión que queda | "La que queda son los parciales: esa semana la fija la facultad, y PULSO no la toca. Lo que sí hace es mostrarlo con datos, para que se programe distinto el próximo semestre." |
| 5 | En **Evaluaciones movidas**, pulsar **Rechazar** en el *Examen final* de **Arquitectura de Software** | "La coordinación siempre tiene la última palabra. Supongamos que el final de Arquitectura no se puede mover: lo rechazo… y PULSO recalcula al instante. Ahora mueve el final de Liderazgo y Oratoria, y las colisiones siguen bajando de 3 a 1." |
| 5b | Bajar hasta **"Propuesta para el coordinador"** (dice *Borrador · pendiente de aprobación*) → **Aprobar propuesta** → **Descargar propuesta** | "Y esto es lo que recibe la coordinación: una propuesta redactada con sus decisiones. Nada se envía a los docentes hasta que la coordinación la aprueba." |
| 6 | Clic en **Simulador docente** → en **Evaluación** elegir **"Práctica Calificada 4 (12/06)"** de Inteligencia Artificial → **Fecha** 12/06/2026 → **Simular** | "Ahora pónganse en el lugar de la profesora de Inteligencia Artificial. Quiere tomar su práctica el viernes 12 de junio…" |
| 7 | Ver el resultado: **100 %** y **Fecha sugerida: vie 05/06/2026, 0 %** | "…PULSO le avisa que **el 100 % de sus alumnos** tendría tres evaluaciones fuertes en 72 horas, porque esa misma semana tienen el trabajo final de Gestión Estratégica y el de Ingeniería de Software II. Y le sugiere el **viernes 5 de junio: 0 %**. Ella decide; PULSO solo le da la información." |
| 8 | (Si sobra tiempo) **Subir sílabos** | "Y cualquier coordinación puede subir los sílabos de su ciclo y obtener todo esto en minutos." |

### Cierre — 4:50–5:00 · Voz 1
> PULSO: que la carga académica se planifique desde el primer día, y no se sufra en la semana 8. Gracias.

### Plan B (si algo falla)
1. Si la URL de Vercel no carga: abrir la app local (`uvicorn src.app:app`) en la laptop de la demo, con los mismos pasos.
2. Si tampoco funciona: reproducir el **video de respaldo** (sección 3) sin pedir disculpas largas: "Les mostramos la grabación de hace una hora."
3. Nunca depender del wifi para la propuesta: con los sílabos del ciclo 7 todo sale guardado y no necesita internet para la IA.

---

## 3. Video de respaldo (≤ 2 min) — PUL-24

Grabación de pantalla con voz en off. Mismo recorrido que la demo, más rápido.

| Tiempo | Imagen | Voz en off |
|---|---|---|
| 0:00–0:10 | Pestaña Cohorte | "PULSO leyó los seis sílabos reales del ciclo 7 de la USMP: 38 evaluaciones." |
| 0:10–0:30 | Carga semanal | "Así se ve el semestre del estudiante. En la semana 8 los seis cursos toman parcial; en la 16, los finales." |
| 0:30–0:55 | Antes / después | "PULSO propone mover solo 4 evaluaciones: las colisiones bajan de 3 a 1, sin cambiar ningún examen de tipo ni de peso." |
| 0:55–1:15 | Propuesta | "La coordinación recibe una propuesta lista para enviar a los docentes." |
| 1:15–1:45 | Simulador → Práctica Calificada 4 de IA | "Antes de fijar su práctica el 12 de junio, la docente ve que el 100 % de sus alumnos chocaría. PULSO le sugiere el 5 de junio: 0 %." |
| 1:45–2:00 | Volver a Carga semanal | "PULSO: la carga académica se planifica desde el primer día." |

---

## 4. Preguntas probables y respuestas cortas

**¿Los docentes realmente moverían sus fechas?**
Las prácticas y trabajos son decisión del docente (reglamento, art. 7). PULSO no obliga: le muestra al docente, antes de fijar la fecha, cuántos de sus alumnos chocarían. Y los parciales y finales los programa el departamento al inicio del semestre: ahí entra la propuesta para la coordinación.

**¿Por qué no usar simplemente ChatGPT?**
Porque un chatbot puede inventar una fecha o saltarse una regla. En PULSO la inteligencia artificial solo **lee** los sílabos y **redacta** la propuesta; las fechas las calcula un optimizador matemático que respeta las reglas siempre (fechas bloqueadas, feriados, semanas de exámenes) y da la mejor solución posible.

**¿Y la privacidad?**
PULSO trabaja con los sílabos, que ya son públicos para el alumno, y con conteos de alumnos por combinación de cursos. No necesita nombres, notas ni datos personales.

**¿Funciona a escala, con toda la facultad?**
Cada sílabo se lee una sola vez y queda guardado. El cálculo de un ciclo completo tarda menos de un segundo. Leer un sílabo nuevo cuesta menos de un centavo, y también funciona con modelos gratuitos.

**¿Qué pasa si el sílabo no dice en qué semana es la evaluación?**
PULSO la estima y la marca como estimada, para que la coordinación sepa qué fechas confirmar con el docente.

**¿Cómo saben que lee bien los sílabos?**
Lo revisamos a mano: en Ingeniería de Software II acertó las 11 evaluaciones con su semana y su peso, calculado desde la fórmula del promedio del sílabo.

**¿Qué sigue?**
Lo que nos recomendaron los mentores: cruzar el sílabo con el **horario personal** de cada alumno, usar los datos reales de **matrícula** y un **balanceador de aulas** para los exámenes.

---

## 5. Checklist antes de subir al escenario

- [ ] Laptop cargada, cargador y adaptador HDMI probados en el auditorio.
- [ ] URL de Vercel abierta en una pestaña y app local corriendo como respaldo.
- [ ] Selector **Datos** en "Cohorte extraída de los sílabos".
- [ ] Video de respaldo descargado en la laptop (sin depender de internet).
- [ ] Diapositivas en PDF abiertas en otra ventana.
- [ ] Ensayo con cronómetro: láminas ≤ 3:00, demo ≤ 2:00.
