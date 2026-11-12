# ticalc — TI-Nspire `.tns` toolkit

Pure-Python tool for working with TI-Nspire documents (`.tns`) **without** the calculator software:

- **See what is inside** a document and **recover every stored TI-Basic program and function** as plain text.
- **Decode** a `.tns` to readable XML and **rebuild** it (lossless, self-verifying).
- **Store TI-Basic text** (`Define name(args)=Prgm … EndPrgm`) into a copy of an existing document.

It was consolidated from a larger collection of PowerShell/Python experiments; the container,
encryption and compression handling is all Python now, and PowerShell 7 is just an optional front end.

## Who is this for / what problem does it solve?

TI-Nspire calculator documents (`.tns`) are a closed, compressed and partly encrypted format.
If you wrote TI-Basic programs on the calculator or in the TI-Nspire software and want to
**back them up, read them as text, edit them on a computer, or put them back**, this tool does that
from the command line without needing the TI software. It is a read/rebuild tool, not an emulator.

## Install

Requires Python 3.10+ (and `pip`).

```powershell
git clone https://github.com/johnharolddunn/ticalc-project ; cd ticalc-project
python -m venv .venv ; .\.venv\Scripts\Activate.ps1    # Linux/macOS: source .venv/bin/activate
pip install .
```

## Use

```text
ticalc info      FILE.tns                    contents + number of programs/functions
ticalc programs  FILE.tns [-o out.txt] [--format json] [--headers] [--unique]
ticalc decode    FILE.tns [-o FOLDER]        readable XML (plus hidden _artifacts to rebuild)
ticalc build     FOLDER   [-o out.tns]       rebuild; decodes the result to prove it matches
ticalc encode    code.txt --base FILE.tns -o NEW.tns [--problem N]
ticalc check     FILE.tns|FOLDER...          decode → rebuild → decode self-test
```

Typical uses:

```powershell
ticalc programs Actual.tns -o my-programs.txt        # get your code out
ticalc encode my-programs.txt --base Actual.tns -o Actual-edited.tns   # put edited code back
```

`encode` accepts complete `Define name(args)=Prgm` / `=Func` blocks (nested definitions allowed). It
**does not check TI-Basic syntax** and always works on a *copy* of a calculator-made `--base` document
(the base is never modified, and the output must be a different path). After writing, it decodes the
new file and confirms every definition came back identical; otherwise the output is deleted and an
error is shown. Always open the result in TI-Nspire software to confirm it runs.

## PowerShell 7 front end

```powershell
./scripts/ticalc.ps1 programs Actual.tns        # forwards all arguments, keeps the exit code
./scripts/ticalc-menu.ps1                        # simple numbered menu
```

`ticalc.ps1` uses `.venv` if present, otherwise `python` on PATH, and installs the package on first run.

## Reliability

- Every input is validated (exists, non-empty, really a TNS container); problems give a one-line
  `error: …` message and exit code `1`, never a traceback (`--debug` shows one).
- Output files are verified by decoding them again before they are reported as written.
- Tests (`pytest`) run real `.tns` samples in `tests/data` through decode/rebuild round trips, program
  extraction (the large sample has 20 programs and 11 functions), encoding and error cases.
  GitHub Actions runs them on Linux and Windows, Python 3.10 and 3.13.

```powershell
pip install -e ".[dev]" ; pytest
```

## Quick start (3 steps)

1. Install as above, then check it works: `ticalc --version`
2. Get your code out: `ticalc programs MyDoc.tns -o my-programs.txt`
3. Edit the text, then put it back into a **copy**: `ticalc encode my-programs.txt --base MyDoc.tns -o MyDoc-edited.tns`

Your original file is never changed. Errors print one clear line starting with `error:`.

## Reporting a problem

Please [open a GitHub issue](https://github.com/johnharolddunn/ticalc-project/issues/new/choose),
or email **johnharoldpeterdunn@outlook.com**. Include the command you ran, the `error:` line, and
`ticalc --version`. Run again with `--debug` for full details. **Do not attach personal documents
you are not happy to share publicly.** This is a small hobby project maintained on a best-effort basis.

## License

MIT, see [LICENSE](LICENSE).

## Limits (honest notes)

- Only documents using the standard TNS container (compression method 13 or plain/deflate) are
  supported; others report a clear error.
- The Program Editor *widget tree* is not generated: programs are stored as symbols (visible to the
  calculator's catalog/variables), not as editor pages.
- `.tns`/`.xml` files are git-ignored except `tests/data/*.tns`, so personal documents are not committed by accident.
