# Artefacto publicado

`lakehouse publish --out DIR` convierte los marts en un producto de datos versionado y
autodescriptivo que otro proyecto puede consumir sin instalar este paquete. `lakehouse build
--publish --out DIR` ejecuta el pipeline completo y publica después de la compuerta de
calidad. `lakehouse verify DIR` vuelve a revisar el resultado y termina con código 8 ante
cualquier inconsistencia.

El artefacto es un directorio, no un servicio ni un servidor de base de datos: puede
comprimirse en un zip, adjuntarse a un GitHub Release, copiarse a una memoria USB o leerse
directamente desde un proyecto hermano.

## Estructura

```text
DIR/ecuador-lakehouse-1.0.0/
├── ecuador_lakehouse.duckdb   # solo los esquemas marts + meta
├── parquet/
│   ├── dim_date.parquet
│   ├── ...                    # un archivo Parquet ZSTD por tabla publicada
│   └── mart_tax_lifecycle.parquet
├── manifest.json              # metadatos deterministas, sin campos de reloj
├── SHA256SUMS                 # un SHA-256 por archivo de contenido
└── ATTRIBUTION.md             # URLs de origen, licencias y modificaciones
```

El nombre del directorio es `<artifact_name>-<artifact_version>`. La versión actual del
artefacto es `1.0.0` e iguala la versión del contrato; es independiente de la versión del
paquete de Python. La base de datos expone solo `marts` (las tablas públicas) y una pequeña
tabla `meta.build_info` (hora de build, versión del artefacto, generador, modo de datos). La
hora de build nunca participa en una huella digital.

Las tablas publicadas son las 7 dimensiones conformadas, los 3 hechos y los 4 marts
analíticos listados en [ARCHITECTURE.md](ARCHITECTURE.md). El esquema tipado está versionado
en `src/ecuador_lakehouse/artifact_contract.json` y se explica en
[CONTRACT.md](CONTRACT.md).

## Manifest

`manifest.json` se valida con
[`docs/schemas/manifest.schema.json`](schemas/manifest.schema.json)
(JSON Schema draft 2020-12, `schema_version: "1.0"`). No contiene fechas de build.

| Campo | Significado |
| --- | --- |
| `schema_version` | Versión del esquema del manifest; actualmente `"1.0"` |
| `artifact_name` | `ecuador-lakehouse` |
| `artifact_version` | Versión semver del producto de datos; iguala la versión del contrato |
| `generator` | `ecuador-open-data-lakehouse/<versión del paquete>` |
| `duckdb_version` | Versión de DuckDB que escribió el artefacto |
| `dbt_core_version` | Versión de dbt-core que construyó los marts |
| `data_mode` | `sample` o `full` |
| `built_from` | Por fuente `{source_id, url, license_id, files:[{name, sha256}]}` |
| `tables` | Una entrada por tabla publicada |
| `quality` | `{tests_total, tests_passed, unit_tests_total, unit_tests_passed}` |
| `attribution` | El texto completo de atribución, también escrito en `ATTRIBUTION.md` |

Cada entrada de `tables` tiene:

| Campo | Significado |
| --- | --- |
| `name`, `schema` | Nombre de la tabla y esquema (`marts`) |
| `kind` | `dim`, `fct` o `mart` |
| `grain` | Grano legible por personas, reflejado desde el contrato |
| `row_count` | Número exacto de filas al momento de publicar |
| `columns` | Ternas ordenadas `{name, type, description}` |
| `content_sha256` | Huella digital lógica de la tabla |
| `parquet_file` | Ruta relativa, por ejemplo `parquet/dim_date.parquet` |

`content_sha256` es el SHA-256 de los bytes producidos por
`COPY (SELECT * FROM <table> ORDER BY ALL) TO <file> (FORMAT CSV)`. Normaliza el orden de
las filas e ignora los metadatos de archivo de DuckDB y Parquet, de modo que dos builds con
las mismas entradas y el mismo modo de datos coinciden, aunque los bytes de la base de datos
y de Parquet no coincidan. Esa es la garantía de determinismo: dos builds limpios de la
muestra producen valores `content_sha256` iguales para las 14 tablas.

## Consumo con DuckDB

Abra la base de datos en modo de solo lectura. `ATTACH` es útil cuando el consumidor ya tiene
una conexión con sus propias tablas:

