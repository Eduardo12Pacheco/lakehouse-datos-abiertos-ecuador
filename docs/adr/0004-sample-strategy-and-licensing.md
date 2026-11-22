# ADR 0004 — Estrategia de muestra incluida y licencias

## Estado

Aceptada (2026-11-20).

## Contexto

`lakehouse build` debe funcionar por completo sin conexión y sin claves (S2), mientras que las
entradas reales suman unos 960 MB en doce archivos. Incluir esos bytes en el wheel sería
inaceptable, y incluir filas sintéticas arbitrarias rompería la promesa de que la muestra son
datos reales cuyos totales concilian con cifras publicadas. El artefacto publicado también debe
ser redistribuible (S14), lo que descarta los conjuntos de datos cuya licencia en CKAN es no
comercial.

Las tres fuentes se comportan de forma distinta. El SRI entrega diez CSV anuales de 83–109 MB
con grano provincial y cantonal; solo una porción agregada es útil para un ejemplo liviano. El
BCE entrega un único archivo congelado de 6 MB que ya es pequeño. El INEC entrega un archivo
anidado cuyos doce CSV de índices son la carga útil que necesita el parser.

## Decisión

- **Solo se incluyen fuentes redistribuibles.** Se incluyen SRI (`cc-by`), BCE (`cc-by`) e INEC
  (CC BY 4.0 en la página del editor). Los conjuntos de datos del BCE cuya licencia en CKAN es
  `cc-nc` (información mensual, cuentas nacionales 2024, tasas de interés) se excluyen del
  pipeline y del artefacto, aunque sean técnicamente accesibles. El producto de datos publicado
  sigue, por lo tanto, siendo redistribuible bajo CC BY.
- **La muestra del SRI es una reducción determinista, no datos sintéticos.** Las filas se agrupan
  por `ANIO, MES, GRUPO_IMPUESTO, SUBGRUPO_IMPUESTO, IMPUESTO, TIPO_CONTRIBUYENTE, PROVINCIA`,
  `VALOR_RECAUDADO` se suma con `decimal.Decimal` y se redondea half-up a centavos, y se eliminan
  el cantón, `GRAN_CONTRIBUYENTE` y `CODIGO_OPERA_FAMILIA`. Esto cumple D10: unas 22,700–25,900
  filas y alrededor de 0.2 MB por año, mientras cada total se conserva dentro de un centavo por
  grupo.
- **El BCE se incluye sin modificaciones.** Los bytes originales se colocan sin cambios dentro de
  un contenedor gzip, de modo que el SHA-256 descomprimido es igual al checksum fijado del origen
  y las pruebas pueden demostrarlo.
- **El INEC se reempaqueta, no se modifica.** Los doce CSV de índices se copian sin cambios desde
  los archivos anidados a un ZIP plano con marca de tiempo fija `1980-01-01`, orden determinista y
  compresión deflate. El parser maneja el archivo plano mediante el mismo comparador de miembros.
- **La reproducibilidad de bytes es un requisito.** Los escritores de gzip usan `mtime=0` y no
  guardan nombre de archivo; las entradas del ZIP usan una marca de tiempo fija. El manifest no
  contiene marca de tiempo de build, solo el inventario fijado `checked_at`, la versión del
  constructor y, por archivo, el tamaño, el SHA-256, el número de filas y el SHA-256 de origen. Por
  lo tanto, dos ejecuciones producen bytes idénticos.
- **Las cifras de control se generan a partir de los archivos completos del origen**, una fila por
  año del SRI en `dbt_project/seeds/control_totals.csv`; el año en curso se marca con
  `is_frozen=false`. Son el ancla de conciliación para las pruebas singulares de dbt y no se editan
  a mano.
- **La muestra se verifica como cualquier otra fuente.** `SAMPLE_MANIFEST.json` es el contrato:
  `SampleSourceFetcher` verifica tamaño y SHA-256 antes de copiar un archivo a la caché, y
  `lakehouse doctor` vuelve a verificar los doce archivos.
- **Los archivos originales grandes quedan fuera de git.** Las descargas van a
  `$LAKEHOUSE_HOME/cache` (o a `--cache-dir` para el comando de mantenimiento), fuera del
  repositorio; una segunda ejecución los reutiliza. Solo se versiona la muestra generada (unos
  4.1 MB).

## Consecuencias

- `lakehouse build` nunca necesita red en el modo `sample` por defecto, y cualquiera con el wheel
  puede reproducir el artefacto y el reporte.
- La muestra se mantiene dentro del presupuesto de 8,000,000 bytes y conserva los totales reales
  de recaudación, la serie real del BCE y la matriz real del IPC.
- Las pruebas afirman conteos exactos de filas del SRI, el checksum descomprimido del BCE, el
  conteo de filas del INEC y las tolerancias de los totales de control, de modo que un cambio
  silencioso en la reducción o en un archivo de origen se detecta.
- Generar la muestra es una acción de mantenimiento (`lakehouse sample build`); descarga los
  archivos fijados una vez, necesita HTTPS saliente y no forma parte de `lakehouse build`.
- El año en curso del SRI es mutable por naturaleza. El constructor registra el SHA-256 observado
  en el manifest, y las pruebas fijan la instantánea incluida en lugar del checksum en vivo (L4);
  cambiar el paquete es un commit `chore(data)` explícito.
- El grano provincial pierde el detalle de cantón en el modo `sample`. El modo `full` conserva los
  cantones, y la muestra incluida está documentada como de grano provincial.

## Alternativas consideradas

- **Fixtures sintéticos**: rápidos de generar, pero deshonestos para un portafolio de ingeniería
  de datos; los totales no conciliarían con cifras publicadas.
- **Incluir los 960 MB completos**: contradice el tamaño del wheel y la historia de instalación
  offline primero; el artefacto sería inutilizable.
- **Agregar solo a grano nacional**: más pequeño, pero eliminaría la dimensión provincial que
  necesitan el reporte y la prueba de relaciones geográficas.
- **Conservar el archivo anidado del INEC**: preserva la forma original, pero obliga al parser a
  repetir el descubrimiento del archivo en cada build; el ZIP plano es más simple y contiene los
  mismos bytes CSV originales.
- **Incluir los conjuntos `cc-nc` del BCE**: rechazado por higiene de licencias (D9), aunque las
  series adicionales habrían enriquecido el mart macro.
