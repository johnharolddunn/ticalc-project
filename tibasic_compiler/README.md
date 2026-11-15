# TI-Basic → EXE Compiler

Lives only in this folder (`TiCalc\TiBasicCompiler`). Input in `Input\`, temp files in `Build\`, executables in `Output\`.

Run: `python tibasic_compiler.py [Input\file.txt] [--entry NAME] [--console]`

A window shows this note; press **Continue** to compile. The text is analysed first: it compiles only if a
`Define x()=Prgm … EndPrgm` exists (functions defined inside are included). Function-only files are rejected.
Calculator I/O maps to the console: Disp/Text → print, Request/RequestStr → prompt, ClrIO → cls, Pause, Delay, getKey.
Not supported: Goto/Lbl (skipped with a warning), matrices/graphics. Needs Python + PyInstaller (auto-installed).

## PC file access (extension commands)
These work only in the compiled exe (not on a real calculator). The compiler reports "PC FILE ACCESS detected" when a program uses them.

| Command | Meaning |
|---|---|
| `readlines(path)` | file -> list of text lines |
| `readnums(path)` | file -> list of numbers (one per line, or comma/space/semicolon separated) |
| `WriteLines path, list` | write a list (or text) to a file, replacing it |
| `AppendLines path, list` | add lines to the end of a file |
| `DelFile path` | delete a file |
| `fileexists(path)`, `filelist(folder)` | check a file / list a folder |
| `pickfile()`, `picksave()` | Windows Open / Save dialog, returns the path ("" if cancelled) |
| `arg(n)`, `argcount()` | files dragged onto the exe / command-line arguments |
| `split(text, sep)` | split text into a list |

Overwrite protection: the first time a program would overwrite or delete an existing file, the exe warns and asks Y/N once. After Yes it carries on without asking again. See `Input\filedemo.txt`.
