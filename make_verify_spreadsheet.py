"""
make_verify_spreadsheet.py  -  rebuilds verify_ivo_larsen.xlsx. Coaches do not need to run this.

Only this builder needs the extra package openpyxl (pip install openpyxl). The two scripts and the tests do not:
the tests read the finished spreadsheet with Python's standard library alone.

The expected values come from running deidentify.py and cmj_flags.py on the synthetic squad. Every calculated cell is a
live Excel formula. openpyxl cannot store a formula's answer, and a spreadsheet opened in Excel's Protected View shows
only stored answers, so this builder works them out with evaluate_workbook() and stores them beside the formulas.
"""

import math
import os
import re
import shutil
import statistics
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(ROOT, "verify_ivo_larsen.xlsx")
IVO = "Ivo Larsen"
WEEK_8 = (8, 1)
MATCH_TOLERANCE = 0.0051        # the expected values are shown to 2 decimals
IVO_SHEET, SQUAD_SHEET = "Ivo Larsen", "Squad TE and SWC"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# ------------------------------------------------------------------ reading and working out a finished spreadsheet (standard library only)

CELL = re.compile(r"^([A-Z]+)(\d+)$")
TOKEN = re.compile(r"""("[^"]*")|(?:'([^']+)'!)?\$?([A-Z]{1,3})\$?(\d+)(?::\$?([A-Z]{1,3})\$?(\d+))?(?![A-Za-z(])|([<>]=|<>|=)""")
FUNCTIONS = {
    "AVERAGE": lambda *a: statistics.fmean(_numbers(a)),
    "STDEV": lambda *a: statistics.stdev(_numbers(a)),
    "SQRT": math.sqrt,
    "ABS": abs,
    "COUNT": lambda *a: len(_numbers(a)),
    "IF": lambda test, yes, no: yes if test else no,
    "AND": lambda *a: all(a),
}


def _numbers(args):
    out = []
    for a in args:
        out += _numbers(a) if isinstance(a, list) else [a] if isinstance(a, (int, float)) and not isinstance(a, bool) else []
    return out


