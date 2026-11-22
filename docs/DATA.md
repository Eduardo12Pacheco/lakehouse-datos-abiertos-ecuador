# Fuentes de datos, linaje y limitaciones

Esta página registra de dónde provienen los datos, cómo se verifican, qué contiene la
muestra incluida y qué pueden y qué no pueden afirmar las cifras. La fuente de verdad para
la adquisición es `src/ecuador_lakehouse/sources.lock.json`; la fuente de verdad para los
archivos incluidos es `src/ecuador_lakehouse/sample_data/SAMPLE_MANIFEST.json`.

## Fuentes

Todas las fuentes se verificaron el 2026-11-19 sin cuenta, clave ni sesión de navegador,
con el mismo User-Agent que envía el fetcher. Cada archivo de origen está fijado por tamaño
y SHA-256 en `sources.lock.json`; las descargas están restringidas a los hosts indicados
a continuación.

| Fuente | Editor | URL | Formato | Licencia | Partición |
| --- | --- | --- | --- | --- | --- |
| Recaudación de impuestos del SRI | Servicio de Rentas Internas | `https://descargas.sri.gob.ec/download/datosAbiertos/sri_recaudacion_<YYYY>.csv` | `\|`-delimitado, un archivo por año 2017–2026 | CC BY (`license_id: cc-by` en CKAN) | anual |
| Índice de precios al consumidor del INEC | Instituto Nacional de Estadística y Censos | `https://www.ecuadorencifras.gob.ec/documentos/web-inec/Inflacion/2024/Diciembre/Tabulados_y_series_historicas_CSV.zip` | ZIP anidado con 12 CSV anchos, cp1252 | CC BY 4.0 (indicada en la página del IPC) | `2024-12` |
| Cuentas nacionales del BCE | Banco Central del Ecuador | `https://www.datosabiertos.gob.ec/dataset/7d5ad4b3-a8f7-42d9-8103-81336a592ea6/resource/2fe2427a-daeb-4137-a29f-22834f3d5ee0/download/cuentastrimestralesdesagregadas.csv` | CSV delimitado por `;`, cp1252, CRLF | CC BY (`license_id: cc-by` en CKAN) | congelada 2000Q1–2021Q1 |

La API de CKAN `https://www.datosabiertos.gob.ec/api/3/action/package_show?id=<dataset>`
se usa solo como evidencia de licencia; sus respuestas grabadas viven en
`tests/fixtures/ckan/`. Ninguna respuesta del catálogo es necesaria al momento del build.

### Archivos fijados

Estos son los doce archivos que fija el lockfile. Los tamaños están en bytes; los valores
SHA-256 corresponden a los bytes originales de la fuente. Solo el año SRI en curso es
mutable, porque el SRI lo actualiza mensualmente.

| Archivo | Bytes | SHA-256 | Mutable |
| --- | ---: | --- | --- |
| `sri_recaudacion_2017.csv` | 84,892,997 | `dd14c281d082417342daa2e3060ba1df759f2c29a2f7144e4ce91e62a79753d4` | no |
| `sri_recaudacion_2018.csv` | 90,751,274 | `5159954189b7e771b45e8a8f39dced83c1ea555a2044e277ad92dc9a8a4c40a2` | no |
| `sri_recaudacion_2019.csv` | 95,526,741 | `2d109fe8c4419086c17ae11c74095a87d7bb30a3bfe90f6aa1445700ffd475df` | no |
| `sri_recaudacion_2020.csv` | 84,746,785 | `20e51bafc4cb4d49edacc6ee346bff7a5fcc2237bbc8f041163dc3bab65b1903` | no |
| `sri_recaudacion_2021.csv` | 101,639,183 | `bf088d16738ab9e4bca10803155680e80564107f320034e8c8b37ebd200845fe` | no |
| `sri_recaudacion_2022.csv` | 108,707,735 | `7a7f106f64cf0070377b4898c06907bdc50c293763050630bc742601d30b1b69` | no |
| `sri_recaudacion_2023.csv` | 100,356,033 | `e6e80b5cdbae088e7ab4f4e4be3b30b75faf1df81edeb4cca2c3f52001f10c51` | no |
| `sri_recaudacion_2024.csv` | 96,066,889 | `f5ffc07af3666084f2de1904ae198f3b48d9fe219176ca7039109e4d3040e173` | no |
| `sri_recaudacion_2025.csv` | 100,563,014 | `d6ec28197b6b85f2ce05cf12c076d34556e7c99cff49e4ad6d0995639fed1c4d` | no |
| `sri_recaudacion_2026.csv` | 83,320,465 | `90878717f7faadaf5f3e815ca35c6164b059ae97b7ef8b8722e7b843918b420f` | **sí** |
| `Tabulados_y_series_historicas_CSV.zip` | 7,479,409 | `e7b854b4f422d23f622e3c474ebc47a0bc46caa9d15f0a3670bce7f67fc697f4` | no |
| `cuentastrimestralesdesagregadas.csv` | 6,108,986 | `b90e0e5a403a44ecd862969b72c6fc900f730e62d7b4cffecaa55116ed81e187` | no |

