# ADR 0005 — SCD2 como modelo SQL determinista, no como snapshot de dbt

## Estado

Aceptada (2026-11-20).

## Contexto

El catálogo tributario cambia cada año: las líneas se introducen, se retiran, reaparecen tras
un hueco y (raramente) cambian de grupo. El esquema estrella necesita que `dim_tax_item` sea de
cambio lento, para que un hecho pueda apuntar a la versión exacta que era vigente en su año de
recaudación (S10, D15). Existen dos familias de opciones:

1. **Snapshot de dbt** (estrategia `check`/`timestamp`): historial gestionado por dbt, indexado
   por una clave única y una columna `updated_at`. Es con estado: en cada ejecución compara las
   filas actuales del origen con la tabla de snapshot previa, escribe las filas nuevas con
   `dbt_valid_from`/`dbt_valid_to` y depende de marcas de tiempo del reloj.
2. **Modelo SQL**: reconstruir las islas de versiones a partir de los datos crudos actuales en
   cada ejecución, derivando la vigencia solo de los datos.

El origen es un historial anual estático y no un flujo de solo adición. No existe una columna
`updated_at`, y la muestra incluida junto con los archivos completos se vuelven a descargar o a
parsear como particiones inmutables. Un snapshot mezclaría el historial de ejecuciones con el
historial de datos, y dos builds en una máquina limpia no necesariamente coincidirían si se
reutilizara la tabla de snapshot.

## Decisión

- **Implementar SCD2 como modelos SQL sobre el historial raw completo.**
  `int_tax_item_year_presence` construye una matriz de presencia densa por clave natural de
  impuesto y año cargado; `int_tax_item_versions` calcula gaps-and-islands sobre una serie anual
  generada desde la primera presencia de cada línea hasta el último año cargado. Se crea un límite
  de versión cada vez que `(lifecycle_status, tax_group_name)` difiere del año anterior.
- **La vigencia proviene de los datos, nunca del reloj.** `valid_from` es el 1 de enero del primer
  año de la isla, `valid_to` es el 31 de diciembre de su último año, y la última isla es abierta
  (`9999-12-31`). `is_current` equivale exactamente a `valid_to = 9999-12-31`. Hay una fila vigente
  por clave natural por construcción.
- **La clave natural es `(norm(IMPUESTO), norm(SUBGRUPO_IMPUESTO))`** según D15; el grupo es un
  atributo rastreado, así que un cambio de grupo inicia una nueva versión, mientras que los nombres
  para mostrar se toman del año más reciente en que la línea estuvo presente.
- **Los hechos se unen en el punto del tiempo.** `fct_tax_collection` une versiones por clave natural
  cuando el año del hecho está dentro de `[valid_from, valid_to]` y la versión está activa. Un hecho
  nunca puede apuntar a una versión inactiva ni a una versión fuera de su ventana de vigencia.
- **Con pruebas de propiedades sobre el modelo real.** Una prueba de Hypothesis carga matrices
  aleatorias de presencia y de grupo en un warehouse temporal, ejecuta `+dim_tax_item` mediante el
  runner real de dbt y verifica una versión vigente por clave, rangos contiguos sin superposición y
  exactamente una versión activa para cada `(ítem, año)` presente dentro del tramo cargado.
- **Las claves sustitutas son deterministas.** `tax_item_key` es
  `md5(tax_item_nk || '||' || valid_from)`, conforme a D11 y S15, de modo que dos builds producen las
  mismas claves.

## Consecuencias

- Positivo: determinista y sin repetición de ejecuciones; un reconstruido completo reproduce la
  misma dimensión y las mismas claves; no hay una tabla de snapshot con estado que conciliar; la
  vigencia se puede derivar solo de los datos, lo que ejercita la prueba de propiedades.
- Positivo: la definición de los límites de versión es SQL explícito que se puede probar
  unitariamente en dbt (continuidad, huecos, retiro, reclasificación, introducción tardía) en lugar
  de quedar oculta en los internos de dbt.
- Negativo: una edición real del historial del origen (a diferencia de una nueva partición anual)
  reescribe el historial afectado en el siguiente build. Esa es la semántica deseada: la capa raw es
  la fuente de verdad.
- Negativo: "inactiva hasta el último año cargado" significa que un ítem retirado antes del último
  año cargado conserva una versión inactiva abierta. Esto es inocuo, porque los hechos solo se unen
  con versiones activas, y preserva una fila vigente por clave.
- Medido sobre la muestra incluida: 245 claves naturales, una versión vigente por clave, sin cambios
  de grupo en 2017–2026; por lo tanto, el comportamiento con datos reales está dominado por
  introducción, retiro y huecos, tal como se documenta en D14.

## Alternativas consideradas

- **Snapshot de dbt (estrategia `check`)**: rechazado porque el origen no tiene columna
  `updated_at`, los snapshots tienen estado y dependen del historial de ejecuciones, y dos builds
  limpios divergirían si se reutilizara la tabla de snapshot. El modelo SQL determinista reconstruye
  las versiones a partir de los datos crudos.
- **Claves sustitutas generadas con `row_number()`**: rechazado porque el orden de las filas no forma
  parte del contrato de datos; D11 exige claves basadas en hash para que los builds coincidan.
- **Un seed de historial de versiones mantenido a mano**: rechazado porque se desviaría de los
  archivos crudos y no podría someterse a pruebas de propiedades contra el modelo real.
