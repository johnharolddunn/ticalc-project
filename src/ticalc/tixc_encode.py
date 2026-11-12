#!/usr/bin/env python3
"""Minimal pure Python encoder for TIXC0100 XML token streams."""

from __future__ import annotations

import re

from .tixc_decode import decode_tixc


class TixcEncodeError(RuntimeError):
    pass


XML_DECL_RE = re.compile(br'^<\?xml\s+version="([^"]+)"\s+encoding="UTF-8"\s+\?>')
_ETA_TABLE = b" etaionsrhAlcduFmfpgybwvkxqjz,.'"
_DIGIT_TABLE = b"0123456789AN,.EFx; (){}[]^+-/*PB"
# Nibble grammar learned from the decoder and checked against a calculator-made file.
# ETA mode: nibble 10 ('A') terminates, nibble 15 ('F') escapes to table[16 + next nibble].
# DIGIT mode: nibble 15 ('F') terminates, nibble 10 ('A') escapes to table[16 + next nibble].
_ETA_CODES = {bytes([c]): i for i, c in enumerate(_ETA_TABLE) if c not in (ord("A"), ord("F"))}
_DIGIT_CODES = {bytes([c]): i for i, c in enumerate(_DIGIT_TABLE) if c not in (ord("A"), ord("F"), ord("N"), ord("E"), ord("P"), ord("B"))}
_DIGIT_CODES[b"\xe2\x88\x92"] = _DIGIT_TABLE.index(b"N")
_DIGIT_CODES[b"\xef\x80\x80"] = _DIGIT_TABLE.index(b"E")
_DIGIT_CODES[b"))"] = _DIGIT_TABLE.index(b"P")
_BRACKET_PAIR = b"]["
_DIGIT_CODES_PAIR = {_BRACKET_PAIR: _DIGIT_TABLE.index(b"B")}
_MIN_SAVING = 1


def _encode_utf8_sequence(seq: bytes) -> bytes:
    if len(seq) == 2:
        a, b = seq
        if not (0xC0 <= a <= 0xDF and 0x80 <= b <= 0xBF):
            raise TixcEncodeError(f"invalid two-byte UTF-8 sequence: {seq!r}")
        control = (a & 0x1C) >> 2
        packed = ((a & 0x03) << 6) | (b & 0x3F)
        return bytes([control, packed])

    if len(seq) == 3:
        a, b, c = seq
        if not (0xE0 <= a <= 0xEF and 0x80 <= b <= 0xBF and 0x80 <= c <= 0xBF):
            raise TixcEncodeError(f"invalid three-byte UTF-8 sequence: {seq!r}")
        x = ((a & 0x0F) << 4) | ((b & 0x3C) >> 2)
        y = ((b & 0x03) << 6) | (c & 0x3F)
        return bytes([0x80, x, y])

    if len(seq) == 4:
        a, b, c, d = seq
        if not (0xF0 <= a <= 0xF7 and 0x80 <= b <= 0xBF and 0x80 <= c <= 0xBF and 0x80 <= d <= 0xBF):
            raise TixcEncodeError(f"invalid four-byte UTF-8 sequence: {seq!r}")
        x = ((a & 0x07) << 2) | ((b & 0x30) >> 4)
        y = ((b & 0x0F) << 4) | ((c & 0x3C) >> 2)
        z = ((c & 0x03) << 6) | (d & 0x3F)
        return bytes([0x08, x, y, z])

    raise TixcEncodeError(f"unsupported UTF-8 sequence length: {len(seq)}")


def _text_units(data: bytes) -> list[bytes]:
    units: list[bytes] = []
    i = 0
    while i < len(data):
        b = data[i]
        if b < 0x80:
            size = 1
        elif 0xC0 <= b <= 0xDF:
            size = 2
        elif 0xE0 <= b <= 0xEF:
            size = 3
        elif 0xF0 <= b <= 0xF7:
            size = 4
        else:
            raise TixcEncodeError(f"invalid UTF-8 lead byte 0x{b:02x}")
        seq = data[i : i + size]
        if len(seq) != size:
            raise TixcEncodeError("truncated UTF-8 sequence")
        if size == 1 and data[i : i + 2] == b"))":
            seq = data[i : i + 2]
            size = 2
        units.append(seq)
        i += size
    return units


