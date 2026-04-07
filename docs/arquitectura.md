# Arquitectura

Este documento explica cómo funciona Artemis Monitor internamente, cómo fluyen los datos a través del sistema y cómo encaja cada componente.

## Visión General

Artemis Monitor es un dashboard de terminal a pantalla completa que consulta dos fuentes de datos de la NASA en un ciclo, parsea las respuestas y las renderiza usando Rich. El feed XML del DSN se parsea con una extensión en Rust por rendimiento.

```
                         ┌─────────────────────────┐
                         │      main.py (run)       │
                         │   bucle de eventos async │
                         └────────┬────────────────-┘
                                  │
                        asyncio.gather (concurrente)
                       ┌──────────┼──────────────┐
                       │          │              │
                       v          v              v
                  fetch_dsn   fetch_solar    fetch_geo
                       │      _flares       _storms
                       │          │              │
                       v          └──────┬───────┘
               dsn_parser.parse_dsn      │
               (Rust / PyO3)       space_weather.py
                       │           (_fetch_data)
                       │                 │
                       v                 v
              Feed XML del DSN     API REST DONKI de NASA
              eyes.nasa.gov        api.nasa.gov/DONKI
                       │                 │
                       └────────┬────────┘
                                │
                                v
                         ┌─────────────┐
                         │   ui.py     │
                         │ build_layout│
                         └──────┬──────┘
                                │
                                v
                         Rich Live display
                         (TUI a pantalla completa)
```

## Desglose de Módulos

### `artemis/main.py` -- Punto de Entrada y Ciclo de Consultas

Este es el núcleo de la aplicación. Hace tres cosas:

1. **`fetch_dsn()`** -- Hace un GET al feed XML del DSN y pasa el XML crudo como string al parser en Rust.
2. **`fetch_all()`** -- Ejecuta `fetch_dsn()`, `fetch_solar_flares()` y `fetch_geomagnetic_storms()` de forma concurrente usando `asyncio.gather`. Las tres peticiones HTTP ocurren en paralelo.
3. **`run()`** -- El bucle principal. Abre un contexto `Rich.Live` en modo pantalla completa y ejecuta indefinidamente:
   - Llama a `fetch_all()` para obtener datos frescos
   - En caso de error, conserva los últimos datos buenos y establece un mensaje de error
   - Pasa todo a `build_layout()` y actualiza la pantalla
   - Duerme por `REFRESH_INTERVAL` segundos

`main()` envuelve `asyncio.run()` y captura `KeyboardInterrupt` para salir limpiamente.

**Estrategia de manejo de errores:** El bloque `except` en el bucle captura errores HTTP, timeouts y excepciones inesperadas por separado. En caso de fallo, el dashboard sigue mostrando los últimos datos exitosos y muestra el error en la barra de pie de página. Nunca se cae por un problema transitorio de red.

### `artemis/config.py` -- Configuración

Carga variables de entorno desde `.env` usando `python-dotenv`. Tres configuraciones:

| Variable | Tipo | Default | Usado por |
|---|---|---|---|
| `NASA_API_KEY` | `str` | `DEMO_KEY` | `space_weather.py` |
| `REFRESH_INTERVAL` | `int` | `10` | `main.py` (pausa entre consultas) |
| `LAUNCH_DATE` | `datetime` | `2026-06-01T00:00:00+00:00` | `ui.py` (cuenta regresiva) |

`load_dotenv()` se ejecuta al importar, así que cualquier módulo que importe desde `config` recibe los valores ya resueltos.

### `artemis/space_weather.py` -- Cliente de NASA DONKI

