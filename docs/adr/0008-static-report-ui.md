# ADR 0008 - Interfaz de reporte estático de varias páginas

## Estado

Aceptada (2026-11-20, tarea T12).

## Contexto

El lakehouse debe mostrar sus resultados a alguien que no tiene un notebook abierto: recaudación de
impuestos, precios, datos macro, la compuerta de calidad y la procedencia de las fuentes. La interfaz
debe funcionar sin conexión en Linux, Windows y macOS, viajar dentro del mismo wheel que la CLI,
funcionar tanto desde `file://` como desde un servidor local, admitir temas claro y oscuro y nunca
descargar recursos desde una CDN (S2, S16).

Candidatos considerados:

- **Streamlit.** Rápido para prototipar, pero agrega un runtime de servidor, un árbol grande de
  dependencias y un aspecto difícil de llevar a calidad de producto. Además, contradice el nivel L1
  "instalar una CLI, sin servicios".
- **Evidence.dev.** Excelente para reportes de BI, pero necesita Node/npm y una cadena de build, así que
  no puede distribuirse con `uv tool install`.
- **Una SPA con React/Vite.** Flexible, pero agrega un paso de build con Node y un pipeline de bundles
  del lado del cliente para un reporte de solo lectura; excesivo para seis páginas.
- **Plantillas Jinja2 + ECharts incluido en el paquete.** Archivos HTML planos, un servidor HTTP de la
  biblioteca estándar, sin paso de build y sin dependencia de runtime más allá de Jinja2, que el proyecto
  ya usa. Los gráficos se renderizan en el cliente a partir de JSON incrustado en cada página, así que los
  mismos archivos funcionan desde `file://`.

## Decisión

1. **Generar HTML estático con Jinja2.** `application.use_cases.build_report` orquesta un puerto de solo
   lectura `ReportReader` y un puerto `ReportRenderer`. `adapters.report.renderer.JinjaReportRenderer`
   escribe `index.html`, `tax.html`, `prices.html`, `macro.html`, `quality.html`, `sources.html` y un
   `empty.html` explícito, y copia los recursos a `site/assets/`.
2. **Incrustar datos, no solicitudes.** El lector agrega los datos de cada página en una sola conexión de
   solo lectura a DuckDB, y el renderizador serializa los datos de cada página en un bloque
   `<script type="application/json" id="data-<page>">`. Ninguna página llama a `fetch`, así que `file://` y
   `http://127.0.0.1` se comportan de forma idéntica.
3. **Incluir ECharts 6.1.0.** `scripts/vendor_echarts.py` descarga el bundle fijado, verifica el tamaño y el
   SHA-256 (`b66b25ae…fd0`, 1,121,883 bytes) y lo escribe en los recursos del paquete, junto con la licencia
   Apache-2.0 y el aviso. No se contacta ninguna CDN en tiempo de ejecución, y una prueba fija el checksum.
4. **Tokens de diseño y contraste.** `tokens.css` define propiedades personalizadas para los temas claro y
   oscuro; `tests/unit/test_contrast.py` calcula las razones WCAG a partir del CSS y exige 4.5:1 para texto y
   3:1 para colores de gráficos en ambos temas.
5. **Accesible por construcción.** Enlace de salto, landmarks header/nav/main/footer, anillos de foco
   visibles, selects operables con teclado y encabezados de tabla ordenables, `aria-sort`, `<noscript>`,
   estados vacío y de error explícitos, y soporte de `prefers-reduced-motion`.
6. **Servidor solo de loopback.** `lakehouse serve` escucha en `127.0.0.1` en el puerto 15080 por defecto
   (configurable con `--host/--port` y `LAKEHOUSE_SERVE_*`), solo acepta direcciones de loopback y sirve
   exclusivamente desde el sitio generado. Si el sitio no existe, se genera primero; si falta el warehouse,
   el comando termina con código 2 y un mensaje accionable.
7. **Los datos del reporte quedan fuera del contrato del artefacto.** La interfaz lee los marts, pero el
   reporte en sí no es un producto de datos publicado; el contrato del artefacto y las garantías de
   determinismo cubren solo el artefacto DuckDB/Parquet (ADR 0007).

## Consecuencias

- El reporte es un conjunto de archivos que pueden adjuntarse a un release, abrirse desde una memoria USB
  o servirse con cualquier host de archivos estáticos sin cambiar una línea.
- La interfaz es probable sin navegador: los bloques JSON, las comprobaciones de enlaces locales, el cálculo
  de contraste y el servidor de la biblioteca estándar están cubiertos por pytest; las pruebas e2e con
  Playwright llegan en T13.
- Agregar una página implica agregar una plantilla, una entrada en el renderizador y una consulta de datos;
  el shell, el tema y la navegación son compartidos.
- ECharts agrega unos 1.1 MB al wheel, un costo aceptado para un reporte genuinamente offline e interactivo.
- El servidor no pretende ser un servidor de producción: es de un solo usuario, solo loopback, sin
  autenticación y sin TLS. Esto coincide con la restricción local-first.

## Alternativas consideradas

- **Streamlit**, rechazado: runtime pesado, requiere servidor y ofrece un estilo limitado.
- **Evidence.dev**, rechazado: cadena de herramientas de Node y el sitio generado necesita un build.
- **SPA con React**, rechazado: herramientas adicionales para un reporte de solo lectura.
- **Gráficos con Matplotlib/PNG**, rechazado: las imágenes estáticas no admiten filtros por año o por
  ciudad, ni el cambio de tema, sin regenerar archivos.
