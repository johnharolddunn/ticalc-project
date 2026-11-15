# Runtime support prepended to every compiled TI-Basic program (PC console form factor).
import math, sys, os, time, random


class TiError(Exception):
    pass


class Vars(dict):
    def __missing__(self, k):
        raise TiError("Variable '%s' is not defined" % k)


G = Vars()


def _el(a, b, f):
    if isinstance(a, list) and isinstance(b, list):
        return TList(f(x, y) for x, y in zip(a, b))
    if isinstance(a, list):
        return TList(f(x, b) for x in a)
    if isinstance(b, list):
        return TList(f(a, y) for y in b)
    return f(a, b)


class TList(list):
    def __add__(s, o): return _el(s, o, lambda x, y: x + y)
    def __radd__(s, o): return _el(o, s, lambda x, y: x + y)
    def __sub__(s, o): return _el(s, o, lambda x, y: x - y)
    def __rsub__(s, o): return _el(o, s, lambda x, y: x - y)
    def __mul__(s, o): return _el(s, o, lambda x, y: x * y)
    def __rmul__(s, o): return _el(o, s, lambda x, y: x * y)
    def __truediv__(s, o): return _el(s, o, lambda x, y: x / y)
    def __rtruediv__(s, o): return _el(o, s, lambda x, y: x / y)
    def __pow__(s, o): return _el(s, o, lambda x, y: x ** y)
    def __neg__(s): return TList(-x for x in s)


def fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return "%.14g" % v
    if isinstance(v, list):
        return "{" + ",".join(fmt(x) for x in v) + "}"
    return str(v)


def disp(*a):
    for v in a:
        print(fmt(v))


def cat(a, b):
    return fmt(a) + fmt(b)


def cp(v):
    if isinstance(v, list):
        return TList(cp(x) for x in v)
    return v


def ix(a, *i):
    try:
        for k in i:
            if int(k) < 1:
                raise IndexError
            a = a[int(k) - 1]
        return a
    except IndexError:
        raise TiError("Invalid list or matrix index")


def setix(a, v, *i):
    for k in i[:-1]:
        a = a[int(k) - 1]
    a[int(i[-1]) - 1] = v


def frange(lo, hi, step=1):
    if step == 0:
        raise TiError("Step cannot be zero")
    x = lo
    while (step > 0 and x <= hi) or (step < 0 and x >= hi):
        yield x
        x += step


def seq_(f, lo, hi, step=1):
    return TList(f(x) for x in frange(lo, hi, step))


def _num(s):
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except ValueError:
        return s


def request(prompt):
    return _num(input(prompt + " "))


def request_str(prompt):
    return input(prompt + " ")


def pause(*a):
    for v in a:
        print(fmt(v))
    input("Press Enter to continue...")


def delay(ms):
    time.sleep(ms / 1000.0)


def clrio():
    os.system("cls" if os.name == "nt" else "clear")


def getkey():
    if os.name == "nt":
        import msvcrt
        return ord(msvcrt.getwch()) if msvcrt.kbhit() else 0
    return 0


# ---- PC-only file access (extension commands, not available on a calculator)
_OVERWRITE_OK = [False]


def _confirm_overwrite(path, what):
    """One-time warning; after a Yes the program may write/delete freely."""
    if _OVERWRITE_OK[0]:
        return
    print()
    print("WARNING: this program is about to %s existing data:" % what)
    print("   " + path)
    print("You are only asked this ONCE. If you continue, later file changes")
    print("made by this program will not ask again.")
    if input("Continue? (Y/N) ").strip().lower() not in ("y", "yes"):
        raise TiError("Cancelled by user - existing file left untouched")
    _OVERWRITE_OK[0] = True


def _lines(v):
    return [fmt(x) for x in v] if isinstance(v, list) else fmt(v).split("\n")


def readlines(path):
    try:
        with open(fmt(path), "r", encoding="utf-8-sig", errors="replace") as f:
            return TList(f.read().splitlines())
    except OSError as e:
        raise TiError("Cannot read file: %s" % e)


def readnums(path):
    out = TList()
    for ln in readlines(path):
        for tok in ln.replace(",", " ").replace(";", " ").replace("\t", " ").split():
            v = _num(tok)
            if not isinstance(v, str):
                out.append(v)
    return out