Se comunica con la [API DONKI de NASA](https://api.nasa.gov/) (Base de Datos de Notificaciones, Conocimiento e Información del Clima Espacial).

**Helper interno:**

```python
async def _fetch_data(endpoint: str, days: int) -> list[dict]
```

Construye un rango de fechas (`hoy - days` hasta `hoy`), hace un GET async a `https://api.nasa.gov/DONKI/{endpoint}` y devuelve la respuesta JSON como lista de diccionarios.

**Funciones públicas:**

- `fetch_solar_flares()` -- Llama a `_fetch_data("FLR", days=1)`. Devuelve eventos de llamaradas solares de las últimas 24 horas.
- `fetch_geomagnetic_storms()` -- Llama a `_fetch_data("GST", days=7)`. Devuelve eventos de tormentas geomagnéticas de los últimos 7 días.

Ambas usan la API key de `config.NASA_API_KEY`. La `DEMO_KEY` funciona pero tiene límite de ~30 peticiones/hora.

### `artemis/ui.py` -- Interfaz de Terminal

Construye el layout de Rich. Lógica pura de renderizado, sin I/O.

**Estructura del layout:**

```
┌──────────────────────────────────────────────────┐
│ header (size=3)                                  │
│   Cuenta regresiva o "MISSION ACTIVE"            │
├────────────────────────┬─────────────────────────┤
│ dsn (flexible)         │ weather (flexible)      │
│   Tabla de antenas     │   Resumen clima espacial│
├────────────────────────┴─────────────────────────┤
│ footer (size=1)                                  │
│   Timestamp de última actualización o error      │
└──────────────────────────────────────────────────┘
```

**Funciones:**

- `build_countdown()` -- Calcula `LAUNCH_DATE - now`. Si es positivo, muestra `Xd Xh Xm Xs`. Si es cero o negativo, muestra "MISSION ACTIVE".
- `build_dsn_panel(dishes)` -- Renderiza una tabla de antenas DSN. Cada fila muestra nombre de antena, nave objetivo, azimut y elevación. Muestra "No data" si la lista está vacía.
- `build_weather_panel(flares, storms)` -- Resumen de dos filas. Muestra conteo + icono de advertencia si hay eventos, o "Clear"/"None" con checkmark si está tranquilo.
- `build_layout(dishes, flares, storms, error=None)` -- Ensambla los tres paneles en un `Layout`. Si `error` está definido, el footer muestra el error en lugar del timestamp.

### `crates/dsn_parser/` -- Parser XML en Rust

Un módulo de extensión Python escrito en Rust usando [PyO3](https://pyo3.rs/) y [quick-xml](https://docs.rs/quick-xml/).

**¿Por qué Rust?** El feed DSN de NASA es XML. Parsear XML en Python es lento comparado con el resto de la app. El parser en Rust lo maneja en microsegundos.

**Cómo funciona:**

1. `parse_dsn_xml(xml: &str) -> Vec<DishStatus>` -- Función interna de Rust. Itera eventos XML usando `quick-xml::Reader`:
   - En tag de inicio `<dish>`: extrae `name`, `azimuthAngle`, `elevationAngle` de los atributos
   - En `<target>` dentro de un dish: extrae el atributo `name`, filtra valores vacíos y `"none"`
   - En tag de cierre `</dish>`: empuja el `DishStatus` completado al vector de resultados

2. `parse_dsn(py, xml: &str) -> PyResult<PyList>` -- La `#[pyfunction]` expuesta a Python. Llama a `parse_dsn_xml`, luego convierte cada struct `DishStatus` en un diccionario de Python:

```python
# Lo que ve Python:
[
    {
        "name": "DSS-14",        # nombre de antena
        "azimuth": 245.3,        # grados
        "elevation": 36.7,       # grados
        "targets": ["Voyager 1"] # lista de nombres de naves
    },
    ...
]
```

**Sistema de build:** Usa [maturin](https://www.maturin.rs/) para compilar el código Rust en un `.so` e instalarlo como paquete Python. Está registrado como miembro del workspace de uv, así que `uv sync` lo maneja automáticamente.

## Flujo de Datos: Un Ciclo de Refresco

1. `run()` llama a `fetch_all()`
2. `asyncio.gather` dispara tres peticiones HTTP async en paralelo:
   - `GET https://eyes.nasa.gov/dsn/data/dsn.xml` (feed DSN)
   - `GET https://api.nasa.gov/DONKI/FLR?startDate=...&endDate=...&api_key=...`
   - `GET https://api.nasa.gov/DONKI/GST?startDate=...&endDate=...&api_key=...`
3. La respuesta XML del DSN pasa a `dsn_parser.parse_dsn()` (Rust) que devuelve una lista de dicts
4. Las respuestas JSON de DONKI se devuelven tal cual (ya son `list[dict]`)
5. Los tres resultados se pasan a `build_layout()` que construye el árbol de layout de Rich
6. `live.update()` renderiza el layout en la terminal
7. `asyncio.sleep(REFRESH_INTERVAL)` espera antes del siguiente ciclo

Si alguna petición falla, el error se captura, se conservan los últimos datos exitosos y el mensaje de error reemplaza el timestamp del footer.

## Estructura del Workspace

El proyecto usa un workspace de uv con dos miembros:

```toml
# root pyproject.toml
[tool.uv.workspace]
members = ["crates/dsn_parser"]

[tool.uv.sources]
dsn-parser = { workspace = true }
```

- **Paquete raíz (`artemis-monitor`)** -- La aplicación Python. Se construye con hatchling. Declara `dsn-parser` como dependencia.
- **Miembro del workspace (`dsn-parser`)** -- La extensión Rust. Se construye con maturin. Tiene su propio `pyproject.toml` y `Cargo.toml`.

`uv sync` construye e instala ambos. Para desarrollo en el lado Rust, usa `maturin develop` dentro de `crates/dsn_parser/` para recompilar sin hacer un sync completo.

## Verificación de Tipos

La extensión Rust no tiene código fuente Python, así que los verificadores de tipos (basedpyright) no pueden ver sus exports. El archivo stub `typings/dsn_parser/__init__.pyi` provee la firma de tipos:

```python
def parse_dsn(xml: str) -> list[dict[str, object]]: ...
```

Esto se configura via `pyrightconfig.json` con `"stubPath": "typings"`.
