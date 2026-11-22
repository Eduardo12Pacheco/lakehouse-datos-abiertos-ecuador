# ADR 0002 — Arquitectura hexagonal aplicada con import-linter y pruebas AST

## Estado

Aceptada (2026-11-19).

## Contexto

El proyecto mezcla varias preocupaciones que son fáciles de enredar: reglas de negocio puras
(claves canónicas de texto, identificadores de lote, el DAG del pipeline), casos de uso
(adquirir, cargar, transformar, publicar) y adaptadores de E/S (HTTP, DuckDB, dbt, el
renderizador de reportes, la CLI). El estándar del portafolio exige una arquitectura
hexagonal con la dirección de dependencias verificada por una prueba, no solo por convención o
revisión de código.

El dominio debe seguir siendo barato de probar: sin red, sin base de datos, sin dbt y sin
sistema de archivos. La capa de aplicación puede orquestar E/S mediante puertos y puede usar la
biblioteca estándar para archivos, pero no debe acceder a los adaptadores ni a bibliotecas de
E/S de terceros. Los adaptadores deben ser mutuamente independientes, de modo que un parser no
pueda importar el warehouse y un warehouse no pueda importar el renderizador de reportes.

## Decisión

- Paquetes: `domain/`, `application/`, `adapters/`, `cli/`, además de la raíz de composición
  `container.py`, `config.py` y `logging_setup.py`.
- Dirección de dependencias: `cli -> container -> adapters -> application -> domain`. Las capas
  superiores pueden importar capas inferiores, nunca al revés.
- `domain/` usa solo la biblioteca estándar y `ecuador_lakehouse.domain`. Tampoco puede importar
  `config` ni `logging_setup`.
- `application/` define puertos como `typing.Protocol` y se comunica con los adaptadores solo a
  través de ellos. No puede importar `adapters/`, `config`, `logging_setup`, `duckdb`, `dbt`,
  `httpx`, `jinja2`, `typer` ni `rich`.
- Los subpaquetes de adaptadores (`sources`, `parsers`, `warehouse`, `transform`, `artifact`,
  `report`, `docs`) son independientes entre sí.
- La aplicación de la regla tiene dos mecanismos independientes:
  1. contratos de import-linter en `pyproject.toml` (`layers`, `forbidden`, `independence`),
     ejecutados por `uv run lint-imports`, por `scripts/dev.py check` y por la CI;
  2. un escaneo AST en `tests/architecture/test_layers.py` que demuestra que todo import bajo
     `domain/` se resuelve a la biblioteca estándar o a `ecuador_lakehouse.domain`, y que
     `application/` no importa sus módulos prohibidos. El escaneo tiene autopruebas que insertan
     un archivo infractor en un paquete temporal, de modo que la guardia no pueda dejar de
     funcionar en silencio.
- Patrones nombrados en `docs/ARCHITECTURE.md`: Ports & Adapters; Strategy para parsers,
  decodificadores y fetchers; Factory y raíz de composición en `container.py`; Repository para el
  ledger de lotes; Unit of Work para las cargas de particiones; Pipeline/DAG con pasos de
  Template Method; objetos de valor como dataclasses inmutables; y pruebas genéricas propias como
  especificaciones ejecutables.

## Consecuencias

- Las pruebas del dominio se ejecutan en milisegundos y no necesitan más fixtures que valores de
  Python.
- Cambiar HTTP por la muestra incluida, o DuckDB por otro warehouse, modifica solo los
  adaptadores y la raíz de composición.
- Los dos mecanismos de verificación se superponen a propósito: import-linter entiende los imports
  transitivos y externos; el escaneo AST es explícito, rápido de diagnosticar y no puede
  satisfacerse con re-exportaciones ingeniosas.
- Los nuevos subpaquetes de adaptadores deben agregarse al contrato de independencia antes de
  poder importarse entre sí; esa fricción es intencional.
- Algo de código repetitivo es inevitable (puertos, cableado). Se concentra en `container.py` en
  lugar de dispersarse entre los casos de uso.
- `config.py` y `logging_setup.py` quedan fuera de las capas porque son transversales; los
  contratos de prohibición los mantienen fuera de las dos capas internas.

## Alternativas consideradas

- **Layout de paquetes simple con revisión de código**: no verificable, y el estándar exige
  explícitamente una prueba automatizada de dependencias.
- **Un framework de inyección de dependencias**: dependencia extra y magia en tiempo de ejecución
  para una CLI pequeña; una raíz de composición explícita es más fácil de leer y de probar.
- **Una única herramienta de verificación**: import-linter por sí solo no cubre la regla de
  "solo biblioteca estándar" para imports no externos; la prueba AST por sí sola no modela el
  orden de capas ni la independencia de los adaptadores.
