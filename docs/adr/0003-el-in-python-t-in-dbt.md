# ADR 0003 — Extracción y carga en Python, transformación en dbt

## Estado

Aceptada (2026-11-20).

## Contexto

Las tres fuentes originales son estructuralmente desordenadas de maneras distintas. El SRI
entrega un archivo `|`-delimitado de 83–109 MB por año, en UTF-8 con BOM hasta 2022 y en cp1252
desde 2023, con decimales por coma y sin un conjunto estable de columnas (`CANTON` falta en los
archivos antiguos). El BCE entrega un archivo cp1252 de 6 MB delimitado por `;`, con separadores
de miles por coma, 176 valores vacíos y montos negativos. El INEC entrega un ZIP anidado en tres
niveles cuyos CSV están pivotados en formato ancho con 120 columnas de meses, mezclan
`1,000000` y `0.224503124`, y contienen filas de título y de pie.

La alternativa de enseñar a dbt a leer directamente cada formato original llevaría la detección
de codificación, el recorrido de archivos anidados y la búsqueda de encabezados a modelos SQL,
donde son difíciles de probar de forma aislada e imposibles de reutilizar para la muestra
publicada. Por el contrario, hacer toda la limpieza en Python duplicaría el tipado, la
generación de claves y las pruebas de datos que dbt ya ofrece, y haría inaccesible la capa de
transformación para los analistas.

## Decisión

- Los adaptadores de Python son responsables únicamente de la **extracción estructural (EL)**:
  decodificar con la política D13, validar el encabezado de origen, recorrer los archivos
  anidados, encontrar la fila de encabezado, despivotar las columnas de meses anchas y escribir
  un CSV canónico en UTF-8 con finales de línea LF. Cada valor de origen se conserva como texto
  crudo en ese CSV.
- dbt es responsable de **todo el tipado, la normalización, la generación de claves y el modelado
  (T)**: conversiones de tipo, separadores decimales, parseo de meses, paridad con
  `normalize_key`, claves sustitutas, dimensiones, hechos, marts, pruebas de datos y pruebas
  unitarias.
- El warehouse carga en bloque cada CSV canónico mediante `read_csv` de DuckDB con
  `all_varchar=true`; los parsers nunca importan DuckDB, dbt ni pandas. Esto mantiene liviana la
  instalación y evita cargar archivos de 100 MB como objetos de Python.
- Los parsers implementan el puerto `SourceParser` (`source_id`, `parse(path, partition,
  output_dir=None) -> ParsedPartition`) y generan `SourceSchemaError` (código de salida 4) ante
  columnas faltantes o desconocidas, un archivo comprimido ilegible o un archivo no decodificable.
  Los encabezados desconocidos se rechazan en lugar de ignorarse en silencio, de modo que un
  cambio en la fuente falla de forma visible.
- El contrato del CSV canónico se fija por fuente y se documenta en los módulos de los parsers;
  es la única interfaz entre EL y T.

## Consecuencias

- Cada particularidad de formato tiene una prueba unitaria pequeña basada en fixtures, sin
  warehouse ni dbt, y el mismo parser alimenta tanto la muestra incluida como el modo `full`.
- dbt sigue siendo el único motor de transformación: los modelos, las pruebas, el linaje y la
  documentación describen toda la lógica de negocio.
- El CSV canónico agrega un archivo temporal por partición (pequeño comparado con los bytes
  originales), pero hace que la carga sea simple, inspeccionable e independiente de la base de
  datos.
- El texto crudo se mantiene crudo hasta llegar a dbt, así que un valor como `-40,290` o una celda
  vacía de CNT se conserva exactamente y los fallos ocurren en una capa SQL probada.
- Un cambio estructural que modifica solo valores (por ejemplo, una provincia nueva) no es un
  error del parser; se detecta después mediante pruebas de relaciones o de valores aceptados. Un
  cambio que modifica columnas falla temprano con código de salida 4.

## Alternativas consideradas

- **Leer los archivos originales directamente desde dbt**: la detección de codificación y los ZIP
  anidados en SQL son frágiles, y dbt-duckdb seguiría necesitando la semántica de `read_csv` de
  Python.
- **Limpieza completa en Python (pandas/Polars)**: contradice D5, agrega una dependencia pesada,
  duplica las pruebas de dbt y debilita el argumento de que "dbt es el motor de transformación".
- **Un parser por formato de archivo usando solo `csv.DictReader` de Python**: no maneja los ZIP
  anidados del INEC ni el cambio de encabezados del SRI, así que los adaptadores siguen necesitando
  validación explícita de encabezados y manejo de archivos comprimidos.
