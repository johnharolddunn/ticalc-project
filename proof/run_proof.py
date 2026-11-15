"""Regenerate proof/PROOF-REPORT.md: decode, encode and compile checks on the bundled samples.

Run from the repo root:  python proof/run_proof.py
Exit code 0 means every check passed.
"""

from __future__ import annotations

import datetime
import hashlib
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tibasic_compiler"))

import tibasic_compiler as tbc  # noqa: E402
from ticalc import api, programs  # noqa: E402

DATA = ROOT / "tests" / "data"
EXAMPLES = ROOT / "tibasic_compiler" / "examples"
OUT = pathlib.Path(__file__).resolve().parent
rows: list[tuple[str, str, bool, str]] = []


def check(section: str, name: str, fn) -> None:
    try:
        ok, detail = fn()
    except Exception as exc:  # report, never crash
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    rows.append((section, name, ok, detail))


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


for tns in sorted(DATA.glob("*.tns")):
    check("Decode", tns.name, lambda t=tns: (
        not api.roundtrip_check(t),
        f"{len(api.read_xml(t))} XML documents; decode -> rebuild -> decode identical; sha256 {sha(t)}",
    ))

actual = DATA / "Actual.tns"


def count_check():
    d = programs.extract(actual)
    p = sum(x.kind == "Prgm" for x in d)
    f = sum(x.kind == "Func" for x in d)
    return (p, f) == (20, 11), f"{p} programs, {f} functions"


check("Decode", "Actual.tns programs", count_check)
(OUT / "Actual-programs.txt").write_text(programs.format_listing(programs.extract(actual)), encoding="utf-8")


def encode_check(src: pathlib.Path):
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "out.tns"
        before = sha(actual)
        defs = programs.encode(src, actual, out)
        names = {d.name for d in programs.extract(out)}
        ok = all(d.name in names for d in defs) and not api.roundtrip_check(out) and sha(actual) == before
        return ok, f"{len(defs)} definitions stored, decoded back identical, base unchanged"


check("Encode", "Set-And-Multiset-Library.txt", lambda: encode_check(EXAMPLES / "Set-And-Multiset-Library.txt"))


def compile_check(src: pathlib.Path):
    text = src.read_text(encoding="utf-8-sig")
    a = tbc.analyse(text)
    if a["errors"] or not a["programs"]:
        return False, f"analysis: {a['errors'] or 'no Prgm'}"
    code, _ = tbc.translate(text, a, a["programs"][0]["name"])
    compile(code, src.name, "exec")
    return True, f"entry '{a['programs'][0]['name']}', {len(a['defs'])} definitions, generated Python compiles"


for src in sorted(EXAMPLES.glob("*.txt")):
    check("Compile", src.name, lambda s=src: compile_check(s))

lines = [
    "# Proof report",
    "",
    f"Generated {datetime.date.today()} by `python proof/run_proof.py`.",
    "",
    "| Area | Item | Result | Detail |",
    "|---|---|---|---|",
]
lines += [f"| {s} | {n} | {'PASS' if ok else 'FAIL'} | {d} |" for s, n, ok, d in rows]
lines += [
    "",
    "What this proves: files decode, rebuild and re-decode identically; encoded programs read back identically;",
    "TI-Basic examples translate to valid Python. What it does not prove: TI-Nspire software accepting or running",
    "an encoded file, or the compiled `.exe` running (see `compile-run-proof/` for one recorded real run).",
    "",
]
(OUT / "PROOF-REPORT.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
sys.exit(0 if all(ok for *_, ok, _ in rows) else 1)
