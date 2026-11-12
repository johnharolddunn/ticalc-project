"""Safe, validated wrappers around the low-level TNS container code."""

from __future__ import annotations

import contextlib
import io
import pathlib
import tempfile
from collections.abc import Iterator

from . import container
from .tns_outer_parse import describe_entries, parse_tns


class TnsError(Exception):
    """A problem the user can fix (bad path, not a TNS file, bad input)."""


def check_tns_file(path: str | pathlib.Path) -> pathlib.Path:
    """Return ``path`` as a Path after verifying it looks like a readable .tns file."""
    p = pathlib.Path(path)
    if not p.exists():
        raise TnsError(f"file not found: {p}")
    if not p.is_file():
        raise TnsError(f"not a file: {p}")
    if p.stat().st_size == 0:
        raise TnsError(f"file is empty: {p}")
    return p


def _entries(path: pathlib.Path):
    data = path.read_bytes()
    try:
        entries = parse_tns(data)
    except Exception as exc:
        raise TnsError(f"{path} is not a valid TI-Nspire document ({exc})") from exc
    if not entries:
        raise TnsError(f"{path} is not a valid TI-Nspire document (no entries found)")
    return data, entries


def describe(path: str | pathlib.Path) -> str:
    """Human-readable listing of the files stored inside a .tns document."""
    p = check_tns_file(path)
    data, entries = _entries(p)
    return describe_entries(data, entries)


@contextlib.contextmanager
def _quiet() -> Iterator[None]:
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def decode(path: str | pathlib.Path, out_dir: str | pathlib.Path | None = None) -> pathlib.Path:
    """Decode a .tns into a folder of readable XML files and return that folder.

    A hidden ``_artifacts`` subfolder keeps what is needed to rebuild the file.
    """
    p = check_tns_file(path)
    _entries(p)
    out = pathlib.Path(out_dir) if out_dir else pathlib.Path(f"{p.name}.xml")
    if out.exists() and not out.is_dir():
        raise TnsError(f"output path exists and is not a folder: {out}")
    try:
        with _quiet():
            container.decode_tns_file(p, out, artifacts=True, tixc_backend_kind="pure")
    except TnsError:
        raise
    except Exception as exc:
        raise TnsError(f"could not decode {p}: {exc}") from exc
    if not any(out.glob("*.xml")):
        raise TnsError(f"{p} contained no XML documents")
    return out


def build(xml_dir: str | pathlib.Path, out_tns: str | pathlib.Path | None = None, *, verify: bool = True) -> pathlib.Path:
    """Build a .tns from a folder produced by :func:`decode`; optionally verify it."""
    d = pathlib.Path(xml_dir)
    if not d.is_dir():
        raise TnsError(f"not a folder: {d}")
    if not any(d.glob("*.xml")):
        raise TnsError(f"no .xml files found in {d}")
    out = pathlib.Path(out_tns) if out_tns else pathlib.Path(d.name.removesuffix(".xml") + ".rebuilt.tns")
    if out.exists() and out.is_dir():
        raise TnsError(f"output path is a folder: {out}")
    try:
        with _quiet():
            container.build_tns_from_xml(d, out)
    except Exception as exc:
        raise TnsError(f"could not build {out}: {exc}") from exc
    if verify:
        mismatches = compare_to_xml(out, d)
        if mismatches:
            out.unlink(missing_ok=True)
            raise TnsError("rebuilt file did not match its XML source: " + "; ".join(mismatches[:5]))
    return out


def read_xml(path: str | pathlib.Path) -> dict[str, bytes]:
    """Return ``{entry name: XML bytes}`` for every document inside a .tns."""
    with tempfile.TemporaryDirectory(prefix="ticalc-") as tmp:
        d = decode(path, pathlib.Path(tmp) / "x")
        return {
            f.relative_to(d).as_posix(): f.read_bytes()
            for f in sorted(d.rglob("*.xml"))
            if "_artifacts" not in f.parts
        }


def compare_to_xml(tns_path: pathlib.Path, xml_dir: pathlib.Path) -> list[str]:
    """Decode ``tns_path`` and list differences against the XML files in ``xml_dir``."""
    got = read_xml(tns_path)
    problems: list[str] = []
    for src in sorted(xml_dir.rglob("*.xml")):
        if "_artifacts" in src.parts:
            continue
        rel = src.relative_to(xml_dir).as_posix()
        if rel not in got:
            problems.append(f"missing {rel}")
        elif got[rel] != src.read_bytes():
            problems.append(f"differs {rel}")
    return problems


def roundtrip_check(path: str | pathlib.Path) -> list[str]:
    """Decode -> rebuild -> decode a .tns and report any XML differences (empty = OK)."""
    p = check_tns_file(path)
    with tempfile.TemporaryDirectory(prefix="ticalc-") as tmp:
        t = pathlib.Path(tmp)
        xml_dir = decode(p, t / "x")
        rebuilt = build(xml_dir, t / "r.tns", verify=False)
        return compare_to_xml(rebuilt, xml_dir)
