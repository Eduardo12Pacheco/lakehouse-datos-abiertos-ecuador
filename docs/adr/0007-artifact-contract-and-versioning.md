# ADR 0007 - Artefacto publicado, versionado del contrato y determinismo

## Estado

Aceptada (2026-11-20, tarea T11).

## Contexto

El lakehouse debe entregar un producto de datos estable a otros proyectos. Los consumidores
necesitan saber en qué tablas, columnas y tipos pueden confiar, deben poder verificar que un
artefacto descargado está íntegro y deben poder razonar sobre la compatibilidad cuando el producto
de datos evoluciona. Al mismo tiempo, dos builds con las mismas entradas deben producir contenidos
de tabla idénticos para que los artefactos publicados puedan compararse byte a byte a nivel lógico
(S14, S15, D19).

Los archivos de base de datos DuckDB y los archivos Parquet incorporan metadatos específicos del
build y no son reproducibles byte a byte, así que los hashes de archivo no pueden servir como huella
digital de determinismo. Las marcas de tiempo del reloj en los marts tendrían el mismo problema: harían
que cada build difiriera por razones no relacionadas con los datos.

## Decisión

1. **Estructura del artefacto.** `lakehouse publish --out DIR` escribe
   `DIR/ecuador-lakehouse-<artifact_version>/` con un archivo DuckDB que contiene solo los esquemas
   `marts` y `meta`, un archivo Parquet ZSTD por tabla publicada, un `manifest.json` determinista, un
   archivo `SHA256SUMS` y `ATTRIBUTION.md`.
2. **Huella digital lógica.** Cada tabla tiene un `content_sha256`: el SHA-256 de los bytes producidos
   por `COPY (SELECT * FROM <table> ORDER BY ALL) TO <file> (FORMAT CSV)`. Esto normaliza el orden de
   las filas e ignora los metadatos de archivo, de modo que es estable entre dos builds con los mismos
   datos.
3. **Sin reloj en el producto de datos.** Los marts no contienen marcas de tiempo y el manifest no
   contiene fechas de build. La única hora de build vive en `meta.build_info`, dentro del archivo DuckDB
   publicado, y queda excluida de todo `content_sha256` y de `SHA256SUMS`.
4. **Dos versiones.** La versión del paquete describe el software; la versión del artefacto iguala la
   versión del contrato y describe el producto de datos. Evolucionan de forma independiente (una
   corrección puede publicarse como una versión de parche sin cambiar el contrato de datos).
5. **Contrato versionado.** `artifact_contract.json` enumera cada tabla publicada con su tipo, su grano
   y sus columnas tipadas. `lakehouse contract check` lee el esquema realmente materializado en el
   warehouse y lo compara con el contrato versionado: una tabla o columna eliminada, o un tipo cambiado,
   es un cambio incompatible que requiere un incremento MAJOR; una tabla o columna agregada es aditiva y
   requiere un incremento MINOR. Una corrección pura requiere un incremento PATCH.
6. **Verificación.** `lakehouse verify DIR` vuelve a parsear el manifest, comprueba cada entrada de
   `SHA256SUMS`, recalcula la huella lógica de cada tabla a partir del archivo DuckDB del artefacto,
   compara los conteos de filas y los esquemas del manifest, DuckDB y Parquet, y termina con código 8
   ante cualquier discrepancia.

## Consecuencias

- Los consumidores pueden fijar `artifact_version` y usar el manifest para descubrir tablas, granos y
  tipos de columna sin abrir la base de datos.
- La manipulación de un archivo Parquet, del archivo DuckDB o del manifest, o la eliminación de un
  archivo, se detecta y se traduce en código de salida 8.
- Agregar una columna obliga a un incremento MINOR de la versión y eleva la versión del artefacto
  publicado; cambiar un tipo o eliminar cualquier elemento obliga a un incremento MAJOR.
- La publicación no es idéntica a nivel de archivo, pero dos builds de la muestra producen valores
  `content_sha256` iguales para las 14 tablas, que es la garantía de determinismo que anuncia el
  proyecto.
- El contrato no cubre intencionalmente los modelos de staging ni intermediate: solo los marts son una
  interfaz pública.

## Alternativas consideradas

- **Calcular el hash de los archivos `.duckdb` y Parquet para lograr determinismo.** Rechazado: ambos
  formatos incorporan metadatos que cambian entre ejecuciones aunque los datos sean idénticos.
- **Usar versiones de modelos dbt en lugar de un contrato versionado.** Rechazado: las versiones de dbt
  describen interfaces de modelos dentro del proyecto, no el artefacto publicado que consumen los
  repositorios hermanos.
- **Publicar un único directorio Parquet sin DuckDB.** Rechazado: DuckDB ofrece a los consumidores joins
  y SQL sobre todo el producto con una sola dependencia, y los archivos Parquet por tabla mantienen barato
  el consumo parcial.