def _column_number(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _column_letters(n):
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def read_workbook(path):
    """{sheet: {cell: {"formula": text or None, "value": stored value or None}}}"""
    tag = lambda name: f"{{{MAIN_NS}}}{name}"
    with zipfile.ZipFile(path) as z:
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(tag("si")):
                strings.append("".join(t.text or "" for t in si.iter(tag("t"))))
        book = {}
        for s, target in _sheet_targets(z):
            cells = {}
            for c in ET.fromstring(z.read(target)).iter(tag("c")):
                f, v = c.find(tag("f")), c.find(tag("v"))
                value = None
                kind = c.get("t")
                if kind == "inlineStr":
                    value = "".join(x.text or "" for x in c.iter(tag("t")))
                elif v is not None and v.text is not None:
                    value = strings[int(v.text)] if kind == "s" else v.text if kind == "str" else float(v.text)
                cells[c.get("r")] = {"formula": f.text if f is not None else None, "value": value}
            book[s.get("name")] = cells
    return book


def evaluate_workbook(book):
    """Work out every formula in the workbook. Returns {(sheet, cell): answer}."""
    done = {}

    def value(sheet, cell):
        info = book[sheet].get(cell)
        if info is None:
            return None
        if info["formula"] is None:
            return info["value"]
        if (sheet, cell) not in done:
            done[(sheet, cell)] = compute(sheet, info["formula"])
        return done[(sheet, cell)]

    def cell_range(sheet, c1, r1, c2, r2):
        return [value(sheet, f"{_column_letters(c)}{r}") for r in range(int(r1), int(r2) + 1)
                for c in range(_column_number(c1), _column_number(c2) + 1)]

    def compute(sheet, formula):
        def swap(m):
            text, other, c1, r1, c2, r2, op = m.groups()
            if text is not None:
                return text
            if op is not None:
                return {"=": "==", "<>": "!="}.get(op, op)
            where = other or sheet
            if c2:
                return f"_range({where!r}, {c1!r}, {r1}, {c2!r}, {r2})"
            return f"_value({where!r}, {c1 + r1!r})"
        expression = TOKEN.sub(swap, formula.lstrip("="))
        return eval(expression, {"__builtins__": {}, "_value": value, "_range": cell_range, **FUNCTIONS})

    for sheet, cells in book.items():
        for cell, info in cells.items():
            if info["formula"] is not None:
                value(sheet, cell)
    return done


def store_answers(path):
    """Write each formula's answer into the file, beside the formula."""
    answers = evaluate_workbook(read_workbook(path))
    tag = lambda name: f"{{{MAIN_NS}}}{name}"
    ET.register_namespace("", MAIN_NS)
    folder = tempfile.mkdtemp(prefix="xlsx_")
    temp = os.path.join(folder, "new.xlsx")
    with zipfile.ZipFile(path) as z:
        by_target = {target: s.get("name") for s, target in _sheet_targets(z)}
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as out:
            for item in z.infolist():
                data = z.read(item.filename)
                if item.filename in by_target:
                    root = ET.fromstring(data)
                    for c in root.iter(tag("c")):
                        f = c.find(tag("f"))
                        if f is None:
                            continue
                        answer = answers[(by_target[item.filename], c.get("r"))]
                        v = c.find(tag("v"))
                        if v is None:
                            v = ET.SubElement(c, tag("v"))
                        if isinstance(answer, str):
                            c.set("t", "str")
                            v.text = answer
                        else:
                            c.attrib.pop("t", None)
                            v.text = repr(float(answer))
                    data = ET.tostring(root, xml_declaration=True, encoding="UTF-8")
                out.writestr(item, data)
    shutil.move(temp, path)
    shutil.rmtree(folder, ignore_errors=True)


def _sheet_targets(z):
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    pairs = []
    for s in ET.fromstring(z.read("xl/workbook.xml")).find(f"{{{MAIN_NS}}}sheets"):
        target = rels[s.get(f"{{{REL_NS}}}id")].lstrip("/")
        pairs.append((s, target if target.startswith("xl/") else "xl/" + target))
    return pairs


# ------------------------------------------------------------------ the values, from the scripts themselves

def squad_values():
    """Run the scripts on the synthetic squad. Returns ({name: athlete details}, squad thresholds, results by name)."""
    import csv
    import cmj_flags
    import deidentify
    folder = tempfile.mkdtemp(prefix="verify_")
    try:
        settings = {**deidentify.SETTINGS, "profiles": dict(deidentify.SETTINGS["profiles"])}
        profile = dict(settings["profiles"]["force_plate_trials"])
        profile["input_file"] = os.path.join(ROOT, profile["input_file"])
        settings["profiles"]["force_plate_trials"] = profile
        run = deidentify.run(settings, "force_plate_trials", output_override=os.path.join(folder, "out"), key_override=os.path.join(folder, "key"))
        with open(run["key_path"], newline="", encoding="utf-8") as f:
            names = {r["code"]: r["original_id"] for r in csv.DictReader(f)}
        out = cmj_flags.run({**cmj_flags.SETTINGS, "input_file": run["output_file"]}, write=False)
        return {names[c]: a for c, a in out["athletes"].items()}, out["squad"], {(names[r["athlete"]], r["day"]): r for r in out["results"]}
    finally:
        shutil.rmtree(folder, ignore_errors=True)


# ------------------------------------------------------------------ building the spreadsheet (needs openpyxl)

def build(path=OUTPUT):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    athletes, squad, results = squad_values()
    bold = Font(bold=True)
    title = Font(bold=True, size=14)
    head_fill = PatternFill("solid", fgColor="D9E2F3")
    live_fill = PatternFill("solid", fgColor="E2EFDA")
    expected_fill = PatternFill("solid", fgColor="F2F2F2")
    wrap = Alignment(wrap_text=True, vertical="top")

    def headings(sheet, row, labels):
        for i, label in enumerate(labels, start=1):
            c = sheet.cell(row=row, column=i, value=label)
            c.font, c.fill, c.alignment = bold, head_fill, Alignment(wrap_text=True, horizontal="center", vertical="center")

    def checked(sheet, row, col, formula, expected, how=""):
        """One calculated cell: the live formula, the script's value next to it, and whether they match."""
        live = sheet.cell(row=row, column=col, value=formula)
        live.fill = live_fill
        exp = sheet.cell(row=row, column=col + 1, value=expected)
        exp.fill = expected_fill
        a, b = f"{_column_letters(col)}{row}", f"{_column_letters(col + 1)}{row}"
        if isinstance(expected, str):
            sheet.cell(row=row, column=col + 2, value=f'=IF({a}={b},"OK","CHECK")')
        else:
            live.number_format = exp.number_format = "0.00"
            sheet.cell(row=row, column=col + 2, value=f'=IF(ABS({a}-{b})<{MATCH_TOLERANCE},"OK","CHECK")')
        if how:
            sheet.cell(row=row, column=col + 3, value=how)

    wb = Workbook()
    wb.calculation.fullCalcOnLoad = True

    # ---- squad sheet first, so Ivo's sheet can point at its cells
    ivo_sheet = wb.active
    ivo_sheet.title = IVO_SHEET
    sq = wb.create_sheet(SQUAD_SHEET)
    full = sorted(n for n, a in athletes.items() if a["enough"])
    first_row, last_row = 16, 16 + len(full) - 1
    sq["A1"] = "Squad typical error (TE) and smallest worthwhile change (SWC)"
    sq["A1"].font = title
    sq["A2"] = ("All made-up athletes. Every athlete with a full 4-day baseline is below. Green cells are live formulas, grey cells are what "
                "cmj_flags.py reports, and the Match column should say OK.")
    headings(sq, 4, ["Step", "Formula", "Script says", "Match", "What it does"])
    te_rows = {"count": 5, "sd": 6, "te": 7, "between": 8, "mult": 9, "swc": 10, "k": 11, "kte": 12}
    diffs = f"S{first_row}:U{last_row}"
    means = f"R{first_row}:R{last_row}"
    sq["A5"] = "Baseline differences used"
    checked(sq, 5, 2, f"=COUNT({diffs})", float(squad["baseline_diffs_used"]), "How many consecutive-day differences are in the table below.")
    sq["B5"].number_format = sq["C5"].number_format = "0"
    sq["A6"] = "SD of the differences"
    checked(sq, 6, 2, f"=STDEV({diffs})", round(squad["te"] * math.sqrt(2), 2), "The standard deviation of every difference in the table.")
    sq["A7"] = "Typical error (TE)"
    checked(sq, 7, 2, "=B6/SQRT(2)", round(squad["te"], 2), "That SD divided by the square root of 2.")
    sq["A8"] = "Between-athlete SD"
    checked(sq, 8, 2, f"=STDEV({means})", round(squad["between_athlete_sd"], 2), "The standard deviation of the athletes' baseline means.")
    sq["A9"] = "SWC multiplier (a setting)"
    sq["B9"] = 0.2
    sq["A10"] = "Smallest worthwhile change (SWC)"
    checked(sq, 10, 2, "=B9*B8", round(squad["swc"], 2), "0.2 x the between-athlete SD.")
    sq["A11"] = "k (a setting)"
    sq["B11"] = squad["k"]
    sq["A12"] = "k x TE"
    checked(sq, 12, 2, "=B11*B7", round(squad["k_te"], 2), "A drop must be bigger than both this and the SWC to be flagged.")

    labels = ["Athlete"] + [f"Day {d} trial {t}" for d in range(1, 5) for t in range(1, 4)] + [f"Day {d} mean" for d in range(1, 5)]
    labels += ["Baseline mean", "Day 2 minus day 1", "Day 3 minus day 2", "Day 4 minus day 3"]
    headings(sq, first_row - 1, labels)
    for row, name in enumerate(full, start=first_row):
        a = athletes[name]
        sq.cell(row=row, column=1, value=name)
        for d, day in enumerate(a["baseline_days"]):
            for t, height in enumerate(a["trials"][day]):
                sq.cell(row=row, column=2 + d * 3 + t, value=height)
            first, last = _column_letters(2 + d * 3), _column_letters(4 + d * 3)
            c = sq.cell(row=row, column=14 + d, value=f"=AVERAGE({first}{row}:{last}{row})")
            c.fill, c.number_format = live_fill, "0.00"
        c = sq.cell(row=row, column=18, value=f"=AVERAGE(N{row}:Q{row})")
        c.fill, c.number_format = live_fill, "0.00"
        for i, (later, earlier) in enumerate((("O", "N"), ("P", "O"), ("Q", "P"))):
            c = sq.cell(row=row, column=19 + i, value=f"={later}{row}-{earlier}{row}")
            c.fill, c.number_format = live_fill, "0.00"
    sq.column_dimensions["A"].width = 32
    for col in range(2, 22):
        sq.column_dimensions[_column_letters(col)].width = 9.5
    sq.row_dimensions[first_row - 1].height = 45
    sq.freeze_panes = sq.cell(row=first_row, column=2)

    # ---- Ivo Larsen
    a = athletes[IVO]
    ws = ivo_sheet
    ws["A1"] = "Check Ivo Larsen's week 8 flag by hand"
    ws["A1"].font = title
    ws["A2"] = ("A made-up athlete from the synthetic squad. Green cells are live Excel formulas: click one to see it. Grey cells are what "
                "cmj_flags.py reports. The Match column should say OK on every line.")
    ws["A2"].alignment = wrap
    ws.merge_cells("A2:I2")
    ws.row_dimensions[2].height = 34
    ws["A4"] = "Step 1. The baseline: the first 4 test days"
    ws["A4"].font = bold
    headings(ws, 5, ["Test day", "Trial 1", "Trial 2", "Trial 3", "Day mean", "Script says", "Match", "What it does"])
    row = 6
    for day in a["baseline_days"]:
        ws.cell(row=row, column=1, value=f"Week {day[0]} session {day[1]}")
        for t, height in enumerate(a["trials"][day]):
            ws.cell(row=row, column=2 + t, value=height)
        checked(ws, row, 5, f"=AVERAGE(B{row}:D{row})", round(a["day_means"][day], 2), "The mean of that day's trials." if row == 6 else "")
        row += 1
    ws.cell(row=10, column=1, value="Baseline mean").font = bold
    checked(ws, 10, 5, "=AVERAGE(E6:E9)", round(a["baseline_mean"], 2), "The mean of the four day means.")

    ws["A12"] = "Step 2. Week 8"
    ws["A12"].font = bold
    headings(ws, 13, ["Test day", "Trial 1", "Trial 2", "Trial 3", "Value", "Script says", "Match", "What it does"])
    ws["A14"] = f"Week {WEEK_8[0]} session {WEEK_8[1]}"
    for t, height in enumerate(a["trials"][WEEK_8]):
        ws.cell(row=14, column=2 + t, value=height)
    result = results[(IVO, WEEK_8)]
    checked(ws, 14, 5, "=AVERAGE(B14:D14)", round(a["day_means"][WEEK_8], 2), "The mean of that day's trials.")
    ws["A15"] = "Drop from baseline"
    ws["A15"].font = bold
    checked(ws, 15, 5, "=E10-E14", round(result["drop"], 2), "Baseline mean minus the week 8 value.")

    ws["A17"] = f"Step 3. The squad's thresholds (worked out on the '{SQUAD_SHEET}' sheet)"
    ws["A17"].font = bold
    headings(ws, 18, ["Threshold", "", "", "", "Value", "Script says", "Match", "What it does"])
    for r, label, source, expected, how in ((19, "Typical error (TE)", "te", squad["te"], "From the other sheet."),
                                            (20, "Smallest worthwhile change (SWC)", "swc", squad["swc"], "From the other sheet."),
                                            (21, "k x TE", "kte", squad["k_te"], "From the other sheet.")):
        ws.cell(row=r, column=1, value=label)
        checked(ws, r, 5, f"='{SQUAD_SHEET}'!B{te_rows[source]}", round(expected, 2), how)

    ws["A23"] = "Step 4. The decision"
    ws["A23"].font = bold
    headings(ws, 24, ["Question", "", "", "", "Answer", "Script says", "Match", "What it does"])
    ws["A25"] = "Is the drop bigger than the SWC?"
    checked(ws, 25, 5, '=IF(E15>E20,"yes","no")', "yes", "")
    ws["A26"] = "Is the drop bigger than k x TE?"
    checked(ws, 26, 5, '=IF(E15>E21,"yes","no")', "yes", "")
    ws["A27"] = "Flagged?"
    ws["A27"].font = bold
    checked(ws, 27, 5, '=IF(AND(E15>E20,E15>E21),"FLAG","no flag")', "FLAG", "Flagged only when the drop is bigger than both.")
    ws.column_dimensions["A"].width = 34
    for col in "BCD":
        ws.column_dimensions[col].width = 8
    for col in "EFG":
        ws.column_dimensions[col].width = 12
    ws.column_dimensions["H"].width = 48
    wb.save(path)
    store_answers(path)
    return path


if __name__ == "__main__":
    print(f"Wrote {build()}")
