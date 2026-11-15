import pathlib
import sys

import pytest

from ticalc import programs

COMPILER_DIR = pathlib.Path(__file__).parent.parent / "tibasic_compiler"
EXAMPLES = sorted((COMPILER_DIR / "examples").glob("*.txt"))
sys.path.insert(0, str(COMPILER_DIR))
import tibasic_compiler as tbc  # noqa: E402


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_example_translates_to_valid_python(example):
    text = example.read_text(encoding="utf-8-sig")
    analysis = tbc.analyse(text)
    assert analysis["errors"] == []
    entry = analysis["programs"][0]["name"]
    code, _ = tbc.translate(text, analysis, entry)
    compile(code, example.name, "exec")


def test_unclosed_block_is_reported():
    analysis = tbc.analyse("Define a()=Prgm\nDisp 1\n")
    assert analysis["errors"]


def test_library_example_is_valid_ticalc_source():
    lib = COMPILER_DIR / "examples" / "Set-And-Multiset-Library.txt"
    assert programs.parse_source(lib.read_text(encoding="utf-8-sig"))
