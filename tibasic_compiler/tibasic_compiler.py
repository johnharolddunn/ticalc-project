r"""TI-Basic (TI-Nspire style) -> Windows EXE compiler.

Everything (inputs, work files, outputs) stays inside this folder:
  Input\   TI-Basic source text files
  Build\   intermediate Python + PyInstaller work files
  Output\  finished .exe files

Usage:  python tibasic_compiler.py [source.txt] [--entry NAME] [--console] [--no-pause]
"""
import os, re, sys, shutil, subprocess, time, threading

HERE = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(HERE, "Input")
BUILD_DIR = os.path.join(HERE, "Build")
OUTPUT_DIR = os.path.join(HERE, "Output")

README_NOTE = (
    "TI-Basic -> EXE Compiler\n\n"
    "NOTE: This compiler lives and runs in this subfolder only:\n"
    "    " + HERE + "\n\n"
    "  - Source text files are read from / copied into   Input\\\n"
    "  - Temporary work files are written to             Build\\\n"
    "  - Finished executables are written to             Output\\\n"
    "Nothing outside this folder is modified.\n\n"
    "How it works:\n"
    "  1. The text is analysed first. A compile only happens if it contains a\n"
    "     Program (Define name()=Prgm ... EndPrgm). Files with only functions\n"
    "     (Define f(x)=Func ... EndFunc) are reported and not compiled.\n"
    "     Functions defined inside a program are compiled along with it.\n"
    "  2. Calculator I/O is converted to PC console I/O\n"
    "     (Disp -> console print, Request -> keyboard prompt, ClrIO -> clear screen...).\n"
    "  3. The result is packaged as a standalone .exe.\n\n"
    "Press Continue to proceed."
)

IO_MAP = [
    ("disp", "Disp  ->  console line output"),
    ("text", "Text  ->  console line output"),
    ("request", "Request  ->  keyboard prompt on the console"),
    ("requeststr", "RequestStr  ->  keyboard prompt (text)"),
    ("clrio", "ClrIO  ->  clear the console window"),
    ("pause", "Pause  ->  'Press Enter' wait"),
    ("delay", "Delay  ->  sleep (milliseconds)"),
    ("getkey", "getKey()  ->  non-blocking key read"),
]

FILE_STMTS = ("writelines", "appendlines", "delfile")
FILE_FUNCS = ("readlines", "readnums", "filelist", "fileexists", "pickfile", "picksave", "arg", "argcount", "split")
FILE_WORDS = FILE_STMTS + FILE_FUNCS


class CompileError(Exception):
    pass


class NoProgram(CompileError):
    pass


