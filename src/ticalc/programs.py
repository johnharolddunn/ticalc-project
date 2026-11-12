"""Read and write TI-Basic programs/functions stored in a TI-Nspire document.

Stored programs are ``<e t="7">`` (Prgm) and functions ``<e t="6">`` (Func) entries
in a problem's ``<sym>`` table. Writing edits that table as text so that every
other part of the document is left byte-for-byte untouched.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import tempfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from . import api
from .api import TnsError

KIND_BY_TYPE = {"6": "Func", "7": "Prgm"}
_DEFINE_RE = re.compile(r"^\s*Define\s+([A-Za-z_][\w.]*)\s*\(([^)]*)\)\s*=\s*(Prgm|Func)\s*$")
_END_RE = re.compile(r"^\s*End(Prgm|Func)\s*$")
_PROBLEM_RE = re.compile(r"^Problem(\d+)\.xml$", re.IGNORECASE)


@dataclasses.dataclass(frozen=True)
class Definition:
    name: str
    kind: str  # "Prgm" or "Func"
    params: str  # comma separated, may be empty
    body: tuple[str, ...]  # every line after the header, including the End line

    def to_source(self) -> str:
        head = f"Define {self.name}({self.params})={self.kind}"
        return "\n".join((head, *self.body))

    def to_stored(self) -> str:
        return self.kind + "".join(f"\r:{line}" for line in self.body)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _lines_from_stored(value: str) -> tuple[str, list[str]]:
    parts = value.replace("\r\n", "\r").replace("\n", "\r").split("\r")
    first = parts[0].strip()
    return first, [p[1:] if p.startswith(":") else p for p in parts[1:]]


def definitions_from_xml(xml: bytes) -> list[Definition]:
    """Return the top-level programs and functions stored in one problem's XML."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise TnsError(f"document XML is malformed: {exc}") from exc
    sym = next((c for c in root if _local(c.tag) == "sym"), None)
    out: list[Definition] = []
    if sym is None:
        return out
    for e in sym:
        kind = KIND_BY_TYPE.get(e.get("t", ""))
        if _local(e.tag) != "e" or kind is None:
            continue
        fields = {_local(c.tag): (c.text or "") for c in e}
        _, body = _lines_from_stored(fields.get("v", ""))
        out.append(Definition(fields.get("n", ""), kind, fields.get("p", ""), tuple(body)))
    return out


def extract(tns_path: str | pathlib.Path) -> list[Definition]:
    """All stored programs and functions of a .tns, in document order."""
    docs = api.read_xml(tns_path)
    defs: list[Definition] = []
    for name in sorted(docs, key=_problem_sort):
        if _PROBLEM_RE.match(name):
            defs.extend(definitions_from_xml(docs[name]))
    return defs


def _problem_sort(name: str) -> tuple[int, str]:
    m = _PROBLEM_RE.match(name)
    return (int(m.group(1)) if m else 10**9, name)


def format_listing(defs: list[Definition], *, headers: bool = False, unique: bool = False) -> str:
    seen: set[str] = set()
    blocks: list[str] = []
    for d in defs:
        text = d.to_source()
        if unique:
            key = " ".join(text.split())
            if key in seen:
                continue
            seen.add(key)
        blocks.append((f"\u00a9 {d.kind} {d.name}\n" if headers else "") + text)
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def parse_source(text: str) -> list[Definition]:
    """Parse ``Define name(args)=Prgm|Func ... EndPrgm|EndFunc`` blocks from text."""
    lines = text.lstrip("\ufeff").splitlines()
    defs: list[Definition] = []
    names: set[str] = set()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = _DEFINE_RE.match(line)
        if not m:
            raise TnsError(
                f"line {i + 1}: expected 'Define name(args)=Prgm' or '=Func' at top level, got: {line.strip()[:60]!r}"
            )
        name, params, kind = m.group(1), re.sub(r"\s+", "", m.group(2)), m.group(3)
        if name.lower() in names:
            raise TnsError(f"line {i + 1}: duplicate definition of {name!r}")
        names.add(name.lower())
        stack = [kind]
        body: list[str] = []
        start = i + 1
        i += 1
        while i < len(lines) and stack:
            cur = lines[i]
            body.append(cur)
            nested = _DEFINE_RE.match(cur)
            end = _END_RE.match(cur)
            if nested:
                stack.append(nested.group(3))
            elif end:
                if end.group(1) != stack[-1]:
                    raise TnsError(f"line {i + 1}: End{end.group(1)} does not match open {stack[-1]}")
                stack.pop()
            i += 1
        if stack:
            raise TnsError(f"line {start}: definition of {name!r} is missing End{stack[0]}")
        defs.append(Definition(name, kind, params, tuple(body)))
    if not defs:
        raise TnsError("no Define ... Prgm/Func blocks found in the source text")
    return defs


