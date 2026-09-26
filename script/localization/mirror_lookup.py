"""Python mirror of the Rust lookup in crates/gpui/src/localization.rs.

Used to check the matching rules against the real catalog before the Rust
implementation is compiled."""

import json
import re
import sys

LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')


def unescape(token: str) -> str:
    out = []
    index = 0
    while index < len(token):
        character = token[index]
        if character != "\\":
            out.append(character)
            index += 1
            continue
        index += 1
        escape = token[index]
        if escape == "n":
            out.append("\n")
            index += 1
        elif escape == "r":
            out.append("\r")
            index += 1
        elif escape == "t":
            out.append("\t")
            index += 1
        elif escape == '"':
            out.append('"')
            index += 1
        elif escape == "\\":
            out.append("\\")
            index += 1
        elif escape == "u":
            end = token.index("}", index)
            out.append(chr(int(token[index + 2 : end], 16)))
            index = end + 1
        else:
            raise AssertionError(escape)
    return "".join(out)


def load_tables(path):
    exact = {}
    anchored = []
    leading = []
    section = None
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("pub(super) static TRANSLATIONS"):
                section = "exact"
                continue
            if line.startswith("pub(super) static PATTERNS"):
                section = "anchored"
                continue
            if line.startswith("pub(super) static LEADING_PATTERNS"):
                section = "leading"
                continue
            if line.startswith("    (&["):
                values = [unescape(m.group(1)) for m in LITERAL.finditer(line)]
                segments = values[:-1]
                translation = values[-1]
                if section == "anchored":
                    anchored.append((segments, translation))
                else:
                    leading.append((segments, translation))
            elif line.startswith("    ("):
                values = [unescape(m.group(1)) for m in LITERAL.finditer(line)]
                if section == "exact":
                    exact[values[0]] = values[1]
    return exact, anchored, leading


def match_segments(text, segments):
    count = len(segments) - 1
    if count <= 0:
        return None
    if not text.startswith(segments[0]):
        return None
    remaining = text[len(segments[0]) :]
    captures = []
    for index, segment in enumerate(segments[1:]):
        is_last = index == count - 1
        if is_last:
            if segment == "":
                captured = remaining
            elif remaining.endswith(segment):
                captured = remaining[: len(remaining) - len(segment)]
            else:
                return None
            if captured == "":
                return None
            captures.append(captured)
            remaining = ""
        elif segment == "":
            return None
        else:
            position = remaining.find(segment)
            if position <= 0:
                return None
            captures.append(remaining[:position])
            remaining = remaining[position + len(segment) :]
    return captures


def substitute(translation, captures):
    out = []
    index = 0
    used = 0
    while True:
        start = translation.find("{", index)
        if start < 0:
            break
        end = translation.find("}", start)
        if end < 0:
            break
        out.append(translation[index:start])
        if used >= len(captures):
            return None
        out.append(captures[used])
        used += 1
        index = end + 1
    if used == 0:
        return None
    out.append(translation[index:])
    return "".join(out)


class Dictionary:
    def __init__(self, path):
        self.exact, self.anchored, self.leading = load_tables(path)
        self.buckets = {}
        for entry in self.anchored:
            self.buckets.setdefault(entry[0][0][0], []).append(entry)

    def lookup(self, text):
        found = self.exact.get(text)
        if found is not None:
            return found
        if not text:
            return None
        bucket = self.buckets.get(text[0])
        if bucket:
            for segments, translation in bucket:
                captures = match_segments(text, segments)
                if captures is not None:
                    result = substitute(translation, captures)
                    if result is not None:
                        return result
        for segments, translation in self.leading:
            captures = match_segments(text, segments)
            if captures is not None:
                result = substitute(translation, captures)
                if result is not None:
                    return result
        return None


def main():
    dictionary = Dictionary(sys.argv[1])
    print(len(dictionary.exact), len(dictionary.anchored), len(dictionary.leading))

    checks = [
        ("Settings", "设置"),
        ("Open File", "打开文件"),
        ("Downloading Zed update…", None),
        ("Downloading extensions…", None),
        ("Failed to run rust-analyzer. Click to show error.", None),
        ("A server named \"docs\" already exists.", None),
        ("main.rs", None),
        ("src/project_panel.rs", None),
        ("fn main() { println!(\"hi\"); }", None),
        ("", None),
        ("{}", None),
        ("  ", None),
        ("Zed", None),
        ("Move", None),
        ("move", None),
        ("Project Panel", None),
    ]
    for text, expected in checks:
        result = dictionary.lookup(text)
        mark = ""
        if expected is not None:
            mark = " OK" if result == expected else f" MISMATCH (expected {expected!r})"
        print(f"{text!r} -> {result!r}{mark}")

    # Every anchored pattern must round-trip: render the pattern with sample
    # arguments and check that the lookup reproduces the translation.
    failures = 0
    for segments, translation in dictionary.anchored + dictionary.leading:
        rendered = segments[0]
        for index, segment in enumerate(segments[1:]):
            rendered += f"ARG{index}" + segment
        result = dictionary.lookup(rendered)
        if result is None:
            failures += 1
            if failures < 8:
                print("  round-trip miss:", repr(rendered))
        else:
            for index in range(len(segments) - 1):
                if f"ARG{index}" not in result and "ARG" not in translation:
                    failures += 1
                    print("  dropped capture:", repr(rendered), "->", repr(result))
                    break
    print("pattern round-trip failures:", failures)


if __name__ == "__main__":
    main()
