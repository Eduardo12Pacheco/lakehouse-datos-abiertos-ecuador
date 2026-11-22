# ADR 0001 — Python 3.12, DuckDB y dbt como stack analítico

## Estado

Aceptada (2026-11-19). Refinada por el ADR 0003 (EL en Python, T en dbt) y el ADR 0006
(runner de DAG propio en lugar de Dagster).

## Contexto

El lakehouse debe instalarse como un único paquete de Python (nivel de instalación L1),
ejecutarse por completo sin conexión desde una muestra incluida, no requerir cuenta ni
servidor y, aun así, parecerse a una plataforma real de ingeniería analítica y no a un
notebook. El conjunto de datos completo tiene unos siete millones de filas entre la
recaudación de impuestos del SRI, el IPC del INEC y las cuentas nacionales del BCE. La
máquina es una laptop de desarrollo (Linux, pero Windows y macOS también deben funcionar), y
el mismo código participa en una matriz de CI de tres sistemas operativos.

La capa de transformación es un entregable de primera clase: modelos de staging, intermedios
y marts, contratos, pruebas de datos, pruebas unitarias, documentación de linaje y cargas
incrementales. Escribir esa capa como código Python artesanal demostraría mal las habilidades
en SQL y convertiría cada cambio de modelado en código de aplicación.

## Decisión

- Python 3.12, `uv` para resolución y bloqueo, `hatchling` como backend de build, layout
  `src/`, distribución `ecuador-open-data-lakehouse`, paquete de importación
  `ecuador_lakehouse` y script de consola `lakehouse`.
- DuckDB (2.x) como warehouse de un solo archivo en `$LAKEHOUSE_HOME/warehouse.duckdb`, con
  los esquemas `raw`, `staging`, `intermediate`, `marts` y `meta`.
- dbt-core 1.12 y dbt-duckdb 1.11, invocados en el mismo proceso mediante
  `dbt.cli.main.dbtRunner`, de modo que el wheel instalado sea el dueño del proyecto, los
  profiles y las rutas de destino. El proyecto dbt se copia desde los recursos del paquete a
  `$LAKEHOUSE_HOME/dbt/project` antes de cada ejecución.
- Python es responsable de la extracción y de la decodificación estructural; dbt es
  responsable del tipado, la limpieza, las claves, los modelos de esquema estrella y las
  pruebas (ADR 0003).
- La conexión al warehouse se cierra antes de que arranque dbt, porque DuckDB admite un solo
  escritor por archivo de base de datos.

## Consecuencias

- Un solo proceso, sin servicios que iniciar: `lakehouse build` es suficiente.
- DuckDB ofrece rendimiento analítico columnar y un SQL que sería doloroso en SQLite, mientras
  el wheel sigue siendo un paquete normal de Python.
- La regla de un solo escritor limita la concurrencia. Se maneja abriendo el warehouse solo en
  la fase EL y cerrándolo antes de dbt, y manteniendo cuatro hilos de dbt.
- Un entorno de dbt ocupa unos 350 MB instalado; se acepta para L1 porque la tarea requiere un
  framework de transformación real.
- Se requieren rutas absolutas para `--project-dir`, `--profiles-dir`, `--target-path` y
  `--log-path` de dbt; los artefactos y los logs permanecen bajo `$LAKEHOUSE_HOME`, nunca en el
  repositorio.
- El artefacto publicado puede incorporar DuckDB y Parquet sin ningún servicio externo, y los
  valores de `content_sha256` siguen siendo reproducibles (ADR 0007).

## Alternativas consideradas

- **PostgreSQL**: requiere un servicio y credenciales, lo que contradice L1 y la restricción de
  cero servidores.
- **Apache Spark**: JVM, descargas grandes, semántica orientada a clústeres y demasiado pesado
  para una demo en una laptop.
- **Notebooks con pandas/Polars**: rápidos de escribir, pero la capa de transformación dejaría
  de ser SQL, no produciría un manifest de dbt y no admitiría pruebas de datos y unitarias de
  dbt ni documentación de linaje.
- **SQLite**: embebido y simple, pero con SQL analítico débil, sin escaneos columnares y sin un
  adaptador idiomático de dbt con soporte de contratos.
- **Warehouse en la nube (BigQuery/Snowflake)**: cuentas, claves, costo y dependencias de red;
  excluido por los estándares del proyecto.