def _entry_xml(d: Definition) -> str:
    t = "6" if d.kind == "Func" else "7"
    stored = escape(d.to_stored(), {'"': "&quot;", "\r": "&#13;"})
    return f'<e t="{t}" f="0" c="0"><n>{escape(d.name)}</n><p>{escape(d.params)}</p><v>{stored}</v></e>'


_ENTRY_RE = re.compile(r'(?s)<e t="(\d+)"[^>]*><n>([^<]*)</n>.*?</e>')


def upsert(xml_text: str, defs: list[Definition]) -> str:
    """Insert or replace definitions in a problem's ``<sym>`` table."""
    if "<sym>" not in xml_text or "</sym>" not in xml_text:
        raise TnsError("the base document has no symbol table; use a calculator-made .tns as --base")
    for d in defs:
        new = _entry_xml(d)
        sym_start = xml_text.index("<sym>")
        sym_end = xml_text.index("</sym>")
        sym = xml_text[sym_start:sym_end]
        existing = [m for m in _ENTRY_RE.finditer(sym) if m.group(2) == escape(d.name)]
        if existing:
            m = existing[0]
            if m.group(1) not in KIND_BY_TYPE:
                raise TnsError(f"{d.name!r} already exists in the base document as a variable, not a program/function")
            a, b = sym_start + m.start(), sym_start + m.end()
            xml_text = xml_text[:a] + new + xml_text[b:]
            continue
        pos = sym_end
        for m in _ENTRY_RE.finditer(sym):
            if m.group(2).casefold() > escape(d.name).casefold():
                pos = sym_start + m.start()
                break
        xml_text = xml_text[:pos] + new + xml_text[pos:]
    return xml_text


def encode(source: str | pathlib.Path, base_tns: str | pathlib.Path, out_tns: str | pathlib.Path, *, problem: int = 1) -> list[Definition]:
    """Store the definitions from a text file into a copy of ``base_tns``.

    The result is decoded again and every definition is compared with the input,
    so a file that silently lost or changed code is never left behind.
    """
    src = pathlib.Path(source)
    if not src.is_file():
        raise TnsError(f"source file not found: {src}")
    try:
        text = src.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TnsError(f"source file must be UTF-8 text: {exc}") from exc
    defs = parse_source(text)

    base = api.check_tns_file(base_tns)
    out = pathlib.Path(out_tns)
    if out.resolve() == base.resolve():
        raise TnsError("output must differ from --base (the base file is never overwritten)")
    with tempfile.TemporaryDirectory(prefix="ticalc-") as tmp:
        xml_dir = api.decode(base, pathlib.Path(tmp) / "x")
        problems = sorted(p for p in xml_dir.glob("*.xml") if _PROBLEM_RE.match(p.name))
        target = xml_dir / f"Problem{problem}.xml"
        if not target.is_file():
            have = ", ".join(p.name for p in problems) or "none"
            raise TnsError(f"base document has no Problem{problem}.xml (found: {have})")
        target.write_bytes(upsert(target.read_text(encoding="utf-8"), defs).encode("utf-8"))
        api.build(xml_dir, out, verify=True)

    stored = {d.name: d for d in extract(out)}
    for d in defs:
        got = stored.get(d.name)
        if got != d:
            out.unlink(missing_ok=True)
            raise TnsError(f"verification failed for {d.name!r}; output removed")
    return defs
