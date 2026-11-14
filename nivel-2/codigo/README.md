# Costeo de El Término Medio · nivel 2

`costeo.py` calcula el costo de ingredientes por porción de los 50 platos de la carta al **31/10/2026**. Genera `nivel-2/costos.csv`. El mismo script, con `--nivel 1`, genera `nivel-1/costos.csv` al 10/08/2026.

Usa solo la biblioteca estándar de Python 3 (sin dependencias ni entornos virtuales). También lee los PDF de las facturas y notas sin bibliotecas externas.

## Entradas

La carpeta que se pasa con `--datos` es la del material entregado:

| Archivo | Qué aporta |
|---|---|
| `recetas.json` | 50 platos (rinden 1 porción) y 15 subrecetas `S01`–`S15` (rinden una tanda en g o ml) |
| `catalogo.csv` | Equivalencia de cada presentación **por producto** (por ejemplo, `bolsa` de papa = 5000 g, `bolsa` de harina = 25000 g, `unidad` de aceite = 1500 ml) |
| `rendimientos.csv` | Coeficientes limpio/bruto y cocido/limpio por producto |
| `facturas/F-001.pdf` … `F-040.pdf` | Renglones con cantidad, presentación, precio, bonificación y neto. El orden de las columnas cambia según el proveedor: el script las ubica por el encabezado |
| `notas/NC-001.pdf` … `NC-004.pdf` | Notas de crédito: factura y renglón que ajustan, concepto, cantidad devuelta e importe |

## Cómo reproduce el cálculo

1. **Elección de factura por producto.** Toma la última factura con fecha ≤ 31/10/2026. Si dos facturas tienen la misma fecha, gana el identificador alfanuméricamente mayor. Resultado: F-037 (verdura), F-038 (carnes), F-039 (almacén) y F-040 (lácteos), todas del 24/10/2026.
2. **Notas asociadas.** Aplica solo las notas con fecha ≤ 31/10/2026 que apuntan a la factura y renglón elegidos. No las trata como compras nuevas.
   - *Bonificación*: resta el importe y deja igual la cantidad. Es el caso de NC-003, que ajusta F-039 r3 (lenteja) en $2384,64.
   - *Devolución*: resta el importe y las unidades devueltas. Es el caso de NC-004, que ajusta F-040 r5 (huevo): 36 unidades y $10784,53.
   - NC-001 (F-005) y NC-002 (F-022) ajustan facturas que no son las vigentes, así que no cambian el costo.
3. **Precio efectivo.** Es el neto ajustado dividido por la cantidad equivalente. La cantidad equivalente es la cantidad × la equivalencia de esa presentación de ese producto en el catálogo, menos lo devuelto. Se usa el neto impreso en el renglón, que ya incluye la bonificación. No se agregan IVA, fletes ni otros conceptos.
4. **Cantidad bruta por ingrediente.** Las recetas expresan cantidades finales según el `estado`:
   - `bruto`: se usa tal cual.
   - `limpio`: cantidad ÷ (limpio/bruto).
   - `cocido`: cantidad ÷ (limpio/bruto × cocido/limpio). Arroz y lenteja tienen cocido/limpio > 1 porque absorben agua.
   - `preparado`: es una subreceta. Se toma el costo de su tanda ÷ su rendimiento × la cantidad usada. Las subrecetas se resuelven en cadena (por ejemplo, Ragú S14 → Fondo rojo S13 → Salsa S01 + Caldo S02).
   - El agua que completa las tandas no tiene costo.
5. **Redondeo.** Se calcula con `Decimal` a 50 dígitos sin redondeos intermedios. Solo el costo final por porción se redondea a 2 decimales con `ROUND_HALF_UP`.
6. **Salida.** Escribe `plato,costo_por_porcion`, una fila por plato `P01`–`P50`. Las subrecetas no van como filas.

## Ejecución

```bash
python3 costeo.py --nivel 2 --datos ruta/a/nivel-2 --salida ../costos.csv
python3 costeo.py --nivel 1 --datos ruta/a/nivel-1 --salida ../../nivel-1/costos.csv
```

`--detalle` imprime la factura y el renglón elegidos para cada producto, el precio unitario efectivo y el costo sin redondear de cada plato.

## Control

Hicimos una segunda implementación independiente:
- lee las facturas con otro método (texto extraído de los PDF);
- calcula con fracciones exactas;
- expande cada plato a cantidades brutas de compra.

Dio los mismos 50 valores (y los 3 del nivel 1). Además, se revisaron a mano P02, P10, P22 y P42 con precios tomados de los PDF. También se comprobó que en las 320 líneas de factura el neto coincide con cantidad × precio × (1 − bonificación) y que la bonificación del 8 % respeta su umbral.
