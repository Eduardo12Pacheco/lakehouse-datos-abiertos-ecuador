# Contrato del artefacto y versionado

El artefacto publicado es una interfaz pública. `artifact_contract.json` registra las tablas,
los granos y las columnas tipadas en las que los consumidores pueden confiar, y
`lakehouse contract check` compara ese contrato versionado con el esquema que realmente
materializa el warehouse.

El contrato vigente es la versión **1.0.0** y describe 14 tablas: 7 dimensiones, 3 hechos y
4 marts analíticos. La versión del artefacto iguala la versión del contrato.

## Archivo

`src/ecuador_lakehouse/artifact_contract.json` viene dentro del wheel. Su forma es:

```json
{
  "schema_version": 1,
  "contract_version": "1.0.0",
  "artifact_name": "ecuador-lakehouse",
  "tables": [
    {
      "name": "dim_date",
      "kind": "dim",
      "grain": "month",
      "columns": [
        {"name": "month_key", "type": "INTEGER"},
        {"name": "month_start_date", "type": "DATE"}
      ]
    }
  ]
}
```

`kind` es uno de `dim`, `fct` o `mart`. `grain` es una descripción legible de una fila.
`columns` está ordenado, y cada tipo es el tipo DuckDB que debe producir el modelo.

Solo los marts están sujetos a contrato. Los modelos de staging e intermediate, la capa raw,
el sitio del reporte y el esquema del manifest no forman parte de esta interfaz: los
consumidores reciben los marts y el manifest.

## Reglas de semver

La versión del artefacto usa versionado semántico. Las reglas se refieren a lo que un
consumidor puede observar: tablas, columnas, tipos y el significado de un valor.

| Cambio | Tipo | Incremento requerido |
| --- | --- | --- |
| Eliminar una tabla | incompatible | **MAJOR** |
| Renombrar una tabla | incompatible (el nombre anterior desaparece) | **MAJOR** |
| Eliminar una columna | incompatible | **MAJOR** |
| Renombrar una columna | incompatible (el nombre anterior desaparece) | **MAJOR** |
| Cambiar el tipo de una columna (por ejemplo `INTEGER` a `BIGINT`) | incompatible | **MAJOR** |
| Cambiar el grano de una tabla o el significado/unidad de una columna | incompatible por política | **MAJOR** |
| Agregar una tabla | aditivo | **MINOR** |
| Agregar una columna | aditivo | **MINOR** |
| Agregar un valor permitido o ampliar la cobertura sin cambiar el esquema | aditivo | **MINOR** |
| Corregir un error, rellenar filas erróneas o mejorar descripciones sin cambio de esquema | corrección | **PATCH** |

Un incremento **MINOR** es seguro para un consumidor que selecciona columnas por nombre: las
columnas existentes siguen presentes con los mismos nombres y tipos. Un incremento **MAJOR**
obliga al consumidor a actualizar sus consultas. Un incremento **PATCH** no requiere ningún
cambio.

`contract check` realiza la parte mecánica de esa tabla:

```text
committed table missing in warehouse    -> BREAKING: table <name> removed
committed column missing                -> BREAKING: <table>.<column> removed
committed column type differs           -> BREAKING: type changed from A to B
warehouse table absent from contract    -> ADDITIVE: table <name> added
warehouse column absent from contract   -> ADDITIVE: <table>.<column> added
```

Cuando existe alguna entrada incompatible, el incremento requerido es MAJOR; si no, cualquier
entrada aditiva requiere MINOR; si no, no se requiere incremento. El comando termina con
código 8 siempre que el diff no esté vacío, porque el contrato versionado ya no describe el
warehouse. Actualice el contrato (e increméntelo según las reglas) hasta que `contract check`
vuelva a estar limpio.

Los cambios de grano y de semántica no son detectables mediante `information_schema`, así que
siguen siendo responsabilidad de la revisión. Aun así, siguen la regla MAJOR: un consumidor que
suma `collected_usd` por mes no debe recibir en silencio otra unidad ni otro significado de
fila.

## Cómo cambiar el contrato

1. Cambie el modelo dbt y su contrato aplicado; luego, reconstruya y pruebe con
   `lakehouse build`.
2. Ejecute `lakehouse contract check`. Lea las entradas incompatibles y aditivas que se
   reporten. Determine el nivel requerido con la tabla anterior.
3. Edite `src/ecuador_lakehouse/artifact_contract.json`: actualice `contract_version` y las
   entradas afectadas de `tables`, `grain` o `columns`. La versión del artefacto se lee de este
   archivo, así que el directorio publicado y el manifest avanzan juntos.
4. Vuelva a ejecutar `lakehouse build` y `lakehouse contract check`; debe informar que la
   versión versionada coincide con las tablas del warehouse.
5. Publique y verifique:
   `lakehouse publish --out dist-artifact` y
   `lakehouse verify dist-artifact/ecuador-lakehouse-<version>`.
6. Registre el motivo y el incremento en `CHANGELOG.md` y en el pull request. Un cambio
   incompatible también puede requerir una nota de migración para los consumidores conocidos.

La versión del contrato es independiente de la versión del paquete. Una corrección de un parser
puede publicarse como el paquete `0.1.1` mientras el producto de datos sigue en `1.0.0`; agregar
una columna a un mart puede llevar el producto de datos a `1.1.0` sin una publicación del
paquete, si los datos se republican desde el mismo código.

## Verificación y compatibilidad

Existen dos comprobaciones distintas que no son intercambiables:

- `lakehouse contract check` compara el **contrato versionado** con el **esquema actual del
  warehouse**. Responde a la pregunta "¿este build puede mantener la interfaz publicada?" y se
  ejecuta antes de publicar.
- `lakehouse verify DIR` comprueba un **artefacto ya publicado** contra su propio manifest, sus
  checksums y sus huellas digitales lógicas. Responde a la pregunta "¿este directorio está
  íntegro?" y no lee el warehouse.

Un consumidor debe:

1. verificar el artefacto una vez con `lakehouse verify DIR`;
2. leer `manifest.json` y comprobar `schema_version == "1.0"`;
3. fijar el incremento **MAJOR** del artefacto y los nombres exactos de tablas y columnas que
   usa;
4. tratar un nuevo **MINOR** como compatible hacia atrás y un nuevo **MAJOR** como una migración.

El esquema del manifest se versiona mediante `schema_version`. Un cambio futuro en el conjunto
de campos del manifest sería un contrato aparte: incrementaría `schema_version`, y los
consumidores deben verificarlo antes de asumir que existen los campos.

Consulte [ARTIFACT.md](ARTIFACT.md) para la estructura del contenido y los pasos de verificación,
y [ADR 0007](adr/0007-artifact-contract-and-versioning.md) para el registro de la decisión.