def _literal_unit(seq: bytes) -> bytes:
    if len(seq) == 1:
        b = seq[0]
        if b in (0x09, 0x0A, 0x0D) or 0x20 <= b <= 0x7E:
            return seq
        raise TixcEncodeError(f"unsupported XML text control byte 0x{b:02x}")
    if seq == b"))":
        return seq
    return _encode_utf8_sequence(seq)


def _nibbles_for(codes: dict[bytes, int], seq: bytes, escape: int) -> list[int]:
    idx = codes[seq] if seq in codes else _DIGIT_CODES_PAIR[seq]
    return [idx] if idx < 16 else [escape, idx - 16]


def _pack_run(prefix: int, terminator: int, nibbles: list[int]) -> bytes:
    stream = nibbles + [terminator]
    first, rest = stream[0], stream[1:]
    out = bytearray([prefix | first])
    if len(rest) % 2:
        rest.append(terminator)
    for k in range(0, len(rest), 2):
        out.append((rest[k] << 4) | rest[k + 1])
    return bytes(out)


def _encode_text(data: bytes) -> bytes:
    """Greedy encoder: take the maximal table run at each position when it is strictly shorter than literals."""
    units = _text_units(data)
    n = len(units)
    out = bytearray()
    i = 0
    modes = (
        (_ETA_CODES, 0xA0, 0x0A, 0x0F),
        (_DIGIT_CODES, 0xF0, 0x0F, 0x0A),
    )
    while i < n:
        pick = None
        # The first character selects the table: anything the ETA table carries opens an ETA run,
        # otherwise the DIGIT table is tried. The whole maximal run is taken if it saves bytes,
        # else it stays literal.
        if units[i] not in _ETA_CODES and units[i] in _DIGIT_CODES:
            codes, prefix, term, esc = modes[1]
        else:
            codes, prefix, term, esc = modes[0]
        j = i
        nibbles: list[int] = []
        while j < n and units[j] in codes:
            j += 1
        for k in range(i, j):
            # "][" has its own DIGIT code, but the calculator only uses it as the tail of a run.
            if codes is _DIGIT_CODES and units[k] == b"[" and k > i and units[k - 1] == b"]" and k == j - 1:
                nibbles = nibbles[: -len(_nibbles_for(codes, b"]", esc))]
                nibbles += _nibbles_for(codes, _BRACKET_PAIR, esc)
            else:
                nibbles += _nibbles_for(codes, units[k], esc)
        if j > i:
            run_len = (len(nibbles) + 2 + 1) // 2
            lit_len = sum(len(_literal_unit(u)) for u in units[i:j])
            if lit_len - run_len >= _MIN_SAVING:
                out += _pack_run(prefix, term, nibbles)
            else:
                for u in units[i:j]:
                    out += _literal_unit(u)
            i = j
        else:
            out += _literal_unit(units[i])
            i += 1
    return bytes(out)


def _name_end(data: bytes, pos: int) -> int:
    while pos < len(data) and data[pos] not in b" \t\r\n/=>":
        pos += 1
    return pos


def _skip_ws(data: bytes, pos: int) -> int:
    while pos < len(data) and data[pos] in b" \t\r\n":
        pos += 1
    return pos


