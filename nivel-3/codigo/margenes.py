#!/usr/bin/env python3
"""Nivel 3 de El Término Medio: costo por porción al 31/10/2026 y márgenes del trimestre.

Reutiliza la lectura de recetas, catálogo, rendimientos y PDFs del nivel 2
(`nivel-2/codigo/costeo.py`). Suma las compras transcriptas por OCR local
(`compras_imagenes.csv`) y procesa la exportación de caja.

Solo biblioteca estándar. Decimal con 50 dígitos; ROUND_HALF_UP únicamente al escribir.

Uso:
    python3 margenes.py --nivel2 <carpeta nivel-2> --caja <carpeta nivel-3/caja> \
        [--nivel1 <carpeta nivel-1>] --salida <carpeta nivel-3>
"""
import argparse
import csv
import sys
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent.parent / "nivel-2" / "codigo"))
import costeo as n2  # noqa: E402  (lectores y costeo de recetas del nivel 2)

getcontext().prec = 50
CORTE = "2026-10-31"
CENT = Decimal("0.01")
MICRO = Decimal("0.000001")


# ------------------------------------------------------------------ compras
def compras_imagenes(ruta):
    """Facturas manuscritas (M-xxx) y tickets (T-xxx) transcriptos y validados."""
    docs = {}
    with open(ruta, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = docs.setdefault(r["documento"], {"id": r["documento"], "fecha": r["fecha"],
                                                 "renglones": [], "total": Decimal(r["total_documento"])})
            d["renglones"].append({
                "renglon": int(r["renglon"]), "producto": r["producto"],
                "cantidad": Decimal(r["cantidad"]), "presentacion": r["presentacion"],
                "neto": Decimal(r["neto"]),
            })
    for d in docs.values():  # control: la suma de renglones es el total del comprobante
        assert sum(x["neto"] for x in d["renglones"]) == d["total"], d["id"]
    return list(docs.values())


def unir_compras(*lotes):
    """Une lotes por identificador. Un comprobante repetido entre lotes debe ser idéntico."""
    por_id = {}
    for lote in lotes:
        for fac in lote:
            clave = [(r["renglon"], r["producto"], r["cantidad"], r["presentacion"], r["neto"]) for r in fac["renglones"]]
            if fac["id"] in por_id:
                previo = por_id[fac["id"]]
                assert previo["fecha"] == fac["fecha"] and previo["_clave"] == clave, fac["id"]
                continue
            por_id[fac["id"]] = {**fac, "_clave": clave}
    return list(por_id.values())


# ---------------------------------------------------------- costo por fecha
class Costeador:
    def __init__(self, facturas, notas, catalogo, rend, recetas):
        self.facturas, self.notas = facturas, notas
        self.catalogo, self.rend, self.recetas = catalogo, rend, recetas
        self._cache = {}

    def costos_al(self, fecha):
        """Costo por porción de cada plato con compras y notas de fecha <= `fecha`."""
        if fecha not in self._cache:
            precios = n2.precios_efectivos(self.facturas, self.notas, self.catalogo, fecha)
            memo = {}
            self._cache[fecha] = {
                c: n2.costo_receta(c, self.recetas, precios, self.rend, self.catalogo, memo) / Decimal(r["rendimiento"])
                for c, r in self.recetas.items() if r["unidad_rendimiento"] == "porción"
            }
        return self._cache[fecha]


# --------------------------------------------------------------------- caja
def leer_caja(carpeta):
    movs = []
    for archivo in sorted(carpeta.glob("2026-*.csv")):
        with open(archivo, encoding="utf-8") as f:
            movs.extend(csv.DictReader(f))
    with open(carpeta / "articulos.csv", encoding="utf-8") as f:
        articulos = list(csv.DictReader(f))
    combos = defaultdict(list)
    with open(carpeta / "combos.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            combos[r["combo"]].append((r["plato"], Decimal(r["unidades"]), Decimal(r["peso_ingreso"])))
    return movs, articulos, combos


def plato_de(articulos, codigo, fecha):
    """Plato del recetario para un código de caja vigente en `fecha` (extremos inclusivos)."""
    hits = [a["plato"] for a in articulos if a["articulo"] == codigo and a["desde"] <= fecha <= a["hasta"]]
    assert len(hits) == 1, (codigo, fecha, hits)
    return hits[0]


def componentes(mov, articulos, combos):
    """[(plato, unidades, ingreso)] de una venta VTA o COM, con el cobro neto repartido."""
    fecha = mov["fecha_hora"][:10]
    cant = Decimal(mov["cantidad"])
    cobrado = Decimal(mov["importe_bruto"]) - Decimal(mov["descuento"])
    if mov["tipo"] == "VTA":
        return [(plato_de(articulos, mov["articulo"], fecha), cant, cobrado)]
    partes = combos[mov["articulo"]]
    peso_total = sum(p for _, _, p in partes)
    return [(plato, cant * u, cobrado * p / peso_total) for plato, u, p in partes]


def margenes(movs, articulos, combos, costeador):
    por_id = {m["id"]: m for m in movs}
    unidades = defaultdict(Decimal)
    ingreso = defaultdict(Decimal)
    costo = defaultdict(Decimal)
    for m in movs:
        if m["tipo"] == "EXT":          # propina del personal: no es facturación de platos
            continue
        if m["tipo"] == "REV":          # reverso íntegro del original, con su fecha y reparto
            original, signo = por_id[m["referencia"]], -1
            assert original["tipo"] in ("VTA", "COM")
            for k in ("articulo", "cantidad", "importe_bruto", "descuento"):
                assert original[k] == m[k], (m["id"], k)
        elif m["tipo"] in ("VTA", "COM"):
            original, signo = m, 1
        else:
            raise ValueError(m["tipo"])
        fecha = original["fecha_hora"][:10]
        cpp = costeador.costos_al(fecha)
        for plato, u, imp in componentes(original, articulos, combos):
            unidades[plato] += signo * u
            ingreso[plato] += signo * imp
            costo[plato] += signo * u * cpp[plato]
    return unidades, ingreso, costo


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nivel2", type=Path, required=True)
    ap.add_argument("--caja", type=Path, required=True)
    ap.add_argument("--nivel1", type=Path)
    ap.add_argument("--compras", type=Path, default=AQUI / "compras_imagenes.csv")
    ap.add_argument("--salida", type=Path, required=True)
    a = ap.parse_args()

    catalogo = n2.leer_catalogo(a.nivel2)
    rend = n2.leer_rendimientos(a.nivel2)
    recetas = n2.leer_recetas(a.nivel2)
    fac2, notas = n2.leer_comprobantes_pdf(a.nivel2)
    lotes = [fac2, compras_imagenes(a.compras)]
    if a.nivel1:
        lotes.append(n2.leer_facturas_txt(a.nivel1)[0])  # F-001..F-005: deben coincidir
    facturas = unir_compras(*lotes)
    costeador = Costeador(facturas, notas, catalogo, rend, recetas)

    platos = sorted(c for c, r in recetas.items() if r["unidad_rendimiento"] == "porción")
    al_cierre = costeador.costos_al(CORTE)
    with open(a.salida / "costos.csv", "w", encoding="utf-8", newline="") as f:
        f.write("plato,costo_por_porcion\n")
        for c in platos:
            f.write(f"{c},{al_cierre[c].quantize(CENT, ROUND_HALF_UP)}\n")

    movs, articulos, combos = leer_caja(a.caja)
    unidades, ingreso, costo = margenes(movs, articulos, combos, costeador)
    with open(a.salida / "margenes.csv", "w", encoding="utf-8", newline="") as f:
        f.write("plato,unidades_vendidas,ingreso_neto,costo,margen\n")
        for c in platos:
            ing, cst = ingreso[c], costo[c]
            mg = (ing - cst) / ing if ing != 0 else Decimal(0)
            u = unidades[c]
            assert u == u.to_integral_value()
            f.write(f"{c},{int(u)},{ing.quantize(CENT, ROUND_HALF_UP)},"
                    f"{cst.quantize(CENT, ROUND_HALF_UP)},{mg.quantize(MICRO, ROUND_HALF_UP)}\n")


if __name__ == "__main__":
    main()
