#!/usr/bin/env python3
"""
xlsx_tools.py — Formula recalculation and verification for Excel files.

Usage:
  python3 xlsx_tools.py recalc <file.xlsx>     Recalculate all formulas
  python3 xlsx_tools.py verify <file.xlsx>      Verify no formula errors remain
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import warnings

# UTF-8 stdio guard — win32 pipes default to the ANSI codepage (cp1252/cp936)
# and CJK sheet names / file paths in JSON output would crash the print.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Forbidden functions (incompatible with Excel 2019 and earlier)
FORBIDDEN_FUNCTIONS = [
    'FILTER', 'UNIQUE', 'SORT', 'SORTBY', 'XLOOKUP', 'XMATCH',
    'SEQUENCE', 'LET', 'LAMBDA', 'RANDARRAY'
]

# Implicit array formula pattern
IMPLICIT_ARRAY_PATTERN = re.compile(r'MATCH\s*\(\s*TRUE\s*\(\s*\)', re.IGNORECASE)

# Shared by every openpyxl ImportError path so the message never dumps a
# traceback: state what is missing and the exact command to fix it.
OPENPYXL_INSTALL_HINT = (
    "install it with: pip3 install --user openpyxl "
    "(if pypi.org times out, retry once with a mirror: "
    "-i https://pypi.tuna.tsinghua.edu.cn/simple)"
)


def _find_libreoffice():
    """Return a LibreOffice/soffice executable path, or None.

    Discovery order: PATH (`libreoffice`, then `soffice`), then platform
    app paths (macOS .app bundle, Windows Program Files, common Linux paths).
    """
    candidates = []
    for name in ('libreoffice', 'soffice'):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    if sys.platform == 'darwin':
        candidates.append('/Applications/LibreOffice.app/Contents/MacOS/soffice')
    elif sys.platform == 'win32':
        for env_var in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            base = os.environ.get(env_var)
            if base:
                # soffice.com is the console-attached variant: it stays
                # synchronous and keeps stdout/stderr attached, whereas
                # GUI-subsystem soffice.exe may return before --convert-to
                # finishes. Prefer .com; .exe is the fallback.
                candidates.append(os.path.join(base, 'LibreOffice', 'program', 'soffice.com'))
                candidates.append(os.path.join(base, 'LibreOffice', 'program', 'soffice.exe'))
    else:  # Linux and other POSIX
        candidates.extend(['/usr/bin/soffice', '/usr/local/bin/soffice',
                           '/snap/bin/libreoffice', '/opt/libreoffice/program/soffice'])
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _conditional_formatting_count(filepath):
    """Count conditional-formatting rule blocks in sheet XML (std + x14 ext)."""
    total = 0
    try:
        import zipfile
        with zipfile.ZipFile(filepath) as z:
            for name in z.namelist():
                if re.match(r'xl/worksheets/sheet\d+\.xml$', name):
                    xml = z.read(name).decode('utf-8', errors='replace')
                    total += xml.count('<conditionalFormatting')
                    total += xml.count(':conditionalFormatting')  # x14 extension blocks
    except Exception:
        pass
    return total


# LibreOffice headless does NOT recalculate xlsx cells that already carry a
# cached <v> value: the OOXMLRecalcMode load option defaults to 'never', so
# stale caches written by Excel/WPS used to pass through unchanged while we
# reported recalculated=true. Pre-seeding the isolated profile with
# OOXMLRecalcMode=0 forces a full recalculation on load.
_LO_FORCE_RECALC_XCU = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<oor:items xmlns:oor="http://openoffice.org/2001/registry" '
    'xmlns:xs="http://www.w3.org/2001/XMLSchema" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
    ' <item oor:path="/org.openoffice.Office.Calc/Formula/Load">'
    '<prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop>'
    '</item>\n</oor:items>\n'
)


def _seed_lo_profile(profile_dir):
    """Pre-seed an isolated LO user profile forcing full recalc on xlsx load.
    Failure is non-fatal: unseeded only means stale caches may survive."""
    try:
        user_dir = os.path.join(profile_dir, 'user')
        os.makedirs(user_dir, exist_ok=True)
        with open(os.path.join(user_dir, 'registrymodifications.xcu'),
                  'w', encoding='utf-8') as f:
            f.write(_LO_FORCE_RECALC_XCU)
    except OSError:
        pass


def _rename_aside(path, stamp=None):
    """Rename `path` to '<path>.legacy-<timestamp>' and return the new path.

    Two calls in the same second would otherwise collide on the timestamp
    name (os.rename onto a non-empty dir raises); append -2, -3, ... until
    the name is free. Never deletes anything.
    """
    stamp = stamp or time.strftime('%Y%m%d-%H%M%S')
    candidate = f'{path}.legacy-{stamp}'
    serial = 1
    while os.path.exists(candidate):
        serial += 1
        candidate = f'{path}.legacy-{stamp}-{serial}'
    os.rename(path, candidate)
    return candidate


def cmd_recalc(args):
    """Recalculate all formulas in an Excel file."""
    filepath = args.file
    if not os.path.exists(filepath):
        print(json.dumps({"status": "error", "message": f"File not found: {filepath}"}))
        sys.exit(2)

    # Hard gate: .xlsx only. Without this, `recalc data.csv` makes
    # LibreOffice convert the CSV to xlsx and then overwrite the ORIGINAL
    # .csv path with binary content -- silent data destruction reported as
    # success. (.xlsm is refused for the same reason: conversion strips VBA.)
    if os.path.splitext(filepath)[1].lower() != '.xlsx':
        print(json.dumps({
            "status": "error",
            "message": (f"recalc only supports .xlsx files, got: {filepath}. "
                        "Convert to .xlsx first (e.g. open in Excel/WPS and Save As .xlsx)."),
        }))
        sys.exit(2)

    # Option 1: formulas library.
    try:
        # formulas lazily compiles its submodules through PEP 562 __getattr__:
        # `import formulas` only compiles __init__.py, and the modules carrying
        # `v is 1.0`-style SyntaxWarnings (functions/math.py, stat.py, ...)
        # compile at ExcelModel()/loads()/calculate()/write() time. Keep the
        # WHOLE branch inside one block that filters SyntaxWarning only, so
        # other warning categories and other engine branches are unaffected.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            import formulas
            print("Recalculating with formulas library...")
            xl_model = formulas.ExcelModel().loads(filepath).finish()
            xl_model.calculate()

            # Write a recalculated copy for verification only (formulas strips
            # charts/styles). xl_model.write() treats its dirpath argument as a
            # DIRECTORY and drops files with upper-case .XLSX extensions in it,
            # so write into a temp dir and move the right file out as a single
            # <base>_recalc_verify.xlsx.
            base = os.path.splitext(filepath)[0]
            verify_path = base + '_recalc_verify.xlsx'
            formula_warnings = []
            tmpdir = tempfile.mkdtemp(prefix='xlsx_formulas_')
            try:
                xl_model.write(dirpath=tmpdir)
                produced = sorted(
                    os.path.join(tmpdir, name) for name in os.listdir(tmpdir)
                    if name.lower().endswith('.xlsx')
                    and os.path.isfile(os.path.join(tmpdir, name))
                )
                if not produced:
                    raise RuntimeError(f'formulas produced no .xlsx in {tmpdir}')
                if len(produced) > 1:
                    stem = os.path.basename(base).lower()
                    same_name = [p for p in produced
                                 if os.path.splitext(os.path.basename(p))[0].lower() == stem]
                    if len(same_name) != 1:
                        raise RuntimeError(
                            f'formulas produced {len(produced)} workbooks, none matching '
                            f'{os.path.basename(filepath)} uniquely; refusing to guess')
                    produced = same_name
                if os.path.isdir(verify_path):
                    # Self-heal the legacy bad artifact: earlier versions left a
                    # DIRECTORY named <base>_recalc_verify.xlsx at this path.
                    # Remove it only when every entry inside is a plain .xlsx
                    # FILE — a .xlsx-named subdirectory can hold user data and
                    # must never be rmtree'd. Anything else gets renamed aside,
                    # not deleted.
                    contents = os.listdir(verify_path)
                    if all(os.path.isfile(os.path.join(verify_path, name))
                           and name.casefold().endswith('.xlsx')
                           for name in contents):
                        shutil.rmtree(verify_path)
                    else:
                        legacy = _rename_aside(verify_path)
                        formula_warnings.append(
                            f'Legacy verify path contained entries that were not '
                            f'plain .xlsx files; kept as {legacy}')
                elif os.path.exists(verify_path):
                    # shutil.move only replaces an existing file on POSIX.
                    os.remove(verify_path)
                shutil.move(produced[0], verify_path)
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
        print(json.dumps({
            "status": "success",
            "method": "formulas",
            "recalculated": True,
            "delivery_file_recalculated": False,
            "verification_file": verify_path,
            "warnings": formula_warnings,
            "note": f"Verification file: {verify_path} (do NOT deliver this — it strips charts/styles). Deliver the original file.",
        }))

        # Set calcMode=auto on the ORIGINAL file so Excel recalculates on open
        _set_calc_mode_auto(filepath)
        return
    except ImportError:
        print("formulas library not available, trying libreoffice...")
    except Exception as e:
        print(f"formulas library failed: {e}, trying libreoffice...")

    # Option 2: libreoffice headless.
    # LibreOffice refuses to overwrite the source file when converting to the
    # same format in the same directory, so convert into a fresh temp dir and
    # move the result back over the original.
    lo_bin = _find_libreoffice()
    if lo_bin:
        cf_before = _conditional_formatting_count(filepath)
        tmpdir = tempfile.mkdtemp(prefix='xlsx_recalc_')
        profile = tempfile.mkdtemp(prefix='xlsx_lo_profile_')
        _seed_lo_profile(profile)
        try:
            from pathlib import Path
            subprocess.run([
                lo_bin, '--headless', '--calc',
                # Isolated user profile: a locked/absent default profile
                # (fresh CI machines, parallel runs) must not break recalc.
                f'-env:UserInstallation={Path(profile).resolve().as_uri()}',
                '--convert-to', 'xlsx',
                '--outdir', tmpdir, os.path.abspath(filepath)
            ], check=True, capture_output=True, timeout=120)
            converted = glob.glob(os.path.join(tmpdir, '*.xlsx'))
            if not converted:
                raise RuntimeError('LibreOffice produced no output file')
            # os.replace cannot move across volumes — on win32 the temp dir
            # (C:\Users\...\Temp) and the checkout/target (D:\...) are often
            # different drives and it dies with WinError 17. Stage the copy
            # next to the target and replace atomically: a mid-copy failure
            # must never leave the user's original file truncated.
            recalc_tmp = filepath + '.recalc-part'
            shutil.copyfile(converted[0], recalc_tmp)
            os.replace(recalc_tmp, filepath)
            lo_warnings = []
            if cf_before > 0 and _conditional_formatting_count(filepath) < cf_before:
                lo_warnings.append('LibreOffice recalc may drop conditional-formatting extensions')
            print(json.dumps({
                "status": "success",
                "method": "libreoffice",
                "recalculated": True,
                "delivery_file_recalculated": True,
                "warnings": lo_warnings,
            }))
            return
        except Exception as e:
            print(f"libreoffice failed: {e}, falling back to calcMode=auto...")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            shutil.rmtree(profile, ignore_errors=True)

    # Fallback: request recalculation on open, but do not claim that formulas ran.
    if not _set_calc_mode_auto(filepath):
        message = "No calculation engine is available and calcMode=auto could not be set."
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            message += (f" The 'openpyxl' package is not installed; "
                        f"{OPENPYXL_INSTALL_HINT}")
        print(json.dumps({
            "status": "error",
            "method": "calcMode_auto",
            "recalculated": False,
            "message": message,
        }))
        sys.exit(2)
    print(json.dumps({
        "status": "deferred",
        "method": "calcMode_auto",
        "recalculated": False,
        "delivery_file_recalculated": False,
        "note": "Neither formulas nor libreoffice is available. Formula results remain unverified; Excel/WPS has been asked to recalculate them on open.",
    }))


def _set_calc_mode_auto(filepath):
    """Set calcMode=auto (+fullCalcOnLoad/forceFullCalc) on the workbook.

    Surgical zip edit of xl/workbook.xml only: an openpyxl load/save
    round-trip silently drops charts, images and shapes from the delivered
    file. Every other zip entry is copied byte-for-byte and the package is
    swapped in atomically (same-directory os.replace). No openpyxl needed.
    """
    import zipfile

    want = {'calcMode': 'auto', 'fullCalcOnLoad': '1', 'forceFullCalc': '1'}

    def _fix_tag(m):
        tag = m.group(0)
        for attr in want:
            tag = re.sub(rf'\s*{attr}="[^"]*"', '', tag)
        attrs = ' '.join(f'{a}="{v}"' for a, v in want.items())
        return tag.replace('<calcPr', f'<calcPr {attrs}', 1)

    def _patch(xml):
        new, k = re.subn(r'<calcPr\b[^>]*/>', _fix_tag, xml)
        if k == 0:
            new, k = re.subn(r'<calcPr\b[^>]*>.*?</calcPr>', _fix_tag, xml,
                             flags=re.S)
        if k == 0:
            ins = '<calcPr calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>'
            for anchor in ('</definedNames>', '</sheets>'):
                if anchor in xml:
                    return xml.replace(anchor, anchor + ins, 1)
            return None
        return new

    tmp = filepath + '.calcmode-part'
    try:
        with zipfile.ZipFile(filepath, 'r') as zin:
            infos = zin.infolist()
            data = {i.filename: zin.read(i.filename) for i in infos}
        raw = data.get('xl/workbook.xml')
        if raw is None:
            return False
        patched = _patch(raw.decode('utf-8'))
        if patched is None:
            return False
        data['xl/workbook.xml'] = patched.encode('utf-8')
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            for info in infos:
                zout.writestr(info, data[info.filename])
        os.replace(tmp, filepath)
        return True
    except Exception as e:
        print(f"Warning: could not set calcMode: {e}", file=sys.stderr)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def cmd_verify(args):
    """Verify an Excel file for formula errors, forbidden functions, and implicit arrays."""
    filepath = args.file
    if not os.path.exists(filepath):
        print(json.dumps({"status": "error", "message": f"File not found: {filepath}"}))
        sys.exit(2)

    try:
        from openpyxl import load_workbook
    except ImportError:
        print(json.dumps({
            "status": "error",
            "message": ("The 'openpyxl' package is required for verify but is not "
                        f"installed; {OPENPYXL_INSTALL_HINT}"),
        }))
        sys.exit(2)

    issues = []
    wb_data = None
    formula_count = 0
    missing_formula_cache_locations = []

    # Check 1: Formula errors (open with data_only to see cached values)
    try:
        wb_data = load_workbook(filepath, data_only=True)
        for ws in wb_data.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.startswith('#'):
                        issues.append({
                            "type": "formula_error",
                            "severity": "error",
                            "location": f"{ws.title}!{cell.coordinate}",
                            "value": cell.value,
                        })
    except Exception as e:
        issues.append({"type": "load_error", "severity": "error", "detail": str(e)})

    # Check 2: Forbidden functions + implicit arrays (open with formulas)
    try:
        wb_formulas = load_workbook(filepath)
        for ws in wb_formulas.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.startswith('='):
                        formula_count += 1
                        formula = cell.value.upper()

                        if (
                            wb_data is not None
                            and ws.title in wb_data.sheetnames
                            and wb_data[ws.title][cell.coordinate].value is None
                        ):
                            missing_formula_cache_locations.append(
                                f"{ws.title}!{cell.coordinate}"
                            )

                        # Forbidden functions
                        for func in FORBIDDEN_FUNCTIONS:
                            if func + '(' in formula:
                                issues.append({
                                    "type": "forbidden_function",
                                    "severity": "warning",
                                    "location": f"{ws.title}!{cell.coordinate}",
                                    "function": func,
                                    "formula": cell.value[:80],
                                })

                        # Implicit array formula
                        if IMPLICIT_ARRAY_PATTERN.search(cell.value):
                            issues.append({
                                "type": "implicit_array",
                                "severity": "warning",
                                "location": f"{ws.title}!{cell.coordinate}",
                                "formula": cell.value[:80],
                                "hint": "Use SUMPRODUCT or helper column instead of MATCH(TRUE(), ...)",
                            })
    except Exception as e:
        issues.append({"type": "load_error", "severity": "error", "detail": str(e)})

    if missing_formula_cache_locations:
        sample_limit = 20
        issues.append({
            "type": "formula_cache_missing",
            "severity": "warning",
            "count": len(missing_formula_cache_locations),
            "locations": missing_formula_cache_locations[:sample_limit],
            "omitted_location_count": max(
                0, len(missing_formula_cache_locations) - sample_limit
            ),
            "detail": "Formula cells have no cached results, so their outcomes were not evaluated.",
            "hint": "Recalculate with Excel/WPS/LibreOffice or independently verify every reported derived value from the raw inputs.",
        })

    # Output
    errors = [i for i in issues if i['severity'] == 'error']
    warnings = [i for i in issues if i['severity'] == 'warning']

    has_missing_formula_cache = any(
        issue.get("type") == "formula_cache_missing" for issue in issues
    )
    status = (
        "fail"
        if errors
        else "unverified"
        if has_missing_formula_cache
        else "pass_with_warnings"
        if warnings
        else "pass"
    )

    result = {
        "status": status,
        "file": filepath,
        "formula_count": formula_count,
        "formula_cache_missing_count": len(missing_formula_cache_locations),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": issues,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if not errors else 1)


def main():
    parser = argparse.ArgumentParser(description="Excel formula tools")
    subparsers = parser.add_subparsers(dest="command")

    recalc_p = subparsers.add_parser("recalc", help="Recalculate all formulas")
    recalc_p.add_argument("file", help="Excel file path")
    recalc_p.set_defaults(func=cmd_recalc)

    verify_p = subparsers.add_parser("verify", help="Verify formula errors and forbidden functions")
    verify_p.add_argument("file", help="Excel file path")
    verify_p.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