# ---------------------------------------------------------------- text utils
def normalise(text):
    for a, b in (("\u2212", "-"), ("\u00d7", "*"), ("\u00f7", "/"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"')):
        text = text.replace(a, b)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_statements(line):
    """Split a physical line on ':' (not ':='), outside strings; strip (c) comments."""
    out, cur, instr, i = [], [], False, 0
    while i < len(line):
        c = line[i]
        if c == '"':
            instr = not instr
        if not instr:
            if c == "\u00a9":
                break
            if c == ":" and not line[i + 1:i + 2] == "=":
                out.append("".join(cur))
                cur = []
                i += 1
                continue
        cur.append(c)
        i += 1
    out.append("".join(cur))
    return [s.strip() for s in out if s.strip()]


def statements(text):
    res = []
    for n, line in enumerate(normalise(text).split("\n"), 1):
        for s in split_statements(line):
            res.append((n, s))
    return res


DEF_BLOCK = re.compile(r"^define\s+([a-z_][\w.]*)\s*\((.*?)\)\s*=\s*(prgm|func)\s*$", re.I)
DEF_INLINE = re.compile(r"^define\s+([a-z_][\w.]*)\s*\((.*?)\)\s*=\s*(.+)$", re.I)
DEF_VAR = re.compile(r"^define\s+([a-z_][\w.]*)\s*=\s*(.+)$", re.I)


# ------------------------------------------------------------------ analysis
def analyse(text):
    stack, defs, errors = [], [], []
    for n, s in statements(text):
        m = DEF_BLOCK.match(s)
        if m:
            d = dict(name=m.group(1).lower(), kind=m.group(3).lower(), line=n,
                     nested=len(stack) > 0, params=[p.strip().lower() for p in m.group(2).split(",") if p.strip()])
            defs.append(d)
            stack.append(d)
            continue
        low = s.lower()
        if low in ("endprgm", "endfunc"):
            want = "prgm" if low == "endprgm" else "func"
            if not stack:
                errors.append("line %d: %s without matching Define" % (n, s))
            elif stack[-1]["kind"] != want:
                errors.append("line %d: %s closes %s '%s'" % (n, s, stack[-1]["kind"], stack[-1]["name"]))
                stack.pop()
            else:
                stack.pop()
    for d in stack:
        errors.append("line %d: '%s' (%s) is never closed" % (d["line"], d["name"], d["kind"]))
    inline = [DEF_INLINE.match(s) for _, s in statements(text)]
    for m in inline:
        if m and m.group(3).lower() not in ("prgm", "func"):
            defs.append(dict(name=m.group(1).lower(), kind="func", line=0, nested=False,
                             params=[p.strip().lower() for p in m.group(2).split(",") if p.strip()]))
    return dict(
        programs=[d for d in defs if d["kind"] == "prgm"],
        functions=[d for d in defs if d["kind"] == "func"],
        errors=errors,
        defs=defs,
    )


# --------------------------------------------------------------- expressions
TOKEN = re.compile(
    r'''\s*(?:(?P<num>\d+\.?\d*(?:\u1d07[+-]?\d+)?|\.\d+)'''
    r'''|(?P<str>"(?:[^"]|"")*")'''
    r'''|(?P<id>[^\W\d][\w.]*|\u03c0|\u221a)'''
    r'''|(?P<op>:=|->|\u2192|<=|>=|\u2264|\u2265|\u2260|/=|<>|!=|[-+*/^&=<>(){}\[\],!]))''')
CMP = {"=": "==", "\u2260": "!=", "/=": "!=", "<>": "!=", "!=": "!=", "<": "<", ">": ">",
       "<=": "<=", ">=": ">=", "\u2264": "<=", "\u2265": ">="}
WORDS = {"and", "or", "xor", "not"}


def tokenize(s):
    toks, pos, s = [], 0, s.rstrip()
    while pos < len(s):
        m = TOKEN.match(s, pos)
        if not m:
            raise CompileError("Cannot read '%s'" % s[pos:pos + 12].strip())
        pos = m.end()
        k = m.lastgroup
        v = m.group(k)
        if k == "op" and v == "\u2192":
            v = "->"
        toks.append((k, v))
    return toks


class Gen:
    def __init__(self, known):
        self.known = set(known)
        self.lines = []
        self.ind = 0
        self.scopes = []
        self.blocks = []
        self.warnings = []
        self.used = set()
        self.alias = {}
        self.tmp = 0
        self.pending_single = False

    # ---- emit helpers
    def emit(self, s):
        self.lines.append("    " * self.ind + s)

    def close_pass(self):
        if self.lines and self.lines[-1].rstrip().endswith(":"):
            self.emit("    pass")

    # ---- variables
    def varref(self, name):
        name = name.lower()
        if name in self.alias:
            return self.alias[name]
        for sc in reversed(self.scopes):
            if name in sc["locals"]:
                return "v_" + re.sub(r"\W", "_", name)
        return "G[%r]" % name

    def target(self, name):
        name = name.lower()
        if self.scopes:
            if name in self.scopes[-1]["locals"]:
                return "v_" + re.sub(r"\W", "_", name)
            for sc in self.scopes[:-1]:
                if name in sc["locals"]:
                    self.scopes[-1]["nl"].add("v_" + re.sub(r"\W", "_", name))
                    return "v_" + re.sub(r"\W", "_", name)
        return "G[%r]" % name

    # ---- expression parsing
    def expr(self, text):
        return self.expr_toks(tokenize(text))

    def expr_toks(self, toks):
        p = _Parser(self, toks)
        r = p.or_()
        if p.i < len(toks):
            raise CompileError("Unexpected '%s' in expression" % toks[p.i][1])
        return r

    def args(self, toks):
        """Parse comma separated expression list from tokens."""
        p = _Parser(self, toks)
        out = []
        while p.i < len(toks):
            out.append(p.or_())
            if p.i < len(toks):
                if toks[p.i][1] != ",":
                    raise CompileError("Expected ',' but found '%s'" % toks[p.i][1])
                p.i += 1
        return out

    def assign(self, lhs_toks, value):
        if len(lhs_toks) == 1 and lhs_toks[0][0] == "id":
            self.emit("%s = cp(%s)" % (self.target(lhs_toks[0][1]), value))
        elif lhs_toks and lhs_toks[0][0] == "id" and lhs_toks[1][1] == "[" and lhs_toks[-1][1] == "]":
            idx = self.args(lhs_toks[2:-1])
            base = self.varref(lhs_toks[0][1])
            self.emit("setix(%s, %s, %s)" % (base, value, ", ".join(idx)))
        else:
            raise CompileError("Cannot store into that expression")

    # ---- statements
    def feed(self, n, s):
        try:
            self.stmt(s)
        except CompileError as e:
            raise CompileError("line %d: %s  [%s]" % (n, e, s))

    def stmt(self, s):
        low = s.lower()
        word = re.match(r"[a-z_]+", low)
        word = word.group(0) if word else ""
        rest = s[len(word):].strip() if word else s
        is_block_open = False

        m = DEF_BLOCK.match(s)
        if m:
            name, params, kind = m.group(1).lower(), [p.strip().lower() for p in m.group(2).split(",") if p.strip()], m.group(3).lower()
            self.emit("def f_%s(%s):" % (re.sub(r"\W", "_", name), ", ".join("v_" + re.sub(r"\W", "_", p) for p in params)))
            self.ind += 1
            self.scopes.append(dict(locals=set(params), nl=set(), head=len(self.lines), name=name))
            self.blocks.append(kind)
            return
        if low in ("endprgm", "endfunc"):
            self.close_pass()
            sc = self.scopes.pop()
            self.blocks.pop()
            if sc["nl"]:
                self.lines.insert(sc["head"], "    " * self.ind + "nonlocal " + ", ".join(sorted(sc["nl"])))
            self.ind -= 1
            return
        m = DEF_INLINE.match(s)
        if m:
            params = [p.strip().lower() for p in m.group(2).split(",") if p.strip()]
            self.scopes.append(dict(locals=set(params), nl=set(), head=0, name=m.group(1)))
            body = self.expr(m.group(3))
            self.scopes.pop()
            self.emit("def f_%s(%s): return %s" % (re.sub(r"\W", "_", m.group(1).lower()),
                                                 ", ".join("v_" + re.sub(r"\W", "_", p) for p in params), body))
            return
        m = DEF_VAR.match(s)
        if m:
            self.assign([("id", m.group(1))], self.expr(m.group(2)))
            return

        if not self.scopes:
            self.warnings.append("statement outside any Program/Function ignored: " + s)
            return

        if word == "local":
            for nm in [x.strip().lower() for x in rest.split(",") if x.strip()]:
                self.scopes[-1]["locals"].add(nm)
                self.emit("v_%s = 0" % re.sub(r"\W", "_", nm))
        elif word == "delvar":
            pass
        elif word == "if":
            m = re.match(r"^(.*?)\s+then$", rest, re.I)
            if m:
                self.emit("if %s:" % self.expr(m.group(1)))
                self.blocks.append("if")
                self.ind += 1
            else:
                self.emit("if %s:" % self.expr(rest))
                self.ind += 1
                self.pending_single = True
                return
        elif word == "elseif":
            self.close_pass(); self.ind -= 1
            self.emit("elif %s:" % self.expr(re.sub(r"\s+then$", "", rest, flags=re.I)))
            self.ind += 1
        elif word == "else":
            self.close_pass(); self.ind -= 1
            if self.blocks and self.blocks[-1] == "try":
                self.emit("except Exception:")
            else:
                self.emit("else:")
            self.ind += 1
        elif word in ("endif", "endfor", "endwhile", "endloop", "endtry"):
            self.close_pass(); self.ind -= 1
            self.blocks.pop()
        elif word == "for":
            a = tokenize(rest)
            if not a or a[0][0] != "id":
                raise CompileError("For needs a loop variable")
            parts = self.args(a[2:])
            if len(parts) < 2:
                raise CompileError("For needs start and end")
            self.tmp += 1
            t = "_t%d" % self.tmp
            self.emit("for %s in frange(%s):" % (t, ", ".join(parts)))
            self.blocks.append("for")
            self.ind += 1
            self.emit("%s = %s" % (self.target(a[0][1]), t))
        elif word == "while":
            self.emit("while %s:" % self.expr(rest)); self.blocks.append("while"); self.ind += 1
        elif word == "loop":
            self.emit("while True:"); self.blocks.append("loop"); self.ind += 1
        elif word == "try":
            self.emit("try:"); self.blocks.append("try"); self.ind += 1
        elif word == "exit":
            self.emit("break")
        elif word == "cycle":
            self.emit("continue")
        elif word == "stop":
            self.emit("raise SystemExit")
        elif word == "return":
            self.emit("return %s" % self.expr(rest) if rest else "return")
        elif word in ("disp", "text"):
            self.used.add(word)
            self.emit("disp(%s)" % ", ".join(self.args(tokenize(rest))) if rest else "print()")
        elif word in ("request", "requeststr"):
            self.used.add(word)
            t = tokenize(rest)
            depth, cut = 0, None
            for i, (k, v) in enumerate(t):
                depth += v in "([{" and k == "op"
                depth -= v in ")]}" and k == "op"
                if v == "," and depth == 0:
                    cut = i
                    break
            if cut is None:
                raise CompileError("%s needs a prompt and a variable" % word)
            end = len(t)
            for i in range(cut + 1, len(t)):
                if t[i][1] == ",":
                    end = i
                    break
            fn = "request" if word == "request" else "request_str"
            self.assign(t[cut + 1:end], "%s(%s)" % (fn, self.expr_toks(t[:cut])))
        elif word == "clrio":
            self.used.add(word); self.emit("clrio()")
        elif word == "pause":
            self.used.add(word); self.emit("pause(%s)" % ", ".join(self.args(tokenize(rest))))
        elif word == "delay":
            self.used.add(word); self.emit("delay(%s)" % self.expr(rest))
        elif word in FILE_STMTS:
            self.used.add(word)
            t = tokenize(rest)
            if t and t[0][1] == "(" and t[-1][1] == ")":
                t = t[1:-1]
            self.emit("call_builtin(%r, %s)" % (word, ", ".join(self.args(t))))
        elif word in ("goto", "lbl"):
            self.warnings.append("%s is not supported and was skipped: %s" % (word.title(), s))
            self.emit("pass")
        else:
            t = tokenize(s)
            depth, cut, kind = 0, None, None
            for i, (k, v) in enumerate(t):
                if k == "op":
                    depth += v in "([{"
                    depth -= v in ")]}"
                    if depth == 0 and v in (":=", "->"):
                        cut, kind = i, v
                        break
            if cut is None:
                self.emit(self.expr_toks(t))
            elif kind == ":=":
                self.assign(t[:cut], self.expr_toks(t[cut + 1:]))
            else:
                self.assign(t[cut + 1:], self.expr_toks(t[:cut]))
            if "getkey" in s.lower():
                self.used.add("getkey")

        if self.pending_single and not (word == "if" and not re.match(r"^(.*?)\s+then$", rest, re.I) is None):
            pass
        if self.pending_single:
            self.pending_single = False
            self.ind -= 1


class _Parser:
    def __init__(self, gen, toks):
        self.g, self.t, self.i = gen, toks, 0
        self.last_num = False

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def isop(self, *vals):
        k, v = self.peek()
        return k == "op" and v in vals

    def isword(self, *vals):
        k, v = self.peek()
        return k == "id" and v.lower() in vals

    def or_(self):
        l = self.and_()
        while self.isword("or", "xor"):
            w = self.t[self.i][1].lower(); self.i += 1
            r = self.and_()
            l = "(%s or %s)" % (l, r) if w == "or" else "(bool(%s) != bool(%s))" % (l, r)
        return l

    def and_(self):
        l = self.not_()
        while self.isword("and"):
            self.i += 1
            l = "(%s and %s)" % (l, self.not_())
        return l

    def not_(self):
        if self.isword("not"):
            self.i += 1
            return "(not %s)" % self.not_()
        return self.cmp()

    def cmp(self):
        l = self.cat()
        if self.isop(*CMP):
            op = CMP[self.t[self.i][1]]; self.i += 1
            return "(%s %s %s)" % (l, op, self.cat())
        return l

    def cat(self):
        l = self.add()
        while self.isop("&"):
            self.i += 1
            l = "cat(%s, %s)" % (l, self.add())
        return l

    def add(self):
        l = self.mul()
        while self.isop("+", "-"):
            op = self.t[self.i][1]; self.i += 1
            l = "(%s %s %s)" % (l, op, self.mul())
        return l

    def mul(self):
        l = self.unary()
        while True:
            if self.isop("*", "/"):
                op = self.t[self.i][1]; self.i += 1
                l = "(%s %s %s)" % (l, op, self.unary())
            elif self.isop("(") or (self.last_num and self.peek()[0] == "id" and self.peek()[1].lower() not in WORDS):
                l = "(%s * %s)" % (l, self.unary())
            else:
                return l

    def unary(self):
        if self.isop("-"):
            self.i += 1
            return "(-%s)" % self.unary()
        if self.isop("+"):
            self.i += 1
            return self.unary()
        return self.pow()

    def pow(self):
        b = self.post()
        if self.isop("^"):
            self.i += 1
            return "(%s ** %s)" % (b, self.unary())
        return b

    def post(self):
        v = self.prim()
        while True:
            if self.isop("["):
                self.i += 1
                start = self.i
                depth = 1
                while self.i < len(self.t) and depth:
                    if self.t[self.i][1] == "[": depth += 1
                    if self.t[self.i][1] == "]": depth -= 1
                    self.i += 1
                v = "ix(%s, %s)" % (v, ", ".join(self.g.args(self.t[start:self.i - 1])))
                self.last_num = False
            elif self.isop("!"):
                self.i += 1
                v = "call_builtin('factorial', %s)" % v
            else:
                return v

    def group(self):
        """Return token slice inside parentheses (cursor just after '(')."""
        start, depth = self.i, 1
        while self.i < len(self.t) and depth:
            if self.t[self.i][0] == "op":
                if self.t[self.i][1] in "([{": depth += 1
                if self.t[self.i][1] in ")]}": depth -= 1
            self.i += 1
        if depth:
            raise CompileError("Missing closing bracket")
        return self.t[start:self.i - 1]

    def prim(self):
        k, v = self.peek()
        self.last_num = False
        if k is None:
            raise CompileError("Expression ended unexpectedly")
        self.i += 1
        if k == "num":
            self.last_num = True
            return repr(float(v.replace("\u1d07", "e")) if re.search(r"[.\u1d07]", v) else int(v))
        if k == "str":
            return repr(v[1:-1].replace('""', '"'))
        if k == "op" and v == "(":
            return self.g.expr_toks(self.group())
        if k == "op" and v == "{":
            start, depth = self.i, 1
            while self.i < len(self.t) and depth:
                if self.t[self.i][1] in "{": depth += 1
                if self.t[self.i][1] in "}": depth -= 1
                self.i += 1
            return "TList([%s])" % ", ".join(self.g.args(self.t[start:self.i - 1]))
        if k == "id":
            name = v.lower()
            if name == "\u221a":
                if self.isop("("):
                    self.i += 1
                    return "call_builtin('sqrt', %s)" % self.g.expr_toks(self.group())
                return "call_builtin('sqrt', %s)" % self.pow()
            if name in ("pi", "\u03c0"):
                return "math.pi"
            if name == "true": return "True"
            if name == "false": return "False"
            if name == "undef": return "None"
            if self.isop("("):
                self.i += 1
                inner = self.group()
                if name == "seq":
                    parts, depth, cur = [], 0, []
                    for tk in inner:
                        if tk[0] == "op" and tk[1] in "([{": depth += 1
                        if tk[0] == "op" and tk[1] in ")]}": depth -= 1
                        if tk == ("op", ",") and depth == 0:
                            parts.append(cur); cur = []
                        else:
                            cur.append(tk)
                    parts.append(cur)
                    if len(parts) < 4 or not parts[1] or parts[1][0][0] != "id":
                        raise CompileError("seq(expr,var,low,high[,step])")
                    var = parts[1][0][1].lower()
                    self.g.alias[var] = "_sq"
                    try:
                        body = self.g.expr_toks(parts[0])
                    finally:
                        del self.g.alias[var]
                    rest = [self.g.expr_toks(p) for p in parts[2:]]
                    return "seq_(lambda _sq: %s, %s)" % (body, ", ".join(rest))
                args = ", ".join(self.g.args(inner))
                if name in self.g.known:
                    return "f_%s(%s)" % (re.sub(r"\W", "_", name), args)
                if name in BUILTIN_NAMES:
                    return "call_builtin(%r, %s)" % (name, args)
                self.i -= 0
                return "(%s * (%s))" % (self.g.varref(name), args)
            if name == "e" and not any("e" in sc["locals"] for sc in self.g.scopes) and self.isop("^"):
                return "math.e"
            return self.g.varref(name)
        raise CompileError("Unexpected '%s'" % v)


def _builtin_names():
    sys.path.insert(0, HERE)
    import tibasic_runtime
    return set(tibasic_runtime.B)


BUILTIN_NAMES = _builtin_names()


def translate(text, analysis, entry):
    g = Gen([d["name"] for d in analysis["defs"]])
    for n, s in statements(text):
        g.feed(n, s)
    if g.scopes:
        raise CompileError("A Program/Function block is not closed")
    ent = next(d for d in analysis["programs"] if d["name"] == entry)
    run = ", ".join('request(%r)' % (p + "?") for p in ent["params"])
    code = "\n".join(g.lines)
    code += (
        "\n\n\nif __name__ == '__main__':\n"
        "    try:\n"
        "        f_%s(%s)\n"
        "    except SystemExit:\n"
        "        pass\n"
        "    except TiError as _e:\n"
        "        print('Error:', _e)\n"
        "    except Exception as _e:\n"
        "        print('Error:', type(_e).__name__, _e)\n"
        "    input('\\nProgram finished. Press Enter to close...')\n"
    ) % (re.sub(r"\W", "_", entry), run)
    return code, g


# ------------------------------------------------------------------ pipeline
def ensure_dirs():
    for d in (INPUT_DIR, BUILD_DIR, OUTPUT_DIR):
        os.makedirs(d, exist_ok=True)


def compile_file(src, step, entry=None):
    """Run the full pipeline. `step(msg)` receives temporary explanations."""
    ensure_dirs()
    step("Reading source text...  (sources are kept inside Input\\)")
    src = os.path.abspath(src)
    if os.path.dirname(src).lower() != INPUT_DIR.lower():
        dst = os.path.join(INPUT_DIR, os.path.basename(src))
        shutil.copyfile(src, dst)
        step("Copied source into the compiler's Input folder so everything stays in this subfolder.")
        src = dst
    with open(src, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()

    step("Analysing the text: looking for Programs (Prgm) versus plain Functions (Func)...")
    a = analyse(text)
    step("Found %d program(s) and %d function(s)." % (len(a["programs"]), len(a["functions"])))
    body = re.sub(r'"(?:[^"]|"")*"', '""', normalise(text))
    pcwords = sorted({w for w in FILE_WORDS if re.search(r"(?<![\w.])%s(?![\w.])" % w, body, re.I)})
    if pcwords:
        step("PC FILE ACCESS detected (PC-only commands, not valid on a real calculator): " + ", ".join(pcwords))
        step("   The exe will read/write real files on this PC. If it is about to overwrite or delete "
             "an existing file it asks once for confirmation, then carries on.")
    for e in a["errors"]:
        step("Structure warning - " + e)
    if not a["programs"]:
        raise NoProgram("No Program found - only functions (or nothing). A Program "
                        "'Define name()=Prgm ... EndPrgm' is required, so nothing was compiled.")
    if a["errors"]:
        raise CompileError("Unbalanced Define/EndPrgm/EndFunc blocks - fix the source first.")
    tops = [d for d in a["programs"] if not d["nested"]] or a["programs"]
    if entry is None:
        entry = tops[0]["name"]
    if entry not in [d["name"] for d in a["programs"]]:
        raise CompileError("Entry program '%s' not found" % entry)
    step("Program '%s' is the entry point. Functions defined inside it will be compiled with it." % entry)

    step("Translating TI-Basic statements to executable code (parsing blocks, expressions, lists)...")
    code, g = translate(text, a, entry)
    for w in g.warnings:
        step("Note - " + w)

    step("Converting calculator input/output to the PC console form factor...")
    for key, desc in IO_MAP:
        if key in g.used:
            step("   " + desc)
    step("   (Programs with no Disp/Request still get a 'Press Enter to close' pause so the window stays open.)")

    with open(os.path.join(HERE, "tibasic_runtime.py"), "r", encoding="utf-8") as f:
        runtime = f.read()
    full = "# Generated by tibasic_compiler.py from %s\n%s\n\n# ---- compiled program ----\n%s\n" % (
        os.path.basename(src), runtime, code)
    name = re.sub(r"\W", "_", entry)
    os.makedirs(BUILD_DIR, exist_ok=True)
    py_path = os.path.join(BUILD_DIR, name + ".py")
    with open(py_path, "w", encoding="utf-8") as f:
        f.write(full)
    try:
        compile(full, py_path, "exec")
    except SyntaxError as e:
        raise CompileError("Internal translation error at generated line %s: %s" % (e.lineno, e.msg))
    step("Generated and checked intermediate code: Build\\%s.py" % name)

    step("Checking for the PyInstaller packager...")
    if subprocess.run([sys.executable, "-c", "import PyInstaller"], capture_output=True).returncode != 0:
        step("Installing PyInstaller (one-time)...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], capture_output=True, text=True)
        if r.returncode:
            raise CompileError("Could not install PyInstaller:\n" + r.stdout[-800:] + r.stderr[-800:])

    step("Packaging into a standalone .exe (this takes a minute)...")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
           "--name", name, "--distpath", OUTPUT_DIR, "--workpath", os.path.join(BUILD_DIR, "work"),
           "--specpath", BUILD_DIR, py_path]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", cwd=BUILD_DIR)
    tail, last = [], 0
    for line in p.stdout:
        tail.append(line.rstrip())
        if time.time() - last > 4 and "INFO" in line:
            step("   packager: " + line.split("INFO:")[-1].strip()[:90])
            last = time.time()
    if p.wait():
        raise CompileError("Packaging failed:\n" + "\n".join(tail[-15:]))
    exe = os.path.join(OUTPUT_DIR, name + ".exe")
    if not os.path.isfile(exe):
        raise CompileError("Packager finished but the exe was not found.")
    step("Finished! Executable ready: " + exe)
    return exe


# ----------------------------------------------------------------------- UI
def pick_default_source():
    ensure_dirs()
    fs = sorted(f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".txt"))
    return os.path.join(INPUT_DIR, fs[0]) if fs else ""


def run_console(src, entry, pause=True):
    print(README_NOTE.replace("Press Continue to proceed.", ""))
    input("[ Continue ]  Press Enter to proceed...")
    try:
        exe = compile_file(src, lambda m: (print(" >", m), time.sleep(0.4)), entry)
        return 0
    except CompileError as e:
        print("\nSTOPPED:", e)
        return 1


def run_gui(src, entry):
    import tkinter as tk
    from tkinter import filedialog, ttk, scrolledtext

    root = tk.Tk()
    root.title("TI-Basic to EXE Compiler")
    root.geometry("760x620")
    state = {"src": src}

    note = scrolledtext.ScrolledText(root, wrap="word", height=22, font=("Consolas", 10))
    note.insert("1.0", README_NOTE)
    note.configure(state="disabled")
    note.pack(fill="both", expand=True, padx=10, pady=(10, 4))

    row = ttk.Frame(root); row.pack(fill="x", padx=10)
    srclbl = ttk.Label(row, text="Source: " + (src or "(none chosen)"))
    srclbl.pack(side="left")

    def browse():
        p = filedialog.askopenfilename(initialdir=INPUT_DIR, title="Choose TI-Basic text file",
                                       filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if p:
            state["src"] = p
            srclbl.config(text="Source: " + p)
    browse_btn = ttk.Button(row, text="Choose source...", command=browse)
    browse_btn.pack(side="right")

    status = ttk.Label(root, text="", font=("Segoe UI", 10, "bold"), wraplength=720)
    log = scrolledtext.ScrolledText(root, wrap="word", height=10, font=("Consolas", 9), state="disabled")
    btn = ttk.Button(root, text="Continue")
    btn.pack(pady=8)

    def ui(fn):
        root.after(0, fn)

    def step(msg):
        def f():
            status.config(text=msg)
            log.configure(state="normal"); log.insert("end", msg + "\n"); log.see("end"); log.configure(state="disabled")
        ui(f)
        time.sleep(0.7)

    def work():
        try:
            exe = compile_file(state["src"], step, entry)
            ui(lambda: status.config(text="DONE: " + exe, foreground="green"))
            ui(lambda: btn.config(text="Close", state="normal", command=root.destroy))
        except CompileError as e:
            step("STOPPED: " + str(e))
            ui(lambda: status.config(foreground="red"))
            ui(lambda: btn.config(text="Close", state="normal", command=root.destroy))
        except Exception as e:
            step("UNEXPECTED ERROR: %s: %s" % (type(e).__name__, e))
            ui(lambda: btn.config(text="Close", state="normal", command=root.destroy))

    def go():
        if not state["src"]:
            browse()
            if not state["src"]:
                return
        btn.config(state="disabled")
        browse_btn.config(state="disabled")
        note.pack_forget()
        status.pack(fill="x", padx=10, pady=4, before=btn)
        log.pack(fill="both", expand=True, padx=10, before=btn)
        threading.Thread(target=work, daemon=True).start()

    btn.config(command=go)
    root.mainloop()
    return 0


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    entry = None
    if "--entry" in argv:
        entry = argv[argv.index("--entry") + 1].lower()
        args = [a for a in args if a.lower() != entry]
    src = args[0] if args else pick_default_source()
    if "--console" in argv or not src and False:
        return run_console(src, entry)
    try:
        import tkinter  # noqa
    except ImportError:
        return run_console(src, entry)
    return run_gui(src, entry)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
