# Política de seguridad

## Versiones soportadas

El proyecto está en una versión previa a 1.0. Las correcciones de seguridad se aplican a la
última versión publicada en `main`; las instantáneas antiguas no se mantienen. El artefacto de
datos publicado sigue su propia versión de contrato (ver [docs/CONTRACT.md](docs/CONTRACT.md));
una corrección de seguridad del software puede publicarse sin cambiar el contrato de datos.

## Reportar una vulnerabilidad

No abra un issue público para problemas de seguridad. Use la pestaña **Security** del repositorio
para abrir un aviso privado
(<https://github.com/Eduardo12Pacheco/lakehouse-datos-abiertos-ecuador/security/advisories/new>)
e incluya:

- la versión y el comando afectados,
- una reproducción mínima,
- el impacto que espera,
- cualquier mitigación conocida.

Se espera un acuse de recibo en pocos días. Cuando haya una corrección disponible, se publica un
nuevo release y el aviso se divulga, con crédito si se desea. Conceda al proyecto un plazo razonable
para publicar una corrección antes de divulgar los detalles.

## Alcance

La herramienta es local-first y de un solo usuario. Están dentro del alcance:

- el paquete de Python, la CLI y la muestra incluida,
- el proyecto dbt y la compuerta de calidad de datos,
- el sitio de reporte estático y `lakehouse serve`,
- el formato del artefacto publicado y `lakehouse verify`,
- los workflows de CI y de release de este repositorio.

Quedan fuera de alcance: las vulnerabilidades de DuckDB, dbt, httpx, Jinja2, ECharts o del sistema
operativo anfitrión (repórtelas al proyecto upstream, pero infórmenos si el uso de este proyecto
las vuelve explotables), y los ataques que requieren una cuenta local ya comprometida o acceso
físico.

## Garantías de diseño

### Sin credenciales ni cuentas

La herramienta se ejecuta localmente y nunca requiere credenciales, claves de API, tokens ni
cuentas. No existe variable de entorno secreta, flujo de inicio de sesión ni API de pago. Las
descargas usan únicamente hosts de origen públicos y sin clave.

### Descargas verificadas y restringidas

- Las solicitudes se restringen a una lista de permitidos de hosts públicos de datos:
  `descargas.sri.gob.ec`, `www.ecuadorencifras.gob.ec`, `www.datosabiertos.gob.ec` y
  `datosabiertos.gob.ec`.
- Las redirecciones se validan contra la misma lista de permitidos; una redirección fuera de ella
  se rechaza.
- Cada archivo tiene un límite de 300 MiB y se verifica contra un SHA-256 fijado en
  `sources.lock.json` antes de usarse. Una discrepancia en un archivo inmutable genera
  `ChecksumMismatchError` (código 3).
- El único archivo mutable es el año SRI en curso. Un checksum modificado emite una advertencia y
  se registra como nueva versión solo con `--accept-new-vintage`.
- Las descargas pueden reanudarse desde un archivo `.part`, y un archivo parcial o con
  discrepancias nunca se carga en el warehouse.

### Manejo de archivos comprimidos

La fuente del INEC es un ZIP anidado. Antes de escribir cualquier byte, los miembros se verifican
por:

- recorrido de rutas (`..`), rutas absolutas, barras invertidas y enlaces simbólicos;
- un límite de 300 MiB descomprimidos por miembro y de 600 MiB en total;
- una razón de descompresión superior a 200x, que se rechaza como bomba de descompresión.

Las infracciones generan `UnsafeArchiveError`, un `SourceSchemaError` con código de salida 4.

### Servidor local

`lakehouse serve` se vincula solo a loopback (por defecto `127.0.0.1:15080`) y sirve un directorio
estático generado. No tiene autenticación ni TLS, y rechaza direcciones de vinculación que no sean
de loopback. No lo exponga mediante una interfaz pública ni un proxy inverso. El manejador estático
rechaza el recorrido de rutas.

### Integridad del artefacto

Los artefactos publicados se autoverifican. `lakehouse verify DIR` comprueba `SHA256SUMS`, los
esquemas y conteos de filas de Parquet y DuckDB, y el `content_sha256` lógico de cada tabla, y
termina con código 8 ante cualquier discrepancia. El archivo DuckDB contiene solo el esquema público
`marts` y una pequeña tabla `meta.build_info`; los esquemas raw, staging e intermediate no se
publican. Los consumidores deben verificar un artefacto una vez antes de usarlo.

### Licencias de datos

Solo se incluyen y publican fuentes CC BY / CC BY 4.0. Los conjuntos de datos no comerciales del
BCE se excluyen deliberadamente, de modo que el artefacto sigue siendo redistribuible con
atribución. Vea [docs/DATA.md](docs/DATA.md) y
[docs/adr/0004-sample-strategy-and-licensing.md](docs/adr/0004-sample-strategy-and-licensing.md).

### Cadena de suministro y CI

- `gitleaks` escanea todo el historial de git en la CI; no se almacena ningún secreto en el
  repositorio ni en los fixtures.
- `pip-audit` audita la exportación bloqueada de dependencias en la CI. Un hallazgo conocido debe
  documentarse con una justificación y una nota de seguimiento; nunca se ignora en silencio.
- Las GitHub Actions están fijadas por versión mayor, usan bloques `permissions` de mínimo
  privilegio, y el workflow de release exige que el workflow de CI completo pase antes de poder
  crear un release.
- El wheel y el sdist publicados se construyen en la CI a partir de un entorno bloqueado.
- Dependabot supervisa `github-actions` y `uv` semanalmente.

### Comandos de verificación

```bash
uv run python scripts/dev.py check
uv lock --check
gitleaks detect --no-banner
uv export --no-hashes --no-emit-project > /tmp/requirements.txt
uvx pip-audit --disable-pip --no-deps -r /tmp/requirements.txt
```

Si cree que alguna de estas garantías puede eludirse, repórtelo en privado por el canal indicado
arriba.
