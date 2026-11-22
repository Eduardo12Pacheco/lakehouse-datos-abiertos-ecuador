# ADR 0006 — Un runner de DAG propio en lugar de Dagster/Airflow

## Estado

Aceptada (2026-11-20).

## Contexto

El proyecto necesita un pipeline reproducible que ejecute `acquire -> load_raw -> transform ->
quality -> docs -> report` desde un único comando de la CLI, admita re-ejecuciones parciales,
reintente la adquisición idempotente, se detenga antes de los pasos posteriores cuando un paso
falla y registre lo ocurrido en `meta.runs` (S13, D6). El pipeline tiene seis pasos, un proceso,
un archivo DuckDB local y no tiene requisitos de programación.

Las alternativas obvias son:

1. **Dagster**: modelo de assets/materializaciones, reintentos, historial de ejecuciones y una UI
   web. La versión 1.13.31 trae grpcio, SQLAlchemy, Alembic y un daemon, y su uso normal supone una
   instancia persistente y un servicio web.
2. **Airflow**: planificador maduro, pero requiere un planificador, una base de datos de metadatos,
   un webserver y un executor incluso para un único DAG local.
3. **Un DAG mínimo en Python puro**: un grafo validado más un bucle que ejecuta callables, con el
   ledger de ejecuciones guardado en el mismo archivo DuckDB.

Los estándares exigen una instalación L1 local-first (`uv tool install`, sin Docker ni servidor), y
el plan declara explícitamente que el orquestador es un no-objetivo para servicios externos
(Contexto: "sin servicio orquestador — ver ADR 0006").

## Decisión

- **Mantener el orquestador propio y pequeño.** `domain.dag.Dag` valida pasos duplicados,
  dependencias desconocidas y ciclos en el momento de la construcción, y devuelve un orden
  topológico determinista (empates en orden alfabético). `application.pipeline.PipelineRunner`
  ejecuta callables registrados, admite `--select` (el paso más sus dependencias transitivas),
  `--only` (un paso) y `--from-step` (el paso más los posteriores), se detiene en el primer fallo y
  registra una fila en `meta.runs` por invocación, con estado por paso, duración, intentos, detalle
  y métricas numéricas como JSON compacto.
- **Los reintentos son opcionales y la idempotencia se verifica.** Solo los pasos declarados
  idempotentes pueden recibir una `RetryPolicy`; el runner rechaza una política para cualquier otro
  paso en el momento de la construcción. Hoy solo se reintenta `acquire`, porque volver a descargar
  un archivo verificado es seguro, mientras que una carga o una ejecución de dbt aplicadas
  parcialmente no se repiten a ciegas.
- **Los pasos son callables planos de la aplicación, cableados por la raíz de composición.** El
  runner no sabe nada de DuckDB, dbt ni HTTP. `container.py` selecciona la estrategia de descarga
  según el modo, arma los seis pasos y pasa el warehouse como repositorio del ledger de ejecuciones.
  Un wrapper de Dagster solo tendría que invocar los mismos callables.
- **El ledger de ejecuciones vive en `meta.runs`.** Una fila por ejecución (inicio/fin, estado, modo,
  JSON de pasos) se escribe al final de la ejecución, incluidas las fallidas, de modo que el estado
  del último build se puede inspeccionar con SQL simple y mostrarse en la UI del reporte sin
  infraestructura externa.
- **dbt obtiene acceso exclusivo al warehouse.** Los pasos de transform, quality y docs cierran la
  conexión de la aplicación antes de invocar dbt y la reabren después (D18). El paso de reporte
  lee luego el ledger a través de la conexión reabierta.

## Consecuencias

- Positivo: cero servicios adicionales, sin daemon, sin base de datos de metadatos; la instalación
  sigue en unos 350 MB, dominados por dbt; el pipeline funciona sin conexión y en Windows.
- Positivo: el orden, la selección y el comportamiento de reintentos tienen pruebas unitarias sobre
  el `Dag` real, y `meta.runs` lo verifican pruebas de integración.
- Positivo: reemplazar el runner por Dagster en el futuro significa implementar los mismos seis
  callables como assets; ninguna lógica de dominio o de adaptadores queda atrapada en el runner.
- Negativo: no hay UI, planificador, alertas ni ejecución distribuida. El proyecto es, por diseño, un
  lakehouse batch local; la programación (cron, GitHub Actions) queda fuera de alcance.
- Negativo: el runner es código nuestro que debemos mantener. Su superficie es intencionalmente
  pequeña (un módulo más el DAG puro) y está cubierta por pruebas unitarias y pruebas de propiedades
  sobre el orden y los ciclos del grafo.

## Alternativas consideradas

- **Dagster**: modelo de assets, reintentos y una UI, pero arrastra grpcio, SQLAlchemy, Alembic y un
  daemon, y espera una instancia persistente; rechazado para una CLI L1 de un solo proceso.
- **Airflow**: planificador maduro, pero necesita planificador, base de datos de metadatos,
  webserver y executor para un único DAG local; rechazado por desproporcionado.
- **Un cron job o un script de shell**: sin grafo tipado, sin detección de ciclos, sin ledger de
  ejecuciones y sin selección parcial; rechazado porque esas son especificaciones explícitas.
