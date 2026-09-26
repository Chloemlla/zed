//! Simplified Chinese translations for interface text.
//!
//! Zed writes its interface strings inline, at the call site. Rather than
//! rewriting every one of those call sites, this module translates text where
//! it enters GPUI's text layout: a string that exactly matches a catalogued
//! interface string -- or a message built from one with `format!` -- is
//! replaced by its Simplified Chinese translation before it is measured and
//! shaped.
//!
//! The dictionary lives in `crates/gpui/src/localization/zh_cn.rs`, generated
//! by `script/localization/generate_zh_cn.py`. Anything that is not in it --
//! code, file names, terminal output, messages from language servers -- is
//! rendered as-is.
//!
//! The interface is rendered in Simplified Chinese by default; set
//! `ZED_UI_LOCALE=en` to get English back.

use std::{
    collections::HashMap,
    sync::{
        OnceLock,
        atomic::{AtomicU8, Ordering},
    },
};

use crate::SharedString;

mod zh_cn;

/// A language the interface can be rendered in.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Locale {
    /// English, the language Zed's interface strings are written in.
    English = 1,
    /// Simplified Chinese.
    SimplifiedChinese = 2,
}

/// Marks [`LOCALE`] as not yet resolved.
const LOCALE_UNSET: u8 = 0;

static LOCALE: AtomicU8 = AtomicU8::new(LOCALE_UNSET);

/// The locale the interface is rendered in.
///
/// The first call resolves the locale from the environment; later calls are a
/// relaxed atomic load.
pub fn locale() -> Locale {
    let stored = LOCALE.load(Ordering::Relaxed);
    if stored == Locale::SimplifiedChinese as u8 {
        return Locale::SimplifiedChinese;
    }
    if stored == Locale::English as u8 {
        return Locale::English;
    }

    let detected = detected_locale();
    set_locale(detected);
    detected
}

/// Overrides the locale the interface is rendered in.
pub fn set_locale(locale: Locale) {
    LOCALE.store(locale as u8, Ordering::Relaxed);
}

/// Reads `ZED_UI_LOCALE`, defaulting to Simplified Chinese.
fn detected_locale() -> Locale {
    match std::env::var("ZED_UI_LOCALE") {
        Ok(value) => match_locale(&value),
        Err(_) => Locale::SimplifiedChinese,
    }
}

fn match_locale(value: &str) -> Locale {
    let normalized = value.trim().to_ascii_lowercase().replace('_', "-");
    if normalized == "zh" || normalized.starts_with("zh-") {
        Locale::SimplifiedChinese
    } else {
        Locale::English
    }
}

/// Translates `text` into the current locale, if a translation is catalogued.
///
/// `None` means the string has no translation and should be rendered as-is.
pub fn translate(text: &str) -> Option<String> {
    if locale() == Locale::English || text.is_empty() {
        return None;
    }

    if let Some(exact) = exact_lookup(text) {
        return Some(exact.to_owned());
    }

    pattern_lookup(text)
}

/// Translates `text` into the current locale, keeping `text` when there is no
/// translation for it.
pub fn translate_shared_string(text: SharedString) -> SharedString {
    if locale() == Locale::English {
        return text;
    }

    if let Some(exact) = exact_lookup(text.as_ref()) {
        return SharedString::new_static(exact);
    }

    match pattern_lookup(text.as_ref()) {
        Some(translated) => SharedString::from(translated),
        None => text,
    }
}

/// Looks `text` up in the table of verbatim strings.
fn exact_lookup(text: &str) -> Option<&'static str> {
    static TABLE: OnceLock<HashMap<&'static str, &'static str>> = OnceLock::new();
    let table = TABLE.get_or_init(|| zh_cn::TRANSLATIONS.iter().copied().collect());
    table.get(text).copied()
}

/// A message split into the literal segments surrounding each of its arguments,
/// paired with its translation.
type Pattern = (&'static [&'static str], &'static str);

/// Looks `text` up in the table of messages built with `format!`.
///
/// Patterns are grouped by their first character, so only the handful of
/// messages that could possibly match are compared.
fn pattern_lookup(text: &str) -> Option<String> {
    if let Some(first) = text.chars().next() {
        static INDEX: OnceLock<HashMap<char, Vec<Pattern>>> = OnceLock::new();
        let index = INDEX.get_or_init(|| {
            let mut index: HashMap<char, Vec<Pattern>> = HashMap::new();
            for pattern in zh_cn::PATTERNS {
                if let Some(first) = pattern.0.first().and_then(|segment| segment.chars().next()) {
                    index.entry(first).or_default().push(*pattern);
                }
            }
            index
        });

        if let Some(patterns) = index.get(&first) {
            if let Some(translated) = lookup_in(text, patterns) {
                return Some(translated);
            }
        }
    }

    lookup_in(text, zh_cn::LEADING_PATTERNS)
}

fn lookup_in(text: &str, patterns: &[Pattern]) -> Option<String> {
    for pattern in patterns {
        let (segments, translation) = *pattern;
        if let Some(captures) = match_segments(text, segments) {
            if let Some(translated) = substitute(translation, &captures) {
                return Some(translated);
            }
        }
    }

    None
}

/// Matches `text` against the literal segments of a message, returning the
/// arguments that were substituted into it.
///
/// The first segment anchors the start of the text and the last one anchors its
/// end, which is what keeps a message like `"{} copied to clipboard."` from
/// matching unrelated text that merely contains that sentence. Empty arguments
/// are rejected as well, since a template that matches with nothing in between
/// its literal segments is far more likely to be a plain interface string that
/// happens to contain the same words.
fn match_segments<'a>(text: &'a str, segments: &[&str]) -> Option<Vec<&'a str>> {
    let count = segments.len().checked_sub(1)?;
    if count == 0 {
        return None;
    }

    let mut remaining = text.strip_prefix(segments[0])?;
    let mut captures = Vec::with_capacity(count);
    for segment in segments[1..count].iter() {
        let segment = *segment;
        if segment.is_empty() {
            return None;
        }

        let position = remaining.find(segment)?;
        let (captured, rest) = remaining.split_at(position);
        if captured.is_empty() {
            return None;
        }

        captures.push(captured);
        remaining = &rest[segment.len()..];
    }

    let last = segments[count];
    let captured = if last.is_empty() {
        remaining
    } else {
        remaining.strip_suffix(last)?
    };
    if captured.is_empty() {
        return None;
    }

    captures.push(captured);
    Some(captures)
}

/// Substitutes `captures` into the arguments of `translation`.
///
/// Returns `None` when the translation expects more arguments than were
/// captured, which means the match was wrong and the text should be left alone.
fn substitute(translation: &str, captures: &[&str]) -> Option<String> {
    let mut translated = String::with_capacity(translation.len() + 16);
    let mut rest = translation;
    let mut used = 0;

    while let Some(start) = rest.find('{') {
        let Some(end) = rest[start..].find('}') else {
            break;
        };
        let Some(capture) = captures.get(used) else {
            return None;
        };

        translated.push_str(&rest[..start]);
        translated.push_str(capture);
        used += 1;
        rest = &rest[start + end + 1..];
    }

    if used == 0 {
        return None;
    }

    translated.push_str(rest);
    Some(translated)
}
