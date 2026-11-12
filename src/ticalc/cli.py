"""Command line interface: ``ticalc <command> ...``."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import traceback

from . import __version__, api, programs
from .api import TnsError


def _cmd_info(a: argparse.Namespace) -> int:
    print(api.describe(a.file))
    defs = programs.extract(a.file)
    print(f"\nstored programs: {sum(d.kind == 'Prgm' for d in defs)}, functions: {sum(d.kind == 'Func' for d in defs)}")
    return 0


def _cmd_decode(a: argparse.Namespace) -> int:
    out = api.decode(a.file, a.out)
    n = sum(1 for f in out.rglob("*.xml") if "_artifacts" not in f.parts)
    print(f"decoded {n} XML document(s) to {out}")
    return 0


def _cmd_build(a: argparse.Namespace) -> int:
    out = api.build(a.folder, a.out, verify=not a.no_verify)
    print(f"built {out}" + ("" if a.no_verify else " (verified)"))
    return 0


def _cmd_programs(a: argparse.Namespace) -> int:
    defs = programs.extract(a.file)
    if not defs:
        raise TnsError(f"no stored programs or functions found in {a.file}")
    if a.format == "json":
        text = json.dumps(
            [{"name": d.name, "kind": d.kind, "params": d.params, "source": d.to_source()} for d in defs],
            indent=2,
            ensure_ascii=False,
        ) + "\n"
    else:
        text = programs.format_listing(defs, headers=a.headers, unique=a.unique)
    if a.out:
        out = pathlib.Path(a.out)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {len(defs)} definition(s) to {out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stdout.write(text)
    return 0


def _cmd_encode(a: argparse.Namespace) -> int:
    defs = programs.encode(a.source, a.base, a.out, problem=a.problem)
    print(f"wrote {a.out} with {len(defs)} definition(s) (verified by decoding it again)")
    return 0


def _cmd_check(a: argparse.Namespace) -> int:
    files: list[pathlib.Path] = []
    for item in a.paths:
        p = pathlib.Path(item)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.tns")))
        else:
            files.append(p)
    if not files:
        raise TnsError("no .tns files to check")
    bad = 0
    for f in files:
        try:
            problems = api.roundtrip_check(f)
        except TnsError as exc:
            problems = [str(exc)]
        print(f"{'ok  ' if not problems else 'FAIL'} {f}" + ("" if not problems else f"  ({'; '.join(problems[:3])})"))
        bad += bool(problems)
    print(f"{len(files) - bad}/{len(files)} passed")
    return 1 if bad else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ticalc",
        description="Inspect, extract and rebuild TI-Nspire .tns documents (pure Python, no calculator software needed).",
    )
    p.add_argument("--version", action="version", version=f"ticalc {__version__}")
    p.add_argument("--debug", action="store_true", help="show full tracebacks on errors")
    sub = p.add_subparsers(dest="command", required=True, metavar="command")

    s = sub.add_parser("info", help="list a .tns file's contents and count stored programs/functions")
    s.add_argument("file")
    s.set_defaults(func=_cmd_info)

    s = sub.add_parser("decode", help="decode a .tns file into a folder of readable XML")
    s.add_argument("file")
    s.add_argument("-o", "--out", help="output folder (default: <file>.xml)")
    s.set_defaults(func=_cmd_decode)

    s = sub.add_parser("build", help="build a .tns file from a folder made by 'decode'")
    s.add_argument("folder")
    s.add_argument("-o", "--out", help="output .tns (default: <folder>.rebuilt.tns)")
    s.add_argument("--no-verify", action="store_true", help="skip decoding the result to confirm it matches")
    s.set_defaults(func=_cmd_build)

    s = sub.add_parser("programs", help="print the TI-Basic programs and functions stored in a .tns")
    s.add_argument("file")
    s.add_argument("-o", "--out", help="write to a file instead of the screen")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.add_argument("--headers", action="store_true", help="add a comment line before each definition")
    s.add_argument("--unique", action="store_true", help="drop definitions that are identical apart from whitespace")
    s.set_defaults(func=_cmd_programs)

    s = sub.add_parser("encode", help="store TI-Basic 'Define ...' text into a copy of an existing .tns")
    s.add_argument("source", help="text file with Define name(args)=Prgm/Func ... EndPrgm/EndFunc blocks")
    s.add_argument("--base", required=True, help="calculator-made .tns to start from (never modified)")
    s.add_argument("-o", "--out", required=True, help="new .tns to write")
    s.add_argument("--problem", type=int, default=1, help="problem number to store into (default 1)")
    s.set_defaults(func=_cmd_encode)

    s = sub.add_parser("check", help="self-test: decode, rebuild and re-decode .tns files and compare")
    s.add_argument("paths", nargs="+", help=".tns files or folders containing them")
    s.set_defaults(func=_cmd_check)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except TnsError as exc:
        print(f"error: {exc}", file=sys.stderr)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
    except Exception as exc:  # never show a raw traceback unless asked
        if args.debug:
            traceback.print_exc()
        print(f"error: unexpected failure ({type(exc).__name__}: {exc}). Re-run with --debug for details.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
