"""
Generate a Bloomberg-add-in workbook that pulls Asian USD FX spot history.

Pairs: USDIDR, USDTHB, USDSGD, USDVND (plus EURUSD, optional, so EUR crosses can
be derived — this model is EUR-base). Range 2001-01-01 to 2026-12-31.

The workbook contains live =BDH() formulas, not data. It populates only when
opened in Excel with the Bloomberg Excel Add-in installed and a logged-in
terminal session; anywhere else the cells show #NAME?.

Regenerate:  python tools/build_fx_bloomberg_sheet.py
Output:      data/fx_history_bloomberg.xlsx
"""
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT = Path(__file__).resolve().parents[1] / "data" / "fx_history_bloomberg.xlsx"

# (ticker, label, what it is, number format, optional?)
PAIRS = [
    ("USDIDR Curncy", "USDIDR", "Indonesian rupiah per USD",  "#,##0",     False),
    ("USDTHB Curncy", "USDTHB", "Thai baht per USD",          "#,##0.0000", False),
    ("USDSGD Curncy", "USDSGD", "Singapore dollar per USD",   "#,##0.0000", False),
    ("USDVND Curncy", "USDVND", "Vietnamese dong per USD",    "#,##0",     False),
    ("EURUSD Curncy", "EURUSD", "USD per EUR - for EUR crosses", "#,##0.0000", True),
]

HDR_FILL   = PatternFill("solid", fgColor="1F3864")
SUB_FILL   = PatternFill("solid", fgColor="D9E2F3")
OPT_FILL   = PatternFill("solid", fgColor="EDEDED")
PARAM_FILL = PatternFill("solid", fgColor="FFF2CC")
HDR_FONT   = Font(bold=True, color="FFFFFF", size=11)
TITLE_FONT = Font(bold=True, size=14, color="1F3864")
BOLD       = Font(bold=True)
MUTED      = Font(italic=True, color="595959", size=9)
THIN       = Side(style="thin", color="BFBFBF")
BOX        = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _title(ws, cell, text):
    ws[cell] = text
    ws[cell].font = TITLE_FONT