def writelines(path, data):
    path = fmt(path)
    if os.path.exists(path):
        _confirm_overwrite(path, "overwrite")
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(_lines(data)) + "\n")
    except OSError as e:
        raise TiError("Cannot write file: %s" % e)


def appendlines(path, data):
    try:
        with open(fmt(path), "a", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(_lines(data)) + "\n")
    except OSError as e:
        raise TiError("Cannot write file: %s" % e)


def delfile(path):
    path = fmt(path)
    if os.path.isfile(path):
        _confirm_overwrite(path, "delete")
        os.remove(path)


def fileexists(path):
    return os.path.exists(fmt(path))


def filelist(folder="."):
    try:
        return TList(sorted(os.listdir(fmt(folder))))
    except OSError as e:
        raise TiError("Cannot list folder: %s" % e)


def _dialog(kind):
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return (filedialog.asksaveasfilename if kind == "save" else filedialog.askopenfilename)() or ""
    finally:
        root.destroy()


def arg(n=1):
    a = sys.argv[1:]
    return a[int(n) - 1] if 1 <= int(n) <= len(a) else ""


def _split(s, sep=","):
    return TList(fmt(s).split(fmt(sep)))


def _mid(s, a, n=None):
    s = fmt(s)
    a = int(a) - 1
    return s[a:] if n is None else s[a:a + int(n)]


def _map(f):
    return lambda x: TList(f(y) for y in x) if isinstance(x, list) else f(x)


def _round(x, n=0):
    return TList(_round(y, n) for y in x) if isinstance(x, list) else round(x, int(n))


def _log(x, b=None):
    return math.log(x) if b is None else math.log(x, b)


def _randint(lo=None, hi=None, n=None):
    if lo is None:
        return random.random()
    if n is None:
        return random.randint(int(lo), int(hi))
    return TList(random.randint(int(lo), int(hi)) for _ in range(int(n)))


def _prod(l):
    r = 1
    for x in l:
        r *= x
    return r


def _cumsum(l):
    r, t = TList(), 0
    for x in l:
        t += x
        r.append(t)
    return r


def _instr(s, t, st=1):
    return fmt(s).find(fmt(t), int(st) - 1) + 1


def _expr(s):
    r = _num(s)
    if isinstance(r, str):
        raise TiError("Cannot convert string to expression")
    return r


B = {
    "abs": _map(abs), "sqrt": _map(math.sqrt), "sin": _map(math.sin), "cos": _map(math.cos),
    "tan": _map(math.tan), "asin": _map(math.asin), "acos": _map(math.acos),
    "atan": _map(math.atan), "sinh": _map(math.sinh), "cosh": _map(math.cosh),
    "tanh": _map(math.tanh), "ln": _map(math.log), "log": _log, "exp": _map(math.exp),
    "floor": _map(math.floor), "ceiling": _map(math.ceil), "int": _map(math.floor),
    "round": _round, "ipart": _map(math.trunc), "fpart": _map(lambda x: x - math.trunc(x)),
    "sign": _map(lambda x: (x > 0) - (x < 0)), "mod": lambda a, b: a % b,
    "gcd": math.gcd, "lcm": math.lcm,
    "min": lambda *a: min(a[0]) if len(a) == 1 else min(a),
    "max": lambda *a: max(a[0]) if len(a) == 1 else max(a),
    "sum": sum, "product": _prod, "cumsum": _cumsum, "dim": len,
    "randint": _randint, "rand": _randint, "factorial": math.factorial,
    "left": lambda s, n=1: fmt(s)[:int(n)],
    "right": lambda s, n=1: fmt(s)[len(fmt(s)) - int(n):],
    "mid": _mid, "string": fmt, "expr": _expr, "upper": lambda s: fmt(s).upper(),
    "lower": lambda s: fmt(s).lower(), "instring": _instr, "char": chr, "ord": lambda s: ord(s[0]),
    "readlines": readlines, "readnums": readnums, "writelines": writelines,
    "appendlines": appendlines, "delfile": delfile, "fileexists": fileexists,
    "filelist": filelist, "pickfile": lambda: _dialog("open"), "picksave": lambda: _dialog("save"),
    "arg": arg, "argcount": lambda: len(sys.argv) - 1, "split": _split,
    "getkey": getkey, "iseven": lambda x: x % 2 == 0,
    "sortd": lambda l: TList(sorted(l, reverse=True)), "sorta": lambda l: TList(sorted(l)),
}


def call_builtin(name, *a):
    return B[name](*a)