```sql
ATTACH 'DIR/ecuador-lakehouse-1.0.0/ecuador_lakehouse.duckdb'
    AS lakehouse (READ_ONLY);

SELECT tax_group_name, sum(nominal_usd) AS total_usd
FROM lakehouse.marts.mart_tax_collection_monthly
WHERE period_year = 2025
GROUP BY tax_group_name
ORDER BY total_usd DESC
LIMIT 5;
```

Desde Python, con solo la dependencia `duckdb`:

```python
import duckdb

database = artifact_dir / "ecuador_lakehouse.duckdb"
with duckdb.connect(str(database), read_only=True) as con:
    rows = con.execute(
        """
        SELECT period_year, ratio
        FROM marts.mart_tax_to_gdp_annual
        WHERE is_complete
        ORDER BY period_year DESC
        LIMIT 1
        """
    ).fetchall()
```

Use `ATTACH ... (READ_ONLY)` en su lugar cuando ya tenga una conexión con sus propias tablas,
como en el ejemplo SQL anterior.

El ejemplo ejecutable completo está en
[`examples/consume_artifact.py`](../examples/consume_artifact.py). Solo importa `duckdb` y la
biblioteca estándar, imprime los cinco principales grupos de impuestos del último año y la
última razón SRI/PIB completa, y una prueba verifica que no importa `ecuador_lakehouse`.

Los archivos Parquet se pueden leer sin la base de datos DuckDB:

```sql
SELECT * FROM read_parquet('DIR/ecuador-lakehouse-1.0.0/parquet/mart_inflation_monthly.parquet');
```

## Verificar un artefacto

```bash
lakehouse verify DIR/ecuador-lakehouse-1.0.0
```

La verificación es deliberadamente redundante. Comprueba:

1. `manifest.json` se parsea y es internamente consistente.
2. Existe cada archivo esperado: la base de datos, `manifest.json`, `ATTRIBUTION.md` y un
   archivo Parquet por tabla; no hay archivos no listados.
3. `SHA256SUMS` cubre cada archivo de contenido y cada byte coincide con su SHA-256
   registrado.
4. El número de filas de cada Parquet y la lista de tipos de columna coinciden con el
   manifest.
5. El archivo DuckDB tiene un esquema `marts` y ningún esquema `raw`, `staging` o
   `intermediate`.
6. El conjunto de tablas de DuckDB, las columnas ordenadas y el número de filas coinciden con
   el manifest.
7. El `content_sha256` lógico de cada tabla coincide con el manifest.

Una tabla faltante, un byte alterado, un cambio de esquema o una edición del manifest fallan
con `ArtifactVerificationError` y código de salida 8. La verificación solo necesita el
directorio del artefacto y DuckDB; no lee el warehouse.

## Compatibilidad de versiones

Dos versiones evolucionan de forma independiente:

- **Versión del paquete** (`0.1.1`) describe el software: CLI, parsers, reporte y el proyecto
  dbt.
- **Versión del artefacto** (`1.0.0`) describe el producto de datos e iguala la versión del
  contrato.

Los consumidores deben fijar la versión del artefacto que probaron y revisar
`manifest.json.schema_version` antes de parsear el manifest. El significado semver de
`artifact_version` se define en [CONTRACT.md](CONTRACT.md): un incremento MAJOR significa que
se eliminó o renombró una tabla o columna, o que cambió un tipo; un incremento MINOR agrega
algo; un incremento PATCH corrige datos sin cambiar el esquema.

El manifest también registra `duckdb_version` y `dbt_core_version`, de modo que un consumidor
pueda reproducir o diagnosticar un build. `data_mode` es importante: la `sample` incluida
tiene grano provincial, mientras que `full` conserva el detalle de cantones.

## Licencias y redistribución

El artefacto contiene datos derivados, no código. `ATTRIBUTION.md` enumera el editor, la URL
de origen, la licencia y las modificaciones de SRI, INEC y BCE. Los datos del SRI y del BCE
son CC BY; los del INEC son CC BY 4.0. Solo se incluyen fuentes CC BY / CC BY 4.0, así que el
artefacto es redistribuible con atribución. Los conjuntos de datos no comerciales del BCE se
excluyen deliberadamente ([ADR 0004](adr/0004-sample-strategy-and-licensing.md)).