### Particularidades de formato que manejan los parsers

- **SRI** está en UTF-8 con BOM para 2017–2022 y en cp1252 para 2023–2026. Los archivos
  están delimitados por `|`, los meses son etiquetas como `01 Enero`, los montos usan coma
  decimal (`83,3100`) y `CANTON` no existe en los archivos antiguos. Las columnas reales
  adicionales (`GRAN_CONTRIBUYENTE`, `CODIGO_OPERA_FAMILIA`) se ignoran solo después de
  validar el encabezado requerido. Las columnas requeridas faltantes y los encabezados
  desconocidos generan `SourceSchemaError` (código 4).
- **BCE** está en cp1252 con delimitadores `;` y CRLF; los montos usan separadores de miles
  con coma, los valores vacíos se conservan como cadenas vacías y los valores negativos son
  válidos.
- **INEC** es un ZIP dentro de un ZIP dentro de un ZIP. Cada uno de los 12 CSV tiene cuatro
  filas de título, un encabezado `Nivel`, 120 columnas de meses en español
  (`ene-15`…`dic-24`), tres filas de pie y decimales mixtos (`1,000000` y
  `0.224503124`). El parser detecta el encabezado, se detiene en el pie y convierte los
  meses en filas largas.

La política de decodificación D13 es estricta: se intenta `utf-8-sig` y luego `cp1252`;
nunca se ignoran bytes. Si ambas fallan, el parser genera `SourceSchemaError`.

## Muestra incluida

`lakehouse build` usa por defecto `--mode sample` y lee solo el wheel. La muestra son datos
reales, reducidos de forma determinista:

- Los archivos del SRI se agregan a `ANIO, MES, GRUPO, SUBGRUPO, IMPUESTO,
  TIPO_CONTRIBUYENTE, PROVINCIA` con redondeo `Decimal` half-up a centavos. El grano
  provincial elimina el detalle de cantón y de familia de operadores, pero conserva cada
  total de grupo dentro de un centavo.
- Los bytes del BCE se incluyen sin cambios dentro de gzip, de modo que el SHA-256
  descomprimido es igual al checksum fijado del origen.
- Los 12 CSV del IPC del INEC se copian sin cambios dentro de un ZIP plano, con marcas de
  tiempo fijas y orden determinista.

El paquete pesa unos 4.15 MB (presupuesto: 8,000,000 bytes) y contiene 12 archivos. Conteo
de filas:

| Partición | Filas |
| --- | ---: |
| SRI 2017 | 22,679 |
| SRI 2018 | 22,777 |
| SRI 2019 | 24,035 |
| SRI 2020 | 23,839 |
| SRI 2021 | 25,260 |
| SRI 2022 | 25,889 |
| SRI 2023 | 25,519 |
| SRI 2024 | 24,423 |
| SRI 2025 | 25,348 |
| SRI 2026 (ene–oct) | 21,548 |
| Cuentas nacionales del BCE | 32,470 |
| IPC del INEC (filas largas tras pasar a formato largo) | 911,520 |

`lakehouse doctor` vuelve a verificar cada archivo incluido contra `SAMPLE_MANIFEST.json`.
El comando de mantenimiento `lakehouse sample build` reconstruye el paquete a partir de los
archivos originales fijados y no forma parte de un build normal. La reducción de la muestra
y su justificación de licencia están registradas en
[ADR 0004](adr/0004-sample-strategy-and-licensing.md).

## Hechos medidos

Estas cifras se miden a partir de los archivos verificados y las usan las pruebas y el
reporte. No son proyecciones.

- Recaudación anual del SRI (millones de USD): 2019 14,268.8; 2020 12,381.8; 2021
  13,976.2; 2022 17,161.8; 2023 17,419.7; 2024 20,131.3; 2025 21,500.9; 2026 ene–oct
  20,763.9. La cifra de 2025 coincide con el titular publicado de unos USD 21,501 millones.
- El historial del SRI contiene 244 líneas de impuesto normalizadas distintas entre
  2017–2026, con 135–173 presentes por año, 83 presentes en los diez años, 109 introducidas
  después de 2017, 102 retiradas antes de 2026 y 62 con huecos. La clave natural SCD2 es
  impuesto x subgrupo, lo que produce 245 combinaciones (una línea de impuesto pertenece
  legítimamente a dos subgrupos). No se observó reclasificación de grupo o subgrupo
  (0 de 244 líneas).
- Las cuentas nacionales del BCE contienen 85 trimestres (2000Q1–2021Q1), 45 industrias,
  agregados del PIB y dos bases de precios; 176 valores están vacíos y 32,470 filas cubren
  el producto de trimestres, bases y 191 códigos.
- IPC nacional del INEC: 633 filas de ítems x 120 meses (enero de 2015 a diciembre de 2024),
  base 2014 = 100. El índice general en enero de 2015 es 101.24.

Las cifras de control que usan las pruebas de conciliación viven en
`src/ecuador_lakehouse/dbt_project/seeds/control_totals.csv`; se generan a partir de los
archivos completos de origen y nunca se editan a mano.

