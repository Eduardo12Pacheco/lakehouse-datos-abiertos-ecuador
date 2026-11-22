# Contribuir

Gracias por el interés en mejorar el Ecuador Open-Data Lakehouse.

## Configuración del entorno de desarrollo

Requisitos previos: Python 3.12 y [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked
uv run lakehouse --version
uv run python scripts/dev.py check
```

`scripts/dev.py` es el punto de entrada multiplataforma para las compuertas de calidad:

| Tarea | Qué ejecuta |
| --- | --- |
| `check` | `lint`, `format`, `arch`, `types`, `test` |
| `lint` | `ruff check .` |
| `format` | `ruff format --check .` |
| `arch` | `import-linter` (contratos de capas hexagonales) |
| `types` | `mypy` (estricto, solo `src/`) |
| `test` | `pytest` (las pruebas de navegador se excluyen salvo que estén marcadas como `e2e`) |
| `fix` | `ruff check --fix .` y luego `ruff format .` |

El primer comando que conviene ejecutar después de un cambio es el archivo de pytest enfocado;
el último es `uv run python scripts/dev.py check`. La CI ejecuta además `uv lock --check`, la
suite de pruebas en Linux, Windows y macOS, la suite de navegador, una prueba de humo del
instalador y los jobs de seguridad. Antes de abrir un pull request, ejecute localmente:

```bash
uv lock --check
uv run python scripts/dev.py check
uv run pytest -m e2e
uv build && uv run python scripts/smoke.py dist/*.whl
```

## Pruebas

- Escriba primero la prueba que falla y luego la implementación. Observe RED antes de GREEN.
- Las pruebas deben ser deterministas y funcionar sin conexión; un fixture `autouse` bloquea
  toda conexión de socket que no sea de loopback. Use `tmp_path` para el estado temporal y nunca
  escriba dentro del repositorio.
- Use Hypothesis para los invariantes de datos (orden del DAG, normalización de texto, paridad de
  codificación de los parsers, orden de carga de particiones, integridad de SCD2) y mantenga
  `deadline=None` para las propiedades que usan dbt.
- Las pruebas de integración usan DuckDB y dbt reales; no simule el warehouse.
- Las pruebas de navegador viven en `tests/e2e` detrás del marcador `e2e`. Instale Chromium una
  sola vez con `uv run playwright install chromium`.
- Nunca debilite, omita ni elimine una prueba para que la suite pase.

## Arquitectura y documentación

La regla de dependencias es `cli -> container -> adapters -> application -> domain`. `domain/`
importa solo la biblioteca estándar y a sí mismo; `application/` se comunica con los adaptadores
solo a través de los protocolos de `application/ports.py`. Si agrega un paquete, actualice en el
mismo cambio los contratos de import-linter de `pyproject.toml` y la prueba de arquitectura.

Cuando cambie un comportamiento, actualice en el mismo commit la documentación orientada al lector:

| Cambio | Documento |
| --- | --- |
| Capa, puerto, patrón, pipeline o código de salida | `docs/ARCHITECTURE.md` |
| Fuente, particularidad de formato, muestra, hecho medido o limitación | `docs/DATA.md` |
| Estructura del artefacto, manifest, verificación o consumo | `docs/ARTIFACT.md` |
| Tabla, columna, tipo o regla de versión publicada | `docs/CONTRACT.md` y `artifact_contract.json` |
| Variable de entorno, valor por defecto o sobrescritura por CLI | `docs/CONFIGURATION.md` |
| Decisión significativa con alternativas | Nuevo ADR en `docs/adr/` |

Los ADR usan la plantilla: `Estado`, `Contexto`, `Decisión`, `Consecuencias` y
`Alternativas consideradas`. Numérelos de forma secuencial y mantenga concretas las opciones
rechazadas (costo, dependencia, motivo operativo). `uv run pytest tests/unit/test_docs.py`
verifica enlaces, cobertura de settings, cobertura de la CLI, encabezados de ADR y bloques
Mermaid.

## Regenerar archivos generados

Todos los archivos generados están versionados, y cada uno tiene un comando reproducible.

**Linaje** (requiere un warehouse construido):

```bash
uv run lakehouse docs --mermaid docs/LINEAGE.md
git diff --exit-code docs/LINEAGE.md   # must be clean after regeneration
```

**Muestra incluida** (solo mantenimiento; descarga unos 960 MB una vez):

```bash
uv run lakehouse sample build --cache-dir "$LAKEHOUSE_HOME/cache"
```

El comando verifica cada SHA-256 fijado, escribe `src/ecuador_lakehouse/sample_data/`, regenera
`SAMPLE_MANIFEST.json` y actualiza `dbt_project/seeds/control_totals.csv`. Confirme el resultado
en un commit aparte `chore(data): ...` e incluya en el mensaje los conteos de filas observados.
Nunca confirme un archivo de origen ni un directorio de caché.

**Medios** (requiere Chromium):

```bash
uv run python scripts/capture_media.py
```

El script construye una muestra desechable del lakehouse, captura ocho PNG de 1440x900 en
`docs/media/` y arma `demo.gif` a partir de las páginas, verificando que cada cuadro no esté vacío
y que el GIF respete el presupuesto de tamaño.

**Métricas del README** (requiere un build de muestra; sin red):

```bash
uv run python scripts/gen_metrics.py
```

El script construye y publica una muestra desechable del lakehouse, lee el manifest de dbt, los
resultados de calidad y el artefacto, y después reescribe `docs/METRICS.json`. Pegue la tabla
impresa tanto en `README.md` como en `README.en.md`, entre los marcadores
`metrics:start`/`metrics:end`. Verifique con `uv run python scripts/gen_metrics.py --check`; nunca
edite una métrica a mano.

**ECharts incluido**:

```bash
uv run python scripts/vendor_echarts.py
```

El script descarga el bundle fijado de ECharts 6.1.0, verifica su tamaño y su SHA-256, y escribe
los archivos de licencia y de aviso. No incluya otra versión sin actualizar el checksum fijado y
el ADR.

## Commits y pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org/) en inglés:
  `feat(cli): add serve command`, `fix(parsers): handle cp1252 SRI files`,
  `docs(architecture): document the artifact contract`.
- Mantenga los commits enfocados y revisables (unas 400 líneas cambiadas o menos, sin contar los
  datos generados). Coloque los bytes de la muestra generada en su propio commit.
- No agregue atribuciones de IA ni trailers `Co-Authored-By`.
- Cada pull request debe pasar lint, las verificaciones de tipos y la matriz de pruebas en Linux,
  Windows y macOS antes de fusionarse.
- Actualice `CHANGELOG.md` bajo `Unreleased` para los cambios visibles para el usuario.

## Publicación de una versión

1. Incremente `version` en `pyproject.toml` y el valor de respaldo en
   `src/ecuador_lakehouse/__init__.py`, luego ejecute `uv lock`. Vuelva a ejecutar
   `uv run lakehouse sample build` (con `--cache-dir` apuntando a la caché de origen verificada,
   para mantenerse sin conexión): `SAMPLE_MANIFEST.json` registra la versión del constructor y una
   prueba la fija a la versión del paquete.
2. Mueva las entradas de `Unreleased` de `CHANGELOG.md` a la nueva versión y actualice la URL del
   wheel del release en ambos README.
3. Actualice la instantánea de métricas (`uv run python scripts/gen_metrics.py`) y confirme el
   cambio.
4. Haga push de una etiqueta `vX.Y.Z`. `release.yml` falla de inmediato si la etiqueta y la
   versión del paquete no coinciden; de lo contrario, vuelve a ejecutar la CI, construye el wheel,
   el sdist y el zip del artefacto de muestra, escribe `SHA256SUMS` y crea el release de GitHub.

## Reportar problemas de seguridad

No abra un issue público para una vulnerabilidad. Siga el procedimiento de
[SECURITY.md](SECURITY.md).