def build_control(ws):
    ws.sheet_view.showGridLines = False
    _title(ws, "B2", "Bloomberg FX history pull - control panel")
    ws["B3"] = ("Every parameter below feeds the =BDH() formulas on the Data sheet. "
                "Change a cell and Excel re-pulls.")
    ws["B3"].font = MUTED

    params = [
        ("Start date",   date(2001, 1, 1),  "First observation requested."),
        ("End date",     date(2026, 12, 31), "Bloomberg returns data up to today; a future end date is harmless."),
        ("Field",        "PX_LAST",    "PX_LAST = closing spot. PX_BID / PX_ASK / PX_MID also valid."),
        ("Periodicity",  "M",          "D=daily, W=weekly, M=monthly, Q=quarterly, Y=yearly."),
        ("Days",         "A",          "A=all calendar days, W=weekdays, T=trading days only."),
        ("Fill",         "P",          "P=carry previous value over non-trading days, B=blank, NA=#N/A."),
        ("Sort",         "A",          "A=ascending (oldest first), D=descending."),
    ]
    ws["B5"] = "Parameter"; ws["C5"] = "Value"; ws["D5"] = "Notes"
    for c in "BCD":
        ws[f"{c}5"].fill = HDR_FILL; ws[f"{c}5"].font = HDR_FONT
    for i, (name, val, note) in enumerate(params):
        r = 6 + i
        ws[f"B{r}"] = name; ws[f"B{r}"].font = BOLD
        ws[f"C{r}"] = val
        ws[f"C{r}"].fill = PARAM_FILL; ws[f"C{r}"].border = BOX
        ws[f"C{r}"].alignment = Alignment(horizontal="center")
        ws[f"D{r}"] = note; ws[f"D{r}"].font = MUTED
    ws["C6"].number_format = "yyyy-mm-dd"
    ws["C7"].number_format = "yyyy-mm-dd"

    # Ticker table
    ws["B15"] = "Ticker"; ws["C15"] = "Label"; ws["D15"] = "Description"
    for c in "BCD":
        ws[f"{c}15"].fill = HDR_FILL; ws[f"{c}15"].font = HDR_FONT
    for i, (tk, label, desc, _fmt, optional) in enumerate(PAIRS):
        r = 16 + i
        ws[f"B{r}"] = tk
        ws[f"B{r}"].fill = OPT_FILL if optional else PARAM_FILL
        ws[f"B{r}"].border = BOX
        ws[f"C{r}"] = label; ws[f"C{r}"].font = BOLD
        ws[f"D{r}"] = desc + (" (optional)" if optional else "")
        ws[f"D{r}"].font = MUTED

    ws["B22"] = "Quality check - reads whatever the Data sheet returned"
    ws["B22"].font = BOLD
    qc = ["Label", "Observations", "First date", "Last date", "Min", "Max"]
    for j, h in enumerate(qc):
        c = get_column_letter(2 + j)
        ws[f"{c}23"] = h; ws[f"{c}23"].fill = HDR_FILL; ws[f"{c}23"].font = HDR_FONT
    for i, (_tk, label, _desc, fmt, _opt) in enumerate(PAIRS):
        r = 24 + i
        dcol = get_column_letter(1 + i * 3)          # Data sheet date column
        vcol = get_column_letter(2 + i * 3)          # Data sheet value column
        ws[f"B{r}"] = label; ws[f"B{r}"].font = BOLD
        # Whole-column refs so the check is valid at any periodicity.
        ws[f"C{r}"] = f"=COUNT(Data!{vcol}:{vcol})"
        ws[f"D{r}"] = f'=IF(C{r}=0,"",MIN(Data!{dcol}:{dcol}))'
        ws[f"E{r}"] = f'=IF(C{r}=0,"",MAX(Data!{dcol}:{dcol}))'
        ws[f"F{r}"] = f'=IF(C{r}=0,"",MIN(Data!{vcol}:{vcol}))'
        ws[f"G{r}"] = f'=IF(C{r}=0,"",MAX(Data!{vcol}:{vcol}))'
        ws[f"D{r}"].number_format = "yyyy-mm-dd"
        ws[f"E{r}"].number_format = "yyyy-mm-dd"
        ws[f"F{r}"].number_format = fmt
        ws[f"G{r}"].number_format = fmt
        for c in "CDEFG":
            ws[f"{c}{r}"].border = BOX

    ws["B31"] = ("Expected at monthly frequency over 2001-2026: ~296 observations per pair. "
                 "A materially lower count means the pull was truncated or the ticker is wrong.")
    ws["B31"].font = MUTED

    for col, w in zip("ABCDEFG", (3, 22, 16, 58, 14, 14, 14)):
        ws.column_dimensions[col].width = w


def build_data(ws):
    ws.sheet_view.showGridLines = False
    _title(ws, "A1", "Live Bloomberg pull")
    ws["A2"] = ("Each block is one =BDH() array formula anchored in row 5; it spills Date | Value "
                "downwards. Do not type below a formula - it will block the spill.")
    ws["A2"].font = MUTED

    for i, (_tk, label, desc, fmt, optional) in enumerate(PAIRS):
        c0 = 1 + i * 3                                # 3-col pitch: 2 spilled + 1 gap
        dcol, vcol = get_column_letter(c0), get_column_letter(c0 + 1)

        ws[f"{dcol}3"] = label + (" (optional)" if optional else "")
        ws[f"{dcol}3"].font = BOLD
        ws[f"{dcol}3"].fill = OPT_FILL if optional else SUB_FILL
        ws[f"{vcol}3"].fill = OPT_FILL if optional else SUB_FILL
        ws[f"{dcol}4"] = "Date"; ws[f"{vcol}4"] = desc
        for c in (dcol, vcol):
            ws[f"{c}4"].fill = HDR_FILL; ws[f"{c}4"].font = HDR_FONT

        tick_ref = f"Control!$B${16 + i}"
        ws[f"{dcol}5"] = (
            f"=BDH({tick_ref},Control!$C$8,Control!$C$6,Control!$C$7,"
            f'"Dir=V","Per="&Control!$C$9,"Days="&Control!$C$10,'
            f'"Fill="&Control!$C$11,"Sort="&Control!$C$12)'
        )

        # Column-level formats so ANY periodicity renders correctly, without
        # materialising thousands of empty styled cells.
        ws.column_dimensions[dcol].width = 13
        ws.column_dimensions[dcol].number_format = "yyyy-mm-dd"
        ws.column_dimensions[vcol].width = 15
        ws.column_dimensions[vcol].number_format = fmt
        ws.column_dimensions[get_column_letter(c0 + 2)].width = 3
    ws.freeze_panes = "A5"