## Linaje

```text
sources.lock.json + sample manifest
        |
        v
raw.sri_tax_collection / raw.bce_cnt_quarterly / raw.inec_cpi_index
  (+ meta.batches)
        |
        v
staging: stg_sri__tax_collection, stg_bce__national_accounts,
         stg_inec__cpi_index
        |
        v
intermediate: int_tax_item_year_presence, int_tax_item_versions,
              int_tax_collection_monthly, int_cpi_national_monthly,
              int_gdp_annual
        |
        v
marts: dim_date, dim_quarter, dim_geography, dim_tax_item, dim_price_area,
       dim_cpi_item, dim_national_account_item, fct_tax_collection,
       fct_cpi_index, fct_national_accounts, mart_tax_collection_monthly,
       mart_inflation_monthly, mart_tax_to_gdp_annual, mart_tax_lifecycle
```

El DAG de modelos renderizado está versionado en [LINEAGE.md](LINEAGE.md) y se regenera con
`lakehouse docs --mermaid docs/LINEAGE.md`. Cada modelo y cada columna se describen en dbt;
el subconjunto publicado se describe en [ARTIFACT.md](ARTIFACT.md).

## Licencias y atribución

El código tiene licencia MIT. Los datos conservan la licencia de su editor:

- Recaudación del SRI y cuentas nacionales del BCE: Creative Commons Attribution (`cc-by`).
- IPC del INEC: Creative Commons Attribution 4.0 International (CC BY 4.0).

La muestra incluida y el artefacto publicado incluyen `ATTRIBUTION.md` con el editor, la URL
de origen, la licencia y las modificaciones. La redistribución de datos derivados está
permitida con atribución. Los conjuntos de datos del BCE cuya licencia en CKAN es no
comercial se excluyen deliberadamente, aunque sean accesibles
([ADR 0004](adr/0004-sample-strategy-and-licensing.md)).

## Limitaciones

- **El SRI no mide la presión fiscal total.** La serie cubre solo los impuestos administrados
  por el SRI. Excluye otros ingresos públicos, y la razón SRI/PIB es un indicador parcial,
  no una medida general de impuestos sobre el PIB. El mart macro expone la razón solo para
  años completos.
- **Corte de la versión del IPC.** La versión incluida del IPC del INEC termina en diciembre
  de 2024, con base 2014 = 100. Una nueva base (julio 2025–junio 2026 = 100) comenzó en 2026
  y está fuera de alcance. Por lo tanto, los valores de impuestos deflactados se detienen en
  2024-12; los meses posteriores conservan valores nominales.
- **La serie del BCE termina en 2021Q1.** Las cuentas nacionales se detienen ahí, así que solo
  2017, 2018, 2019 y 2020 tienen cuatro trimestres y están marcados como `is_complete`. La
  razón de 2021 se publica para inspección, pero se marca como incompleta; 2022 y años
  posteriores no tienen denominador de PIB.
- **Limitación de SCD2.** Con datos reales, el ciclo de vida de las líneas de impuesto se
  explica por su introducción, su retiro y sus huecos; no se observó reclasificación de grupo
  o subgrupo en 2017–2026. Los cambios de atributos están cubiertos por pruebas unitarias de
  dbt y por una prueba de propiedades de Hypothesis sobre el modelo real, no solo por la
  muestra. Un ítem retirado antes del último año cargado conserva una versión inactiva
  abierta; los hechos solo se unen con versiones activas, así que esto no afecta a los marts.
- **Grano de la muestra.** La muestra incluida tiene grano provincial, sin detalle de cantón
  ni columnas de familia de operadores. El modo `full` conserva los cantones presentes en los
  archivos de origen, pero las historias del reporte y del artefacto se construyen sobre la
  muestra.
- **Sin garantía de frescura en vivo.** El año SRI en curso es mutable y el SRI lo actualiza
  mensualmente. El paquete fija la instantánea observada el 2026-11-19; `lakehouse fetch`
  puede obtener bytes más recientes, y aceptar una nueva versión es una acción explícita y
  registrada.
- **No incluido.** Las series del SRI alojadas solo en un host poco confiable, los conjuntos
  de datos no comerciales del BCE, la base 2026 del IPC y la API del Banco Mundial están
  fuera de alcance. El proyecto se limita a tres fuentes ecuatorianas verificadas.

## Reproducir la capa de datos

```bash
# Offline default: uses the bundled sample.
lakehouse build

# Check the bundle and the installation.
lakehouse doctor

# Maintainers only: download the pinned files once and rebuild the bundle.
lakehouse fetch --source sri --years 2025
lakehouse sample build --cache-dir "$LAKEHOUSE_HOME/cache"

# Regenerate lineage from a real dbt parse.
lakehouse docs --mermaid docs/LINEAGE.md
```

Las descargas se guardan en caché bajo `$LAKEHOUSE_HOME/cache` y nunca se versionan. Los
archivos grandes de origen quedan fuera de git; solo se versiona la muestra reducida.