def encode_tixc(xml: bytes) -> bytes:
    """Encode readable XML bytes as a TIXC0100 stream.

    The encoder intentionally emits a simple stream: literal first-use tag and
    attribute names, dictionary references for repeats and close tags, and text
    bytes encoded only where TIXC requires it.
    """
    match = XML_DECL_RE.match(xml)
    if not match:
        raise TixcEncodeError("XML must start with a UTF-8 declaration")
    version = match.group(1)
    body = xml[match.end() :]

    out = bytearray(b"TIXC0100-" + version + b"?>")
    tag_dict: list[bytes] = []
    tag_index: dict[bytes, int] = {}

    i = 0
    space_token_next = False
    while i < len(body):
        if body[i] == ord("<") and not body.startswith(b"<![CDATA[", i):
            space_token_next = False
        if body.startswith(b"<![CDATA[", i):
            end = body.find(b"]]>", i + 9)
            if end < 0:
                raise TixcEncodeError("unterminated CDATA section")
            out += body[i : end + 3]
            i = end + 3
            continue

        if body[i] != ord("<"):
            next_tag = body.find(b"<", i)
            if next_tag < 0:
                next_tag = len(body)
            text = body[i:next_tag]
            if space_token_next and text.startswith(b" "):
                out += _pack_run(0xA0, 0x0A, [0])
                text = text[1:]
            space_token_next = False
            out += _encode_text(text)
            i = next_tag
            continue

        if body.startswith(b"</", i):
            end = body.find(b">", i + 2)
            if end < 0:
                raise TixcEncodeError("unterminated close tag")
            name = body[i + 2 : end]
            idx = tag_index.get(name)
            if idx is None:
                raise TixcEncodeError(f"close tag has no dictionary entry: {name!r}")
            out += bytes([0x0E, idx])
            i = end + 1
            continue

        if body.startswith(b"<?", i):
            raise TixcEncodeError("processing instructions are only supported in the XML declaration")
        if body.startswith(b"<!", i):
            raise TixcEncodeError("only CDATA markup is supported")

        pos = i + 1
        name_end = _name_end(body, pos)
        if name_end == pos:
            raise TixcEncodeError(f"empty tag name at offset {i}")
        name = body[pos:name_end]
        idx = tag_index.get(name)
        used_tag_ref = idx is not None
        if (
            used_tag_ref
            and body[name_end : name_end + 1] == b">"
            and body[name_end + 1 : name_end + 2] in (b"\t", b"\r", b"\n")
        ):
            # After a tag reference, the decoder treats a leading space as an
            # attribute separator, so a leading space is sent as an ETA token (below).
            # Other leading whitespace stays unambiguous only with the literal tag name.
            used_tag_ref = False
        if idx is None:
            if len(tag_dict) >= 256:
                raise TixcEncodeError("tag dictionary exhausted")
            idx = len(tag_dict)
            tag_dict.append(name)
            tag_index[name] = idx
            out += b"<" + name
        elif not used_tag_ref:
            if len(tag_dict) >= 256:
                raise TixcEncodeError("tag dictionary exhausted")
            idx = len(tag_dict)
            tag_dict.append(name)
            tag_index[name] = idx
            out += b"<" + name
        else:
            out += bytes([0x0C, idx])

        pos = name_end
        has_attrs = False
        while True:
            pos = _skip_ws(body, pos)
            if pos >= len(body):
                raise TixcEncodeError("unterminated start tag")
            if body.startswith(b"/>", pos):
                out += b"/>"
                i = pos + 2
                break
            if body[pos] == ord(">"):
                # A tag dictionary start reference has an implicit '>' when it
                # is followed directly by content. If attributes were emitted,
                # the decoder is in the "after attribute value" state and needs
                # an explicit '>' to enter content state.
                if not used_tag_ref or has_attrs:
                    out.append(ord(">"))
                else:
                    space_token_next = True
                i = pos + 1
                break

            attr_start = pos
            attr_end = _name_end(body, pos)
            attr = body[attr_start:attr_end]
            pos = _skip_ws(body, attr_end)
            if pos >= len(body) or body[pos] != ord("="):
                raise TixcEncodeError(f"expected '=' after attribute {attr!r}")
            pos = _skip_ws(body, pos + 1)
            if pos >= len(body) or body[pos] != ord('"'):
                raise TixcEncodeError(f"expected double quote for attribute {attr!r}")
            value_start = pos + 1
            value_end = body.find(b'"', value_start)
            if value_end < 0:
                raise TixcEncodeError(f"unterminated value for attribute {attr!r}")
            value = body[value_start:value_end]
            has_attrs = True

            out += b" " + attr + b'="' + _encode_text(value) + b'"'
            pos = value_end + 1

    encoded = bytes(out)
    decoded = decode_tixc(encoded)
    if decoded != xml:
        first = next((i for i, (a, b) in enumerate(zip(decoded, xml)) if a != b), min(len(decoded), len(xml)))
        got = decoded[max(0, first - 80) : first + 160]
        want = xml[max(0, first - 80) : first + 160]
        raise TixcEncodeError(
            "internal TIXC roundtrip check failed at byte "
            f"{first}: got {got!r}; expected {want!r}"
        )
    return encoded
