#!/usr/bin/env python3
"""Costo de ingredientes por porción de El Término Medio (niveles 1 y 2).

Solo biblioteca estándar. Aritmética exacta con Decimal (precisión 50) y
redondeo ROUND_HALF_UP a dos decimales únicamente en el resultado final.

Uso:
    python3 costeo.py --nivel 1 --datos <carpeta nivel-1> --salida costos.csv
    python3 costeo.py --nivel 2 --datos <carpeta nivel-2> --salida costos.csv
"""
import argparse
import base64
import csv
import json
import re
import zlib
from decimal import Decimal, getcontext, ROUND_HALF_UP
from pathlib import Path

getcontext().prec = 50

FECHA_CORTE = {1: "2026-08-10", 2: "2026-10-31"}


def dec(texto):
    """'1.234,56' o '1234,56' -> Decimal. Formato argentino de los comprobantes."""
    t = texto.strip().replace("$", "").replace("%", "").strip()
    t = t.replace(".", "").replace(",", ".") if "," in t else t
    return Decimal(t)


# ---------------------------------------------------------------- datos fijos
def leer_catalogo(carpeta):
    """(producto, presentación) -> (cantidad en unidad base, unidad base)."""
    cat = {}
    with open(carpeta / "catalogo.csv", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            clave = (fila["producto"], fila["presentacion"])
            cat[clave] = (Decimal(fila["cantidad_base"]), fila["unidad_base"])
    return cat


def leer_rendimientos(carpeta):
    """producto -> (limpio/bruto, cocido/limpio)."""
    with open(carpeta / "rendimientos.csv", encoding="utf-8") as f:
        return {
            r["producto"]: (Decimal(r["limpio_sobre_bruto"]), Decimal(r["cocido_sobre_limpio"]))
            for r in csv.DictReader(f)
        }


def leer_recetas(carpeta):
    with open(carpeta / "recetas.json", encoding="utf-8") as f:
        # parse_float=Decimal evita errores binarios en cantidades como 8.08
        return {r["codigo"]: r for r in json.load(f, parse_float=Decimal)}


# ------------------------------------------------------ comprobantes nivel 1
def leer_facturas_txt(carpeta):
    """Facturas de texto con columnas 'Renglón | Producto | Cantidad | ...'."""
    facturas = []
    for archivo in sorted((carpeta / "facturas").glob("*.txt")):
        texto = archivo.read_text(encoding="utf-8")
        ident = re.search(r"Factura\s+(\S+)", texto).group(1)
        fecha = re.search(r"Fecha:\s*(\d{4}-\d{2}-\d{2})", texto).group(1)
        lineas = texto.splitlines()
        i_enc = next(i for i, l in enumerate(lineas) if l.startswith("Renglón"))
        enc = [c.strip() for c in lineas[i_enc].split("|")]
        renglones = []
        for l in lineas[i_enc + 1:]:
            if "|" not in l:
                break
            v = dict(zip(enc, (c.strip() for c in l.split("|"))))
            renglones.append({
                "renglon": int(v["Renglón"]),
                "producto": v["Producto"].split()[0],
                "cantidad": dec(v["Cantidad"]),
                "presentacion": v["Presentación"],
                "neto": dec(v["Neto"]),
            })
        facturas.append({"id": ident, "fecha": fecha, "renglones": renglones})
    return facturas, []


# ------------------------------------------------------ comprobantes nivel 2
def textos_pdf(archivo):
    """Extrae (x, y, texto) de un PDF de ReportLab sin dependencias externas."""
    datos = archivo.read_bytes()
    piezas = []
    for m in re.finditer(rb"<<(.*?)>>\s*stream\r?\n(.*?)endstream", datos, re.S):
        dic, flujo = m.group(1), m.group(2).strip()
        if b"ASCII85Decode" in dic:
            flujo = base64.a85decode(flujo, adobe=True)
        if b"FlateDecode" in dic:
            flujo = zlib.decompress(flujo)
        contenido = flujo.decode("latin-1")
        for t in re.finditer(r"1 0 0 1 ([\d.]+) ([\d.]+) Tm \((.*?)\) Tj", contenido):
            texto = re.sub(r"\\([0-7]{3})", lambda o: chr(int(o.group(1), 8)), t.group(3))
            texto = texto.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
            piezas.append((float(t.group(1)), float(t.group(2)), texto))
    return piezas


def filas_pdf(archivo):
    """Agrupa los textos por renglón visual (misma y), de arriba hacia abajo."""
    filas = {}
    for x, y, t in textos_pdf(archivo):
        filas.setdefault(round(y, 1), []).append((x, t))
    return [sorted(v) for _, v in sorted(filas.items(), reverse=True)]


ENCABEZADOS = {"R": "renglon", "Código / descripción": "producto", "Cant.": "cantidad",
               "Unidad": "presentacion", "P. unitario": "precio", "Bonif.%": "bonif",
               "Neto": "neto"}


def leer_factura_pdf(archivo):
    """El orden de columnas cambia entre proveedores: se mapea por la x del encabezado."""
    filas = filas_pdf(archivo)
    plano = " ".join(t for f in filas for _, t in f)
    ident = re.search(r"Factura\s+(F-\d+)", plano).group(1)
    fecha = re.search(r"Fecha:\s*(\d{4}-\d{2}-\d{2})", plano).group(1)
    i_enc = next(i for i, f in enumerate(filas) if [t for _, t in f][:1] == ["R"])
    columnas = {x: ENCABEZADOS[t] for x, t in filas[i_enc]}
    renglones = []
    for f in filas[i_enc + 1:]:
        if not re.fullmatch(r"\d+", f[0][1]):
            break
        v = {columnas[x]: t for x, t in f}
        renglones.append({
            "renglon": int(v["renglon"]),
            "producto": v["producto"].split()[0],
            "cantidad": dec(v["cantidad"]),
            "presentacion": v["presentacion"],
            "neto": dec(v["neto"]),
        })
    return {"id": ident, "fecha": fecha, "renglones": renglones}


def leer_nota_pdf(archivo):
    plano = "\n".join(" ".join(t for _, t in f) for f in filas_pdf(archivo))

    def campo(nombre):
        return re.search(nombre + r":\s*(.+)", plano).group(1).strip()

    cant, unidad = campo("Cantidad devuelta").split()
    return {
        "id": re.search(r"Nota de (?:crédito|débito)\s+(\S+)", plano).group(1),
        "tipo": "debito" if "Nota de débito" in plano else "credito",
        "fecha": campo("Fecha"),
        "factura": campo("Factura asociada"),
        "renglon": int(campo("Renglón")),
        "producto": campo("Producto").split()[0],
        "concepto": campo("Concepto"),
        "cantidad": dec(cant),
        "presentacion": unidad,
        "importe": dec(campo("Importe acreditado")),
    }


def leer_comprobantes_pdf(carpeta):
    facturas = [leer_factura_pdf(a) for a in sorted((carpeta / "facturas").glob("*.pdf"))]
    notas = [leer_nota_pdf(a) for a in sorted((carpeta / "notas").glob("*.pdf"))]
    return facturas, notas


# ------------------------------------------------------------------- cálculo
def precios_efectivos(facturas, notas, catalogo, corte):
    """producto -> (precio por unidad base, factura, renglón, unidad base)."""
    elegido = {}
    for fac in facturas:
        if fac["fecha"] > corte:          # facturas posteriores al corte: fuera
            continue
        for r in fac["renglones"]:
            clave = (fac["fecha"], fac["id"])  # fecha y luego id mayor
            if r["producto"] not in elegido or clave > elegido[r["producto"]][0]:
                elegido[r["producto"]] = (clave, fac, r)

    precios = {}
    for prod, (_, fac, r) in elegido.items():
        base, unidad = catalogo[(prod, r["presentacion"])]
        neto = r["neto"]
        cantidad = r["cantidad"] * base
        for n in notas:
            if n["factura"] != fac["id"] or n["renglon"] != r["renglon"] or n["fecha"] > corte:
                continue
            assert n["producto"] == prod, n
            signo = -1 if n["tipo"] == "credito" else 1
            neto += signo * n["importe"]
            if n["concepto"] == "devolución":
                cantidad -= n["cantidad"] * catalogo[(prod, n["presentacion"])][0]
        precios[prod] = (neto / cantidad, fac["id"], r["renglon"], unidad)
    return precios


def costo_receta(codigo, recetas, precios, rend, catalogo, memo):
    """Costo de la tanda completa de una receta (un plato rinde una porción)."""
    if codigo in memo:
        return memo[codigo]
    total = Decimal(0)
    for ing in recetas[codigo]["ingredientes"]:
        prod, cant, estado = ing["producto"], Decimal(ing["cantidad"]), ing["estado"]
        if estado == "preparado":
            sub = recetas[prod]
            assert ing["unidad"] == sub["unidad_rendimiento"], ing
            costo_unitario = costo_receta(prod, recetas, precios, rend, catalogo, memo) / Decimal(sub["rendimiento"])
            total += cant * costo_unitario
            continue
        precio, _, _, unidad = precios[prod]
        assert ing["unidad"] == unidad, (codigo, ing, unidad)
        lsb, csl = rend[prod]
        if estado == "bruto":
            bruto = cant
        elif estado == "limpio":
            bruto = cant / lsb
        elif estado == "cocido":
            bruto = cant / (lsb * csl)
        else:
            raise ValueError(estado)
        total += bruto * precio
    memo[codigo] = total
    return total


def calcular(nivel, carpeta):
    catalogo = leer_catalogo(carpeta)
    rend = leer_rendimientos(carpeta)
    recetas = leer_recetas(carpeta)
    if nivel == 1:
        facturas, notas = leer_facturas_txt(carpeta)
    else:
        facturas, notas = leer_comprobantes_pdf(carpeta)
    precios = precios_efectivos(facturas, notas, catalogo, FECHA_CORTE[nivel])
    memo = {}
    salida = {}
    for codigo, receta in recetas.items():
        if receta["unidad_rendimiento"] != "porción":
            continue  # subrecetas: se usan, pero no van al CSV
        costo = costo_receta(codigo, recetas, precios, rend, catalogo, memo) / Decimal(receta["rendimiento"])
        salida[codigo] = costo
    return salida, precios


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nivel", type=int, choices=[1, 2], required=True)
    ap.add_argument("--datos", type=Path, required=True)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--detalle", action="store_true", help="imprime precios elegidos y costos sin redondear")
    a = ap.parse_args()
    costos, precios = calcular(a.nivel, a.datos)
    if a.detalle:
        for p, (pr, fac, ren, u) in sorted(precios.items()):
            print(f"{p} {fac} r{ren} {pr} $/{u}")
        for c, v in costos.items():
            print(c, v)
    with open(a.salida, "w", encoding="utf-8", newline="") as f:
        f.write("plato,costo_por_porcion\n")
        for codigo in sorted(costos):
            f.write(f"{codigo},{costos[codigo].quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}\n")


if __name__ == "__main__":
    main()