def build_notes(ws):
    ws.sheet_view.showGridLines = False
    _title(ws, "B2", "Read before trusting the numbers")
    rows = [
        ("Requirements", ""),
        ("", "Needs the Bloomberg Excel Add-in and a logged-in terminal on the same machine. "
             "Without it every BDH cell shows #NAME? - that is the add-in missing, not a bad ticker."),
        ("", "If cells show #N/A Requesting Data..., the pull is still in flight. Ctrl+Alt+F9 forces a full recalc."),
        ("Quote direction", ""),
        ("", "All four pairs are quoted as LOCAL CURRENCY PER ONE USD. A rising line means the USD "
             "strengthened and the Asian currency weakened - the opposite sign to a return on holding "
             "that currency. Invert before using as an FX return."),
        ("", "This model is EUR-base, so the USD crosses are an intermediate step. EURUSD Curncy quotes "
             "USD per 1 EUR, and USDxxx quotes xxx per 1 USD, so the EUR cross is the PRODUCT: "
             "EURIDR = USDIDR * EURUSD. Worked example: 16,000 * 1.08 = 17,280 IDR per EUR. "
             "Alternatively pull EURIDR / EURTHB / EURSGD / EURVND Curncy directly and skip the arithmetic."),
        ("Data quality", ""),
        ("", "IDR and VND are non-deliverable. USDIDR / USDVND Curncy are onshore spot references; "
             "offshore NDF-implied rates can differ materially in stress. For NDF history use "
             "IHN+1M BGN Curncy (IDR) and VND+1M BGN Curncy."),
        ("", "USDVND history before roughly 2005 is thin and the rate was tightly managed in a narrow "
             "crawling band - low realised volatility there reflects the peg, not market conditions."),
        ("", "USDIDR from 2001 is entirely post-float (the rupiah floated in Aug 1997), so the series "
             "does not contain the Asian-crisis break. Starting in 2001 excludes it deliberately."),
        ("", "SGD is managed by MAS against an undisclosed trade-weighted band. Its realised vol "
             "understates what an unmanaged float would show."),
        ("", "Fill=P carries the last price over holidays. That suppresses realised volatility slightly "
             "at daily frequency. Set Fill=B and Days=T if you need true trading-day observations."),
        ("Tickers", ""),
        ("", "USDIDR Curncy is the composite quote. For a single consistent contributor use "
             "USDIDR BGN Curncy (Bloomberg Generic). Composite vs BGN can differ in thin markets."),
        ("Provenance", ""),
        ("", "Generated by tools/build_fx_bloomberg_sheet.py. Re-run that script to change tickers or "
             "layout; edit the Control sheet for dates, frequency and field."),
    ]
    r = 4
    for head, body in rows:
        if head:
            ws[f"B{r}"] = head; ws[f"B{r}"].font = Font(bold=True, size=11, color="1F3864")
        else:
            ws[f"B{r}"] = body
            ws[f"B{r}"].alignment = Alignment(wrap_text=True, vertical="top")
            ws.row_dimensions[r].height = 30
        r += 1
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 110


def main():
    wb = Workbook()
    build_control(wb.active); wb.active.title = "Control"
    build_data(wb.create_sheet("Data"))
    build_notes(wb.create_sheet("Notes"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"Wrote {OUT}")
    print(f"  {len(PAIRS)} BDH blocks (4 requested + EURUSD optional)")


if __name__ == "__main__":
    main()
