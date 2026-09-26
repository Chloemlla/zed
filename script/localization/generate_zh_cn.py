"""Generates the Simplified Chinese (zh-CN) lookup tables used by
`crates/gpui/src/localization.rs`.

Inputs are the translation catalog and the string manifest published by the
community localization project `LI-NA/zed-i18n` (AGPL-3.0), which tracks the
upstream Zed source tree:

    translations/zh-CN.json    English source string -> Simplified Chinese
    manifest/ui-strings.json   where each string occurs, and whether the
                               extraction pipeline accepted it as UI text

Only strings that the manifest marks as user facing are kept. Strings that
appear exclusively in Rust doc comments are kept in the verbatim table, where
they cost nothing, but never become message templates, because their
placeholders are prose rather than arguments.

Usage:

    python script/localization/generate_zh_cn.py <translations/zh-CN.json> \
        <manifest/ui-strings.json> <output rust file> [actions json]

The optional `actions json` defaults to `script/localization/actions_zh_cn.json`,
which holds the names of Zed's actions (see `actions_zh_cn.py`). Catalogued
strings win over action names when both cover the same text.
"""

import json
import os
import re
import sys

PLACEHOLDER = re.compile(r"\{[^{}]*\}")

# A message template is only worth matching when literal text surrounds a
# placeholder on both sides. Templates that are a single short word followed by
# an argument ("Open {}") also match unrelated strings that happen to start
# with that word, and translating those is worse than leaving them in English.
MINIMUM_SEGMENTS = 2

# Strings that are far more likely to be user content (file names, symbol
# names) than interface text. They are short, generic and show up verbatim in
# the project panel, so translating them would rename things that the user
# owns.
SKIPPED_STRINGS = frozenset(
    {
        "move",
        "none",
        "item",
        "year",
        "tab",
    }
)


def rust_string(value: str) -> str:
    """Escapes `value` as a Rust string literal."""
    out = ['"']
    for character in value:
        if character == '"':
            out.append('\\"')
        elif character == "\\":
            out.append("\\\\")
        elif character == "\n":
            out.append("\\n")
        elif character == "\r":
            out.append("\\r")
        elif character == "\t":
            out.append("\\t")
        elif ord(character) < 0x20 or ord(character) == 0x7F:
            out.append("\\u{%x}" % ord(character))
        else:
            out.append(character)
    out.append('"')
    return "".join(out)


def split_segments(source: str) -> list:
    """Splits a format string into its literal segments."""
    segments = []
    index = 0
    for match in PLACEHOLDER.finditer(source):
        segments.append(source[index : match.start()])
        index = match.end()
    segments.append(source[index:])
    return segments


def load(translations_path: str, manifest_path: str) -> dict:
    """Returns the translations worth shipping, keyed by source string."""
    with open(translations_path, encoding="utf-8") as handle:
        translations = json.load(handle)
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)

    kept = {}
    for source, translation in translations.items():
        entry = manifest.get(source)
        if not isinstance(entry, dict):
            continue
        if not translation.strip() or translation == source:
            continue
        if source in SKIPPED_STRINGS:
            continue
        kept[source] = (translation, entry.get("occurrences", []))
    return kept


def load_actions(path: str) -> dict:
    """Loads action names, if the file has been generated."""
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)

    kept = load(sys.argv[1], sys.argv[2])
    actions = load_actions(
        sys.argv[4]
        if len(sys.argv) > 4
        else os.path.join(os.path.dirname(os.path.abspath(__file__)), "actions_zh_cn.json")
    )

    exact = []
    patterns = []
    skipped_templates = 0
    for source, translation in sorted(actions.items()):
        if source not in kept:
            exact.append((source, translation))

    for source, (translation, occurrences) in sorted(kept.items()):
        if "{" not in source:
            exact.append((source, translation))
            continue

        # Doc comments describe the source rather than the interface, and their
        # placeholders are prose, not arguments.
        kinds = {occurrence.get("kind") for occurrence in occurrences}
        if kinds == {"rust_doc_comment"}:
            skipped_templates += 1
            continue

        segments = split_segments(source)
        if len([segment for segment in segments if segment]) < MINIMUM_SEGMENTS:
            skipped_templates += 1
            continue

        # Two adjacent arguments cannot be told apart when matching, so a
        # template that has them is dropped rather than guessed at.
        if any(not segment for segment in segments[1:-1]):
            skipped_templates += 1
            continue

        # A pattern that starts with a placeholder would have to be tested
        # against every string, so it gets its own table.
        patterns.append((segments, translation))

    leading = [entry for entry in patterns if entry[0][0] == ""]
    anchored = [entry for entry in patterns if entry[0][0] != ""]

    lines = [
        "// Generated by script/localization/generate_zh_cn.py -- do not edit by hand.",
        "//",
        "// Translations come from the community localization project LI-NA/zed-i18n",
        "// (AGPL-3.0), which tracks the upstream Zed source tree.",
        "",
        "/// English source string -> Simplified Chinese, for strings that are",
        "/// rendered verbatim.",
        "#[rustfmt::skip]",
        "pub(super) static TRANSLATIONS: &[(&str, &str)] = &[",
    ]
    for source, translation in exact:
        lines.append(f"    ({rust_string(source)}, {rust_string(translation)}),")
    lines.append("];")
    lines.append("")

    def table(name: str, entries: list, doc: str) -> None:
        lines.append(f"/// {doc}")
        lines.append("#[rustfmt::skip]")
        lines.append(f"pub(super) static {name}: &[(&[&str], &str)] = &[")
        for segments, translation in entries:
            rendered = ", ".join(rust_string(segment) for segment in segments)
            lines.append(f"    (&[{rendered}], {rust_string(translation)}),")
        lines.append("];")
        lines.append("")

    table(
        "PATTERNS",
        anchored,
        "Messages built with `format!`, split into the literal segments that\n/// surround each argument, keyed by their first character.",
    )
    table(
        "LEADING_PATTERNS",
        leading,
        "Messages whose first segment is empty, i.e. that start with an\n/// argument. These are checked for every string.",
    )

    with open(sys.argv[3], "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))

    print(
        f"{len(exact)} verbatim strings, {len(anchored)} anchored patterns, "
        f"{len(leading)} leading patterns, {skipped_templates} templates skipped"
    )

if __name__ == "__main__":
    main()
