# Costeo y márgenes de El Término Medio · nivel 3

`margenes.py` genera dos archivos:
- `nivel-3/costos.csv`: costo por porción al **31/10/2026** de los 50 platos.
- `nivel-3/margenes.csv`: unidades, ingreso neto, costo histórico y margen del trimestre agosto–octubre 2026, por plato.

Usa solo la biblioteca estándar de Python 3. Las recetas, el catálogo, los rendimientos, las facturas PDF y las notas se leen con las funciones de `nivel-2/codigo/costeo.py`, sin cambios de método.

## Entradas

| Entrada | Origen |
|---|---|
| `--nivel2` | Carpeta del nivel 2: `recetas.json`, `catalogo.csv`, `rendimientos.csv`, `facturas/F-001…F-040.pdf`, `notas/NC-001…NC-004.pdf`. Las recetas se conservan |
| `--nivel1` (opcional) | Carpeta del nivel 1. Sus facturas F-001…F-005 repiten las del nivel 2: el script verifica que sean idénticas y no las cuenta dos veces |
| `compras_imagenes.csv` | Transcripción de las 27 imágenes nuevas (detalle abajo). Las imágenes no están en el repositorio |
| `--caja` | `2026-08.csv`, `2026-09.csv`, `2026-10.csv`, `articulos.csv`, `combos.csv`. Los archivos de caja no están en el repositorio |

### Imágenes → `compras_imagenes.csv`

Las imágenes son de dos tipos:
- 12 comprobantes manuscritos, `M-001` a `M-012`, de los días 14/08, 12/09 y 28/10.
- 15 tickets impresos, `T-001` a `T-015`, de los días 20/08, 20/09 y 30/10.

Se procesaron con OCR local (RapidOCR / ONNX en la máquina, sin servicios externos) y después cada renglón se revisó contra la imagen.

Cuando había tachaduras se tomó el valor vigente: los precios unitarios corregidos y el "Total" en lugar de la "Suma" tachada.

Cada renglón se validó con tres controles:
- `neto = cantidad × precio × (1 − bonificación)`, redondeado al centavo;
- la bonificación del 8 % solo con 4 o más presentaciones, o desde 2000 g/ml;
- la suma de renglones igual al total del comprobante.

Los 120 renglones y los 27 totales cierran. El script vuelve a comprobar los totales al leer el CSV.

## Costo por porción (`costos.csv`)

Se mantiene el método del nivel 2 sobre el conjunto unido de compras (F + M + T):
- por producto, la última factura con fecha ≤ 31/10/2026;
- si hay empate de fecha, el identificador alfanuméricamente mayor;
- las notas con fecha ≤ corte aplicadas a su factura y renglón;
- el neto dividido por la cantidad equivalente del catálogo;
- los rendimientos y las subrecetas;
- redondeo a 2 decimales solo al final.

Hay empates reales en los tickets: T-001 y T-005 (20/08), T-006 y T-010 (20/09), T-011 y T-015 (30/10). En cada caso gana el identificador mayor.

## Márgenes (`margenes.csv`)

Según el manual de caja:
- **VTA**: el código de caja se traduce al plato con `articulos.csv`, respetando la vigencia (extremos inclusivos). Por ejemplo, A1500 y B3100 son ambos P01.
- **COM**: el cobro neto (`importe_bruto − descuento`) del combo se reparte entre sus platos en proporción a `peso_ingreso`, sin redondear. Las unidades y el costo usan las unidades de cada componente × la cantidad del combo.
- **REV**: anula su movimiento de `referencia`. Con sus mismos importes y unidades, resta ingreso, unidades y costo. Conserva el reparto y la fecha de costo del original. No se elimina el original, así que la reversión no se descuenta dos veces.
- **EXT**: propina del personal. No entra en la facturación de los platos.
- **Costo histórico**: cada venta se costea con las compras de fecha ≤ fecha de la venta y las notas emitidas hasta esa fecha. Se usa la misma regla de última factura y desempate. Las primeras ventas (01/08) ya tienen la compra del 01/08 de los 32 productos.
- **Totales**: `unidades_vendidas` es el neto del trimestre. `ingreso_neto` y `costo` son sumas exactas redondeadas a 2 decimales. `margen = (ingreso_neto − costo) / ingreso_neto` con 6 decimales (0.000000 si el ingreso es 0).

## Ejecución

```bash
python3 margenes.py --nivel2 ruta/nivel-2 --nivel1 ruta/nivel-1 --caja ruta/nivel-3/caja --salida ..
```

## Control

Se hizo una implementación independiente, que:
- calcula con fracciones exactas;
- lee los PDF con otra herramienta;
- desarma cada plato hasta las cantidades brutas;
- agrega las ventas por día y por plato.

Dio los mismos 50 costos y las mismas 50 filas de margen, carácter por carácter. Además se verificaron a mano:
- el costo de P01 al 16/08 con los precios de M-001, M-002, M-003, F-005 y F-007;
- el efecto de las notas de crédito en su fecha (NC-001 el 09/08, NC-003 el 25/10, NC-004 el 26/10);
- las unidades e ingresos de P12 (solo VTA y REV) y de P01 (dos códigos de caja más el combo CB01).
