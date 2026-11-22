# Configuración

Toda la configuración de ejecución proviene de variables de entorno con el prefijo
`LAKEHOUSE_`, cargadas por `config.Settings` (pydantic-settings). Los valores se validan
antes de iniciar cualquier trabajo; un valor inválido produce un `ConfigError` legible y el
código de salida 2, nunca un traceback.

Precedencia: un flag explícito de la CLI sobrescribe el entorno, y el entorno sobrescribe el
valor por defecto integrado. La configuración se guarda en caché por proceso con
`get_settings()`; inicie un nuevo comando después de cambiar el entorno.

## Variables de entorno

| Variable | Tipo | Valor por defecto | Valores permitidos | Significado |
| --- | --- | --- | --- | --- |
| `LAKEHOUSE_HOME` | ruta | directorio de datos de usuario de la plataforma para `ecuador-lakehouse` | ruta absoluta | Raíz del warehouse, la caché, el workspace de dbt, el sitio y la salida por defecto del artefacto |
| `LAKEHOUSE_MODE` | cadena | `sample` | `sample`, `full` | `sample` lee los datos incluidos sin conexión; `full` descarga los archivos originales fijados |
| `LAKEHOUSE_LOG_LEVEL` | cadena | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Nivel mínimo de structlog (entrada sin distinguir mayúsculas) |
| `LAKEHOUSE_LOG_FORMAT` | cadena | `console` | `console`, `json` | Logs legibles para personas o JSON por línea |
| `LAKEHOUSE_HTTP_TIMEOUT_S` | float | `30.0` | > 0 y <= 600 segundos | Tiempo de espera HTTP por solicitud |
| `LAKEHOUSE_HTTP_RETRIES` | entero | `3` | 0–10 | Reintentos para fallos transitorios de descarga, con backoff exponencial |
| `LAKEHOUSE_SERVE_HOST` | cadena | `127.0.0.1` | dirección de loopback | Interfaz para `lakehouse serve` |
| `LAKEHOUSE_SERVE_PORT` | entero | `15080` | 1024–65535 | Puerto para `lakehouse serve`; el rango 15000–15999 evita colisiones con otros proyectos locales |
| `LAKEHOUSE_DBT_THREADS` | entero | `4` | 1–32 | Número de hilos de dbt que se pasa al transformador |
| `LAKEHOUSE_YEARS` | selección de años | `2017-2026` | `2024`, `2019,2021-2022`, `2017-2026` | Particiones del SRI usadas por `build`, `fetch` y `sample build` |

`LAKEHOUSE_HOME` acepta una ruta relativa, que se resuelve respecto del directorio de trabajo
actual, pero se recomienda una ruta absoluta. Los comandos que lo necesitan crean el
directorio si no existe.

`LAKEHOUSE_YEARS` se interpreta como una lista de años separados por comas y rangos
inclusivos. Los años deben estar entre 2000 y 2100, el resultado se ordena y se eliminan los
duplicados, y una selección vacía se rechaza. Aplica solo al SRI: el BCE y el INEC tienen
cada uno una única partición fija.

## Sobrescrituras por CLI

Estos flags sobrescriben la configuración correspondiente para una sola invocación:

| Comando | Flag | Sobrescribe |
| --- | --- | --- |
| `lakehouse serve` | `--host`, `--port`, `--open/--no-open` | `LAKEHOUSE_SERVE_HOST`, `LAKEHOUSE_SERVE_PORT` |
| `lakehouse fetch` | `--years` | `LAKEHOUSE_YEARS`, solo para el SRI |
| `lakehouse fetch` | `--source`, `--accept-new-vintage` | no son configuración; selecciona la fuente y acepta explícitamente una versión mutable |
| `lakehouse sample build` | `--years` | `LAKEHOUSE_YEARS` |
| `lakehouse sample build` | `--cache-dir`, `--output-dir`, `--seed-dir` | ubicaciones de caché y de salida (solo mantenimiento) |
| `lakehouse build` | `--select`, `--only`, `--from-step`, `--publish`, `--out` | selección del pipeline y ubicación del artefacto |
| `lakehouse publish` | `--out` | directorio de salida del artefacto |
| `lakehouse docs` | `--mermaid PATH` | también escribe el archivo de linaje en Mermaid en `PATH` |
| `lakehouse contract check` | `--contract`, `--warehouse` | rutas del contrato y del warehouse |
| `lakehouse --debug` | — | muestra un traceback completo para errores inesperados |

