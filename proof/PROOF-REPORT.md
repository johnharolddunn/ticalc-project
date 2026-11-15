# Proof report

Generated 2026-11-15 by `python proof/run_proof.py`.

| Area | Item | Result | Detail |
|---|---|---|---|
| Decode | Actual.tns | PASS | 2 XML documents; decode -> rebuild -> decode identical; sha256 1ff5dd60a965 |
| Decode | testcode.tns | PASS | 2 XML documents; decode -> rebuild -> decode identical; sha256 4c1b0371d2d6 |
| Decode | TestDecode.tns | PASS | 2 XML documents; decode -> rebuild -> decode identical; sha256 a49fffe6ab3c |
| Decode | Actual.tns programs | PASS | 20 programs, 11 functions |
| Encode | Set-And-Multiset-Library.txt | PASS | 19 definitions stored, decoded back identical, base unchanged |
| Compile | demo.txt | PASS | entry 'demo', 2 definitions, generated Python compiles |
| Compile | filedemo.txt | PASS | entry 'filedemo', 1 definitions, generated Python compiles |
| Compile | Set-And-Multiset-Library.txt | PASS | entry 'set_uses', 19 definitions, generated Python compiles |
| Compile | stats.txt | PASS | entry 'stats', 2 definitions, generated Python compiles |

What this proves: files decode, rebuild and re-decode identically; encoded programs read back identically;
TI-Basic examples translate to valid Python. What it does not prove: TI-Nspire software accepting or running
an encoded file, or the compiled `.exe` running (see `compile-run-proof/` for one recorded real run).
