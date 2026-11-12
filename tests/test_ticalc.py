import pathlib
import shutil

import pytest

from ticalc import api, programs
from ticalc.api import TnsError
from ticalc.cli import main
from ticalc.tixc_decode import decode_tixc
from ticalc.tixc_encode import encode_tixc

DATA = pathlib.Path(__file__).parent / "data"
SAMPLES = sorted(DATA.glob("*.tns"))
ACTUAL = DATA / "Actual.tns"


def test_samples_present():
    assert len(SAMPLES) >= 3


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda p: p.name)
def test_roundtrip_is_lossless(sample):
    assert api.roundtrip_check(sample) == []


def test_actual_program_counts():
    defs = programs.extract(ACTUAL)
    assert sum(d.kind == "Prgm" for d in defs) == 20
    assert sum(d.kind == "Func" for d in defs) == 11
    colour = next(d for d in defs if d.name == "colour")
    assert colour.to_source() == "Define colour()=Func\n  Return randInt(1,m)\nEndFunc"


def test_encode_adds_and_replaces(tmp_path):
    src = tmp_path / "new.txt"
    src.write_text(
        'Define zz_add(a,b)=Func\n  Local t\n  t:=a+b\n  Return t\nEndFunc\n\n'
        'Define colour()=Func\n  Return 42\nEndFunc\n\n'
        'Define aa_show()=Prgm\n  Disp "hi"\n  Define inner()=Func\n    Return 1\n  EndFunc\nEndPrgm\n',
        encoding="utf-8",
    )
    out = tmp_path / "out.tns"
    before = ACTUAL.read_bytes()
    programs.encode(src, ACTUAL, out)
    assert ACTUAL.read_bytes() == before
    by_name = {d.name: d for d in programs.extract(out)}
    assert len(by_name) == 33
    assert by_name["zz_add"].params == "a,b"
    assert by_name["colour"].body[0] == "  Return 42"
    assert "Define inner()=Func" in by_name["aa_show"].to_source()
    assert api.roundtrip_check(out) == []


def test_extracted_source_can_be_reencoded(tmp_path):
    listing = tmp_path / "all.txt"
    assert main(["programs", str(ACTUAL), "-o", str(listing)]) == 0
    out = tmp_path / "again.tns"
    assert main(["encode", str(listing), "--base", str(ACTUAL), "-o", str(out)]) == 0
    assert programs.extract(out) == programs.extract(ACTUAL)


@pytest.mark.parametrize(
    "text, message",
    [
        ("Disp 1\n", "expected 'Define"),
        ("Define f()=Prgm\nDisp 1\n", "missing EndPrgm"),
        ("Define f()=Prgm\nEndFunc\n", "does not match"),
        ("Define f()=Prgm\nEndPrgm\nDefine F()=Prgm\nEndPrgm\n", "duplicate"),
        ("\n\n", "no Define"),
    ],
)
def test_bad_source_is_rejected(text, message):
    with pytest.raises(TnsError, match=message):
        programs.parse_source(text)


def test_encode_refuses_to_overwrite_base(tmp_path):
    src = tmp_path / "s.txt"
    src.write_text("Define f()=Prgm\nEndPrgm\n")
    base = tmp_path / "b.tns"
    shutil.copy(ACTUAL, base)
    with pytest.raises(TnsError, match="must differ"):
        programs.encode(src, base, base)


def test_encode_rejects_variable_name_collision(tmp_path):
    src = tmp_path / "s.txt"
    src.write_text("Define abc()=Prgm\nEndPrgm\n")
    with pytest.raises(TnsError, match="variable"):
        programs.encode(src, ACTUAL, tmp_path / "o.tns")
    assert not (tmp_path / "o.tns").exists()


def test_missing_and_invalid_inputs(tmp_path, capsys):
    assert main(["info", str(tmp_path / "nope.tns")]) == 1
    assert "file not found" in capsys.readouterr().err
    junk = tmp_path / "junk.tns"
    junk.write_bytes(b"this is not a tns file" * 10)
    assert main(["decode", str(junk)]) == 1
    assert capsys.readouterr().err.startswith("error:")
    empty = tmp_path / "empty.tns"
    empty.write_bytes(b"")
    assert main(["programs", str(empty)]) == 1
    assert "empty" in capsys.readouterr().err
    assert main(["build", str(tmp_path)]) == 1
    assert "no .xml files" in capsys.readouterr().err


def test_decode_then_build(tmp_path, capsys):
    xml_dir = tmp_path / "x"
    assert main(["decode", str(ACTUAL), "-o", str(xml_dir)]) == 0
    assert (xml_dir / "Problem1.xml").is_file()
    assert main(["build", str(xml_dir), "-o", str(tmp_path / "r.tns")]) == 0
    assert "verified" in capsys.readouterr().out


def test_tixc_roundtrip_with_repeated_tags():
    xml = (
        b'<?xml version="1.0" encoding="UTF-8" ?>'
        b"<root><row><text>first</text></row>"
        b"<row><text>    leading spaces</text></row>"
        b'<item kind="one">first</item><item kind="two">second</item></root>'
    )
    assert decode_tixc(encode_tixc(xml)) == xml
