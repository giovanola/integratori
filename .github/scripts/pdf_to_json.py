#!/usr/bin/env python3
"""
pdf_to_json.py
Konvertiert das PDF des Registro degli Integratori Alimentari
(Ministerio della Salute) in das kompakte JSON-Format fuer SupplementCheck.

Usage:
    python3 pdf_to_json.py <input.pdf> <output.json>
"""

import sys
import re
import json
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber nicht installiert. Fuehre aus: pip install pdfplumber")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def clean(s):
    """Whitespace normalisieren, Markdown-Reste entfernen."""
    if not s:
        return ''
    s = re.sub(r'\*+|_+', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def is_header_row(cells):
    """Tabellenheader erkennen (IMPRESA / PRODOTTO / CODICE)."""
    if not cells:
        return False
    joined = ' '.join((c or '') for c in cells).upper()
    return 'IMPRESA' in joined or 'PRODOTTO' in joined

def is_separator_row(cells):
    """Trennzeilen erkennen (nur Striche oder Leerzeichen)."""
    return all(re.match(r'^[-\s]*$', (c or '')) for c in cells)

def extract_date(page):
    """Aktualisierungsdatum aus Seitentext extrahieren."""
    text = page.extract_text() or ''
    m = re.search(r'aggiornato\s+al\s+(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Haupt-Parser
# ---------------------------------------------------------------------------

def pdf_to_json(pdf_path, output_path):
    entries = []
    current = None
    updated = None
    pages_with_tables = 0

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print(f"  PDF-Seiten:  {total_pages}")

        for page_num, page in enumerate(pdf.pages):

            # Datum nur von erster Seite
            if updated is None:
                updated = extract_date(page)

            tables = page.extract_tables()
            if not tables:
                continue
            pages_with_tables += 1

            for table in tables:
                for row in (table or []):
                    if not row:
                        continue

                    # Mindestens 3 Spalten benoetigt
                    # Manchmal gibt pdfplumber mehr Spalten zurueck
                    if len(row) < 3:
                        continue

                    # Erste drei Spalten: IMPRESA, PRODOTTO, CODICE
                    impresa  = clean(row[0])
                    prodotto = clean(row[1])
                    codice   = clean(row[2])

                    # Header- und Trennzeilen ueberspringen
                    if is_header_row([impresa, prodotto, codice]):
                        continue
                    if is_separator_row([impresa, prodotto, codice]):
                        continue

                    # Neuer Eintrag: CODICE ist numerisch (Notifizierungsnummer)
                    if codice and re.match(r'^\d+$', codice):
                        if current:
                            entries.append(current)
                        current = {'i': impresa, 'p': prodotto, 'c': codice}

                    # Fortsetzungszeile: CODICE leer
                    elif current:
                        if impresa:
                            current['i'] = (current['i'] + ' ' + impresa).strip()
                        if prodotto:
                            current['p'] = (current['p'] + ' ' + prodotto).strip()

        # Letzten Eintrag nicht vergessen
        if current:
            entries.append(current)

    # Abbruch wenn nichts extrahiert wurde
    if not entries:
        print("ERROR: Keine Eintraege extrahiert.")
        print(f"       Seiten mit Tabellen: {pages_with_tables}/{total_pages}")
        print("       Moegliche Ursache: PDF-Struktur hat sich veraendert.")
        print("       Bitte PDF manuell pruefen und Skript anpassen.")
        sys.exit(2)

    # Kompaktformat: Firmen als Index-Array
    company_list = sorted(set(e['i'] for e in entries))
    company_idx  = {c: i for i, c in enumerate(company_list)}
    data_compact = [[company_idx[e['i']], e['p'], e['c']] for e in entries]

    # Datum als Fallback: heute
    if not updated:
        updated = datetime.now().strftime('%d/%m/%Y')

    output = {
        'updated':  updated,
        'co':       company_list,
        'd':        data_compact,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, separators=(',', ':'))

    import gzip
    gz_size = len(gzip.compress(
        open(output_path, 'rb').read(), compresslevel=9
    ))

    print(f"  Eintraege:   {len(entries):,}")
    print(f"  Firmen:      {len(company_list):,}")
    print(f"  Datum:       {updated}")
    print(f"  JSON:        {len(open(output_path).read()) // 1024} KB")
    print(f"  Gzip:        {gz_size // 1024} KB")
    print(f"  Ausgabe:     {output_path}")

    return len(entries), len(company_list), updated


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.pdf> <output.json>")
        sys.exit(1)

    pdf_path    = sys.argv[1]
    output_path = sys.argv[2]

    print(f"\nKonvertierung gestartet: {pdf_path}")
    count, companies, date = pdf_to_json(pdf_path, output_path)
    print(f"\nFertig: {count:,} Eintraege, {companies:,} Firmen, Stand {date}\n")
