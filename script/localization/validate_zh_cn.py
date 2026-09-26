"""Validates the generated zh-CN table: every Rust string literal is unescaped
and compared against the source catalog."""

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
            assert token[index + 1] == "{", token
            end = token.index("}", index)
            out.append(chr(int(token[index + 2 : end], 16)))
            index = end + 1
        else:
            raise AssertionError(f"unknown escape \\{escape} in {token!r}")
    return "".join(out)


def literals(path: str):
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    for line in source.splitlines():
        if not line.startswith("    "):
            continue
        if line.startswith("    ("):
            for match in LITERAL.finditer(line):
                yield unescape(match.group(1))
        elif line.startswith("    (&["):
            for match in LITERAL.finditer(line):
                yield unescape(match.group(1))


def main() -> None:
    generated = list(literals(sys.argv[1]))
    with open(sys.argv[2], encoding="utf-8") as handle:
        translations = json.load(handle)

    missing = [value for value in generated if value not in translations and value not in translations.values()]
    print(f"{len(generated)} literals, {len(missing)} not found in the catalog")
    for value in missing[:10]:
        print("  ", repr(value))

    with open(sys.argv[3], encoding="utf-8") as handle:
        manifest = json.load(handle)
    verbatim = {
        source
        for source, translation in translations.items()
        if "{" not in source
        and translation.strip()
        and translation != source
        and manifest.get(source, {}).get("occurrences")
        and {occurrence.get("kind") for occurrence in manifest[source]["occurrences"]}
        != {"rust_doc_comment"}
    }
    print(f"expected verbatim entries: {len(verbatim)}")


if __name__ == "__main__":
    main()