## Estructura del home de ejecución

Todo lo mutable vive bajo `LAKEHOUSE_HOME`; el repositorio y el paquete instalado permanecen
de solo lectura durante un build.

```text
$LAKEHOUSE_HOME/
├── warehouse.duckdb          # raw, staging, intermediate, marts, meta
├── cache/
│   ├── sri_tax/              # archivos originales verificados (+ .part al reanudar)
│   ├── bce_cnt/
│   └── inec_cpi/
├── dbt/
│   ├── project/              # copia del proyecto dbt empaquetado
│   ├── target/               # run_results.json, manifest.json, docs
│   └── logs/
├── site/                     # reporte estático generado + lineage/index.html
└── artifact/                 # salida de publicación por defecto para la API de librería
```

`lakehouse publish` y `lakehouse build --publish` establecen `--out` por defecto en
`./dist-artifact` para que el artefacto sea fácil de encontrar; pase un `--out` explícito
para mantenerlo dentro del home de ejecución. Las descargas de origen se guardan en caché bajo
`cache/` y nunca se versionan.

## Logging

`LAKEHOUSE_LOG_FORMAT=console` muestra eventos estructurados para una terminal, mientras que
`json` emite un objeto por línea para su ingesta:

```bash
LAKEHOUSE_LOG_LEVEL=DEBUG LAKEHOUSE_LOG_FORMAT=json lakehouse build
```

Cada error esperado se registra con su código de salida. `lakehouse --debug` imprime un
traceback solo para excepciones inesperadas; los fallos esperados se mantienen limpios.

## Códigos de salida

| Código | Significado |
| ---: | --- |
| 0 | éxito |
| 1 | excepción inesperada |
| 2 | configuración inválida o uso incorrecto del comando |
| 3 | discrepancia de checksum en una fuente inmutable |
| 4 | error de esquema o de archivo de la fuente |
| 5 | fuente no disponible |
| 6 | fallo de la transformación dbt |
| 7 | fallo de la compuerta de calidad |
| 8 | fallo de verificación del artefacto o del contrato |

La lista completa y las clases de error que la respaldan están en
[ARCHITECTURE.md](ARCHITECTURE.md#modelo-de-fallos-y-códigos-de-salida).

## Ejemplos

Build de muestra sin conexión en un home aislado:

```bash
LAKEHOUSE_HOME="$(mktemp -d)" lakehouse build
```

Modo `full` contra los archivos reales y, luego, un reporte en otro puerto:

```bash
LAKEHOUSE_MODE=full LAKEHOUSE_YEARS=2019-2026 lakehouse build
LAKEHOUSE_SERVE_PORT=15120 lakehouse serve --no-open
```

Logs JSON reproducibles para una ejecución de CI:

```bash
LAKEHOUSE_LOG_FORMAT=json LAKEHOUSE_LOG_LEVEL=INFO lakehouse test
```

## Notas de seguridad

- No existe ninguna variable de credenciales, token o cuenta. La herramienta nunca solicita
  una.
- Las descargas se limitan a los hosts de `sources.lock.json`; las redirecciones fuera de esa
  lista de permitidos se rechazan.
- Cada descarga tiene un tamaño máximo y se verifica contra un SHA-256 fijado antes de
  usarse.
- `lakehouse serve` solo escucha en loopback por diseño y no tiene autenticación; no lo
  exponga en una interfaz pública.
