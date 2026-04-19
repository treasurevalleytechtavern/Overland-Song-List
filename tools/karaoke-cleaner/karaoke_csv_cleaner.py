#!/usr/bin/env python3
"""
Clean messy karaoke machine CSV exports into review-safe song metadata.

The default run is fully offline and conservative. Online validation can be
enabled with --validate-online; results are cached so repeated rows do not
cause repeated lookups.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


OUTPUT_COLUMNS = [
    "title",
    "artist",
    "year",
    "decade",
    "categories",
    "social_singing",
    "original_vocal",
    "possible_duplicate",
    "match_confidence",
    "needs_review",
    "notes",
    "raw_input",
]

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
DEFAULT_CACHE_PATH = DEFAULT_OUTPUT_DIR / "metadata_cache.json"

APPROVED_CATEGORIES = [
    "Pop",
    "Rock",
    "Country",
    "Hip-Hop",
    "Rap",
    "R&B",
    "Soul",
    "Alternative / Indie",
    "Emo / Pop Punk",
    "Metal / Hard Rock",
    "Dance / Disco",
    "Classic Rock",
    "Punk",
    "Holiday",
    "Broadway / Musical",
    "Novelty / Comedy",
]

IGNORED_FIELD_HINTS = (
    "directory",
    "dir",
    "folder",
    "path",
    "location",
    "file path",
    "filepath",
)

TITLE_FIELD_HINTS = ("title", "song title", "track title")
ARTIST_FIELD_HINTS = ("artist", "singer", "performer")
RAW_FIELD_HINTS = ("song", "song name", "filename", "file", "track", "description")
CATEGORY_FIELD_HINTS = ("categories", "category", "genre", "genres")
YEAR_FIELD_HINTS = ("year", "release year", "original year")
DECADE_FIELD_HINTS = ("decade", "decades")
SOCIAL_FIELD_HINTS = ("social singing", "social_singing", "social", "singing")
VOCAL_FIELD_HINTS = ("original vocal", "original_vocal", "vocal", "vocals", "voice")

VERSION_PHRASES = (
    "live",
    "acoustic",
    "remix",
    "radio edit",
    "duet version",
    "solo version",
    "karaoke version",
    "from ",
    "remastered",
    "reprise",
    "explicit",
    "clean",
)

NOISE_PHRASES = (
    "downloaded from",
    "download from",
    "provided by",
    "karaoke version",
    "instrumental with lyrics",
    "with lyrics",
)

MUSICBRAINZ_ENDPOINT = "https://musicbrainz.org/ws/2/recording/"
USER_AGENT = "OverlandKaraokeCleaner/1.0 (local csv cleanup tool)"


GENRE_MAP = {
    "pop": "Pop",
    "rock": "Rock",
    "country": "Country",
    "hip hop": "Hip-Hop",
    "hip-hop": "Hip-Hop",
    "rap": "Rap",
    "rnb": "R&B",
    "r&b": "R&B",
    "rhythm and blues": "R&B",
    "soul": "Soul",
    "alternative": "Alternative / Indie",
    "indie": "Alternative / Indie",
    "emo": "Emo / Pop Punk",
    "pop punk": "Emo / Pop Punk",
    "metal": "Metal / Hard Rock",
    "hard rock": "Metal / Hard Rock",
    "dance": "Dance / Disco",
    "disco": "Dance / Disco",
    "classic rock": "Classic Rock",
    "punk": "Punk",
    "christmas": "Holiday",
    "holiday": "Holiday",
    "broadway": "Broadway / Musical",
    "musical": "Broadway / Musical",
    "show tune": "Broadway / Musical",
    "comedy": "Novelty / Comedy",
    "novelty": "Novelty / Comedy",
}


@dataclass
class CleanedRow:
    title: str = ""
    artist: str = ""
    year: str = ""
    decade: str = ""
    categories: str = ""
    social_singing: str = ""
    original_vocal: str = ""
    possible_duplicate: str = ""
    match_confidence: str = "Low"
    needs_review: str = "Yes"
    notes: list[str] = field(default_factory=list)
    raw_input: str = ""
    normalized_key: str = ""

    def as_output_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "artist": self.artist,
            "year": self.year,
            "decade": self.decade,
            "categories": self.categories,
            "social_singing": self.social_singing,
            "original_vocal": self.original_vocal,
            "possible_duplicate": self.possible_duplicate,
            "match_confidence": self.match_confidence,
            "needs_review": self.needs_review,
            "notes": "; ".join(unique_preserve_order(self.notes)),
            "raw_input": self.raw_input,
        }


def unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            unique.append(cleaned)
            seen.add(cleaned)
    return unique


def normalize_header(value: str) -> str:
    return normalize_text(value).replace("_", " ")


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9&]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_for_duplicate(title: str, artist: str) -> str:
    title_norm = normalize_text(remove_version_noise(title))
    artist_norm = normalize_text(artist)
    title_norm = re.sub(r"^(the|a|an)\s+", "", title_norm)
    artist_norm = re.sub(r"^(the|a|an)\s+", "", artist_norm)
    return f"{artist_norm}::{title_norm}"


def remove_version_noise(value: str) -> str:
    text = value or ""
    text = re.sub(r"\((?:karaoke|lyrics?|instrumental)\)", "", text, flags=re.I)
    return text.strip()


def title_case_display(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip(" -_.,;:"))
    if not text:
        return ""
    if text.isupper() or text.islower():
        small_words = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on", "or", "the", "to", "vs", "with"}
        words = []
        for index, word in enumerate(text.lower().split()):
            if index and word in small_words:
                words.append(word)
            elif word in {"dj", "ac", "dc"}:
                words.append(word.upper())
            elif word == "feat":
                words.append("feat.")
            else:
                words.append(word[:1].upper() + word[1:])
        text = " ".join(words)
    text = re.sub(r"\bIi\b", "II", text)
    text = re.sub(r"\bIii\b", "III", text)
    text = re.sub(r"\bIv\b", "IV", text)
    text = re.sub(r"\bUsa\b", "USA", text)
    return text


def clean_raw_value(value: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    text = value or ""
    original = text

    text = text.replace("\ufeff", "")
    text = text.replace("\\", "/")
    if "/" in text:
        text = text.split("/")[-1]
        notes.append("removed path fragments")

    text = re.sub(r"\.(zip|mp3|mp4|m4a|wav|flac|cdg|avi|mov|kar|mid|txt|csv)$", "", text, flags=re.I)
    if text != original:
        notes.append("removed file extension")

    lowered = text.lower()
    for phrase in NOISE_PHRASES:
        index = lowered.find(phrase)
        if index >= 0:
            text = text[:index]
            lowered = text.lower()
            notes.append("removed downloaded/source text")

    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*[\[\{](.*?)[\]\}]\s*", lambda m: keep_allowed_bracket(m.group(1), notes), text)
    text = re.sub(r"\s*\((.*?)\)\s*", lambda m: keep_allowed_bracket(m.group(1), notes, parens=True), text)

    before = text
    text = remove_catalog_tokens(text)
    if text != before:
        notes.append("removed machine code")

    text = re.sub(r"\b(track|trk|disc|disk|cd)\s*\d+\b", " ", text, flags=re.I)
    text = re.sub(r"\b\d{1,2}\s*of\s*\d{1,2}\b", " ", text, flags=re.I)
    text = re.sub(r"(^|[\s-])\d{1,3}(?=\s*[-.)_])", " ", text)
    text = re.sub(r"\s*[-|]+\s*", " - ", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" -_.,;:")

    return text, notes


def keep_allowed_bracket(inner: str, notes: list[str], parens: bool = False) -> str:
    normalized = normalize_text(inner)
    if any(normalized.startswith(phrase.strip()) or phrase.strip() in normalized for phrase in VERSION_PHRASES):
        notes.append(f"kept {inner.strip()} as version tag")
        left, right = ("(", ")") if parens else ("[", "]")
        return f" {left}{inner.strip()}{right} "
    notes.append("removed bracketed junk")
    return " "


def remove_catalog_tokens(text: str) -> str:
    token_patterns = [
        r"\b(?:sc|sf|cb|dk|zoom|sunfly|karaoke|kh|kv|phm|leg|ah|mm|tt|sbi|mrh)[-\s_]?\d{2,6}[-\s_]?\d{0,3}\b",
        r"\b[a-z]{1,5}\d{3,6}[-\s_]?\d{1,3}\b",
        r"\b\d{4,6}[-\s_]\d{1,3}\b",
    ]
    cleaned = text
    for pattern in token_patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.I)
    return re.sub(r"\s+", " ", cleaned).strip()


def select_field(row: dict[str, str], hints: tuple[str, ...]) -> str:
    by_header = {normalize_header(k): v for k, v in row.items()}
    for hint in hints:
        if hint in by_header and str(by_header[hint]).strip():
            return str(by_header[hint])
    for header, value in by_header.items():
        if any(hint in header for hint in hints) and str(value).strip():
            return str(value)
    return ""


def select_raw_input(row: dict[str, str]) -> str:
    ignored = {key for key in row if any(hint in normalize_header(key) for hint in IGNORED_FIELD_HINTS)}
    title = select_field(row, TITLE_FIELD_HINTS)
    artist = select_field(row, ARTIST_FIELD_HINTS)
    if title or artist:
        return " - ".join(part for part in [artist, title] if part)

    hinted = select_field({k: v for k, v in row.items() if k not in ignored}, RAW_FIELD_HINTS)
    if hinted:
        return hinted

    candidates = [str(v) for k, v in row.items() if k not in ignored and str(v).strip()]
    if not candidates:
        return ""
    return max(candidates, key=len)


def parse_artist_title(row: dict[str, str]) -> CleanedRow:
    raw_input = select_raw_input(row)
    cleaned = CleanedRow(raw_input=raw_input)
    if not raw_input.strip():
        cleaned.notes.append("empty raw input")
        return cleaned

    title_field = select_field(row, TITLE_FIELD_HINTS)
    artist_field = select_field(row, ARTIST_FIELD_HINTS)
    if title_field or artist_field:
        title_raw, title_notes = clean_raw_value(title_field)
        artist_raw, artist_notes = clean_raw_value(artist_field)
        cleaned.title = title_case_display(title_raw)
        cleaned.artist = title_case_display(artist_raw)
        cleaned.notes.extend(title_notes + artist_notes)
        cleaned.match_confidence = "Medium" if cleaned.title and cleaned.artist else "Low"
        cleaned.needs_review = "" if cleaned.title and cleaned.artist else "Yes"
    else:
        text, notes = clean_raw_value(raw_input)
        cleaned.notes.extend(notes)
        artist, title, split_note, confidence = split_single_field(text)
        cleaned.artist = title_case_display(artist)
        cleaned.title = title_case_display(title)
        cleaned.match_confidence = confidence
        cleaned.needs_review = "" if confidence == "Medium" and cleaned.title and cleaned.artist else "Yes"
        if split_note:
            cleaned.notes.append(split_note)

    if not cleaned.title or not cleaned.artist:
        cleaned.match_confidence = "Low"
        cleaned.needs_review = "Yes"
        cleaned.notes.append("could not confidently separate artist/title")

    cleaned.normalized_key = normalize_for_duplicate(cleaned.title, cleaned.artist)
    return cleaned


def split_single_field(text: str) -> tuple[str, str, str, str]:
    if not text:
        return "", "", "empty cleaned input", "Low"

    by_match = re.search(r"(.+?)\s+\bby\b\s+(.+)", text, flags=re.I)
    if by_match:
        return by_match.group(2), by_match.group(1), "split on title by artist", "Medium"

    separators = [" - ", " -- ", " \u2013 ", " \u2014 ", " | ", "\t"]
    for separator in separators:
        if separator in text:
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) >= 2:
                left, right = parts[0], " ".join(parts[1:])
                if looks_like_catalog_or_track(left):
                    return "", right, "removed leading catalog section", "Low"
                return left, right, "assumed artist - title order", "Medium"

    comma_match = re.match(r"^([^,]{2,60}),\s*(.+)$", text)
    if comma_match:
        return comma_match.group(1), comma_match.group(2), "split on comma; possible reversed artist/title", "Low"

    return "", text, "single field had no reliable separator", "Low"


def looks_like_catalog_or_track(value: str) -> bool:
    return bool(re.fullmatch(r"(?:[a-z]{1,6}[-\s_]?)?\d{1,6}", normalize_text(value).replace(" ", ""), flags=re.I))


def derive_decade(year: str) -> str:
    if not re.fullmatch(r"\d{4}", year or ""):
        return ""
    value = int(year)
    if value < 1900:
        return ""
    decade_start = (value // 10) * 10
    if decade_start >= 2000:
        return f"{decade_start}s"
    return f"{str(decade_start)[2:]}s"


def normalize_decade_value(value: str) -> str:
    normalized = normalize_text(value)
    four_digit = re.search(r"\b(19\d0|20\d0)s\b", normalized)
    if four_digit:
        return derive_decade(four_digit.group(1))
    two_digit = re.search(r"\b(\d{2})s\b", normalized)
    if two_digit:
        return f"{two_digit.group(1)}s"
    return ""


def categories_from_tags(tags: list[str]) -> str:
    mapped: list[str] = []
    normalized_tags = [normalize_text(tag) for tag in tags]
    for tag in normalized_tags:
        for key, category in GENRE_MAP.items():
            if key in tag and category not in mapped:
                mapped.append(category)
    return ", ".join(category for category in APPROVED_CATEGORIES if category in mapped)


def categories_from_field(value: str) -> str:
    if not value:
        return ""
    candidates = re.split(r"[,;/|]+", value)
    mapped: list[str] = []
    for candidate in candidates:
        normalized = normalize_text(candidate)
        exact = next((category for category in APPROVED_CATEGORIES if normalize_text(category) == normalized), "")
        if exact and exact not in mapped:
            mapped.append(exact)
            continue
        for key, category in GENRE_MAP.items():
            if key == normalized or key in normalized:
                if category not in mapped:
                    mapped.append(category)
                break
    return ", ".join(category for category in APPROVED_CATEGORIES if category in mapped)


def apply_existing_metadata(row: CleanedRow, source_row: dict[str, str]) -> None:
    year = select_field(source_row, YEAR_FIELD_HINTS).strip()
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", year)
    if year_match:
        row.year = year_match.group(1)
        row.decade = derive_decade(row.year)

    decade = select_field(source_row, DECADE_FIELD_HINTS).strip()
    if not row.decade and decade:
        row.decade = normalize_decade_value(decade)

    categories = categories_from_field(select_field(source_row, CATEGORY_FIELD_HINTS))
    if categories:
        row.categories = categories

    social = normalize_text(select_field(source_row, SOCIAL_FIELD_HINTS))
    category_text = normalize_text(select_field(source_row, CATEGORY_FIELD_HINTS))
    if "group" in social or "group song" in category_text:
        row.social_singing = "Group Songs"
    elif "duet" in social or "duet" in category_text:
        row.social_singing = "Duets"

    vocal_raw = normalize_text(select_field(source_row, VOCAL_FIELD_HINTS))
    if vocal_raw in {"male", "female", "mixed"}:
        row.original_vocal = vocal_raw[:1].upper() + vocal_raw[1:]


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def validate_online(row: CleanedRow, cache: dict[str, Any], delay: float) -> None:
    if not row.title or not row.artist:
        return

    key = row.normalized_key
    if key in cache:
        result = cache[key]
    else:
        time.sleep(delay)
        query = quote_plus(f'recording:"{row.title}" AND artist:"{row.artist}"')
        url = f"{MUSICBRAINZ_ENDPOINT}?query={query}&fmt=json&limit=5&inc=artist-credits+releases+tags"
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - validation must not block cleaning.
            result = {"error": str(exc)}
        cache[key] = result

    if result.get("error"):
        row.needs_review = "Yes"
        row.notes.append("online validation unavailable")
        return

    recordings = result.get("recordings", [])
    if not recordings:
        row.match_confidence = "Low"
        row.needs_review = "Yes"
        row.notes.append("no online metadata match")
        return

    best = score_musicbrainz_match(row, recordings)
    if not best:
        row.match_confidence = "Low"
        row.needs_review = "Yes"
        row.notes.append("multiple possible song matches")
        return

    recording, score = best
    if score >= 0.92:
        row.match_confidence = "High"
        row.needs_review = ""
        apply_musicbrainz_metadata(row, recording)
    elif score >= 0.78:
        row.match_confidence = "Medium"
        row.needs_review = "Yes"
        apply_musicbrainz_metadata(row, recording, conservative=True)
        row.notes.append("probable online metadata match")
    else:
        row.match_confidence = "Low"
        row.needs_review = "Yes"
        row.notes.append("online lookup ambiguous")


def score_musicbrainz_match(row: CleanedRow, recordings: list[dict[str, Any]]) -> Optional[tuple[dict[str, Any], float]]:
    scored = []
    expected_title = normalize_text(row.title)
    expected_artist = normalize_text(row.artist)
    for recording in recordings:
        title = normalize_text(recording.get("title", ""))
        artist_credit = normalize_text(" ".join(part.get("name", "") for part in recording.get("artist-credit", [])))
        title_score = difflib.SequenceMatcher(None, expected_title, title).ratio()
        artist_score = difflib.SequenceMatcher(None, expected_artist, artist_credit).ratio()
        scored.append((recording, (title_score * 0.6) + (artist_score * 0.4)))
    scored.sort(key=lambda item: item[1], reverse=True)
    if not scored:
        return None
    if len(scored) > 1 and scored[0][1] - scored[1][1] < 0.04:
        return None
    return scored[0]


def apply_musicbrainz_metadata(row: CleanedRow, recording: dict[str, Any], conservative: bool = False) -> None:
    if not conservative:
        row.title = title_case_display(recording.get("title", row.title))
        artist_credit = " ".join(part.get("name", "") for part in recording.get("artist-credit", []))
        if artist_credit:
            row.artist = title_case_display(artist_credit)

    dates = []
    if recording.get("first-release-date"):
        dates.append(recording["first-release-date"])
    for release in recording.get("releases", []):
        if release.get("date"):
            dates.append(release["date"])
    years = sorted({date[:4] for date in dates if re.match(r"\d{4}", date)})
    if years:
        row.year = years[0]
        row.decade = derive_decade(row.year)
    else:
        row.notes.append("could not confirm year")

    tags = [tag.get("name", "") for tag in recording.get("tags", []) if tag.get("name")]
    categories = categories_from_tags(tags)
    if categories:
        row.categories = categories
    else:
        row.notes.append("could not confirm genre")


def flag_possible_duplicates(rows: list[CleanedRow]) -> None:
    by_artist: dict[str, list[CleanedRow]] = {}
    for row in rows:
        if row.artist and row.title:
            by_artist.setdefault(normalize_text(row.artist), []).append(row)

    for bucket in by_artist.values():
        if len(bucket) < 2 or len(bucket) > 500:
            continue
        for index, left in enumerate(bucket):
            left_title = normalize_text(left.title)
            for right in bucket[index + 1 :]:
                ratio = difflib.SequenceMatcher(None, left_title, normalize_text(right.title)).ratio()
                if 0.88 <= ratio < 1.0:
                    left.possible_duplicate = "Yes"
                    right.possible_duplicate = "Yes"
                    left.needs_review = "Yes"
                    right.needs_review = "Yes"
                    left.notes.append("possible duplicate spelling variant")
                    right.notes.append("possible duplicate spelling variant")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError("Input CSV has no header row.")
        return [dict(row) for row in reader]


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore", quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)


def process_file(input_path: Path, output_dir: Path, validate: bool, cache_path: Path, delay: float) -> tuple[int, int, int]:
    source_rows = read_csv(input_path)
    parsed_rows = []
    for source_row in source_rows:
        parsed = parse_artist_title(source_row)
        apply_existing_metadata(parsed, source_row)
        parsed_rows.append(parsed)

    cache = load_cache(cache_path) if validate else {}
    if validate:
        for row in parsed_rows:
            validate_online(row, cache, delay)
        save_cache(cache_path, cache)

    kept: list[CleanedRow] = []
    removed_duplicates: list[CleanedRow] = []
    seen: dict[str, CleanedRow] = {}
    for row in parsed_rows:
        key = row.normalized_key
        if key and key in seen:
            duplicate = row
            duplicate.possible_duplicate = "Yes"
            duplicate.needs_review = "Yes"
            duplicate.notes.append("removed exact duplicate")
            removed_duplicates.append(duplicate)
            continue
        if key:
            seen[key] = row
        kept.append(row)

    flag_possible_duplicates(kept)

    cleaned_output = [row.as_output_dict() for row in kept]
    review_rows = [
        row.as_output_dict()
        for row in kept
        if row.needs_review == "Yes" or row.match_confidence == "Low" or row.possible_duplicate == "Yes"
    ]
    duplicate_rows = [row.as_output_dict() for row in removed_duplicates]

    write_csv(output_dir / "cleaned_output.csv", cleaned_output)
    write_csv(output_dir / "review_needed.csv", review_rows)
    write_csv(output_dir / "duplicates_removed.csv", duplicate_rows)

    return len(cleaned_output), len(review_rows), len(duplicate_rows)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean messy karaoke CSV exports into standardized song metadata.")
    parser.add_argument("input_csv", type=Path, help="Raw karaoke CSV export. This file is never overwritten.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for cleaned_output.csv, review_needed.csv, and duplicates_removed.csv.",
    )
    parser.add_argument(
        "--validate-online",
        action="store_true",
        help="Opt in to conservative MusicBrainz validation and metadata enrichment.",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help="JSON cache for online validation results.",
    )
    parser.add_argument(
        "--lookup-delay",
        type=float,
        default=1.0,
        help="Delay in seconds between uncached online lookups.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    if not args.input_csv.exists():
        parser.error(f"Input CSV not found: {args.input_csv}")

    cleaned_count, review_count, duplicate_count = process_file(
        input_path=args.input_csv,
        output_dir=args.output_dir,
        validate=args.validate_online,
        cache_path=args.cache,
        delay=args.lookup_delay,
    )
    print(f"Wrote {cleaned_count} cleaned rows to {args.output_dir / 'cleaned_output.csv'}")
    print(f"Wrote {review_count} review rows to {args.output_dir / 'review_needed.csv'}")
    print(f"Wrote {duplicate_count} removed duplicates to {args.output_dir / 'duplicates_removed.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
