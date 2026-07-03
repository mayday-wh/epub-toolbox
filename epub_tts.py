from __future__ import annotations

import argparse
import asyncio
import html
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = "+0%"
DEFAULT_PITCH = "+0Hz"
DEFAULT_VOLUME = "+0%"
MAX_TTS_CHARS = 1800
TTS_RETRIES = 3


@dataclass
class Chapter:
    title: str
    text: str
    source: str


@dataclass
class Book:
    title: str
    chapters: list[Chapter]


@dataclass
class ManifestItem:
    href: str
    properties: str


class TextExtractor(HTMLParser):
    block_tags = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
    skip_tags = {"head", "script", "style", "svg", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.skip_tags:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.skip_tags and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        raw = html.unescape("".join(self.parts)).replace("\xa0", " ")
        lines = []
        for line in raw.splitlines():
            clean = re.sub(r"\s+", " ", line).strip()
            if clean:
                lines.append(clean)
        return "\n".join(lines)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def decode_document(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def extract_text(data: bytes) -> str:
    parser = TextExtractor()
    parser.feed(decode_document(data))
    return parser.text()


def safe_filename(name: str, fallback: str = "untitled") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:90] or fallback


def first_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if 2 <= len(line) <= 80:
            return line
    return fallback


def parse_epub(epub_path: Path, min_chars: int = 30) -> Book:
    with zipfile.ZipFile(epub_path) as zf:
        container = ET.fromstring(zf.read("META-INF/container.xml"))
        rootfile = None
        for elem in container.iter():
            if local_name(elem.tag) == "rootfile":
                rootfile = elem.attrib.get("full-path")
                break
        if not rootfile:
            raise RuntimeError("Cannot find EPUB rootfile in META-INF/container.xml")

        opf = ET.fromstring(zf.read(rootfile))
        base_dir = posixpath.dirname(rootfile)
        title = epub_path.stem
        for elem in opf.iter():
            if local_name(elem.tag) == "title" and (elem.text or "").strip():
                title = (elem.text or "").strip()
                break

        manifest: dict[str, ManifestItem] = {}
        for elem in opf.iter():
            if local_name(elem.tag) == "item":
                item_id = elem.attrib.get("id")
                href = elem.attrib.get("href")
                media_type = elem.attrib.get("media-type", "")
                properties = elem.attrib.get("properties", "")
                if item_id and href and ("html" in media_type or href.lower().endswith((".xhtml", ".html", ".htm"))):
                    manifest[item_id] = ManifestItem(href=href, properties=properties)

        spine_ids = []
        for elem in opf.iter():
            if local_name(elem.tag) == "itemref":
                idref = elem.attrib.get("idref")
                if idref:
                    spine_ids.append(idref)

        ordered_paths = []
        for item_id in spine_ids:
            item = manifest.get(item_id)
            if item and "nav" not in item.properties.split():
                ordered_paths.append(posixpath.normpath(posixpath.join(base_dir, item.href)))

        if not ordered_paths:
            ordered_paths = [
                name
                for name in zf.namelist()
                if name.lower().endswith((".xhtml", ".html", ".htm"))
            ]

        chapters: list[Chapter] = []
        seen_paths: set[str] = set()
        for index, path in enumerate(ordered_paths, start=1):
            if path in seen_paths or path not in zf.namelist():
                continue
            seen_paths.add(path)
            text = extract_text(zf.read(path))
            if len(text) < min_chars:
                continue
            fallback = f"Chapter {index:03d}"
            chapters.append(Chapter(title=first_title(text, fallback), text=text, source=path))

    if not chapters:
        raise RuntimeError("No readable chapter text was found in this EPUB.")
    return Book(title=title, chapters=chapters)


def select_chapters(chapters: list[Chapter], args: argparse.Namespace) -> list[Chapter]:
    start = max(args.start_index, 1) - 1
    end = args.end_index if args.end_index else None
    selected = chapters[start:end]
    if args.exclude_regex:
        pattern = re.compile(args.exclude_regex)
        selected = [chapter for chapter in selected if not pattern.search(chapter.title) and not pattern.search(chapter.source)]
    if not selected:
        raise RuntimeError("No chapters left after applying chapter filters.")
    return selected


def split_text(text: str, max_chars: int = MAX_TTS_CHARS) -> list[str]:
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    sentence_pattern = re.compile(r"(?<=[。！？!?；;：:])")
    for paragraph in paragraphs:
        pieces = [p.strip() for p in sentence_pattern.split(paragraph) if p.strip()]
        if not pieces:
            pieces = [paragraph]
        for piece in pieces:
            while len(piece) > max_chars:
                part, piece = piece[:max_chars], piece[max_chars:]
                if len(current) + len(part) + 1 > max_chars:
                    flush()
                current = f"{current}\n{part}".strip()
                flush()
            if len(current) + len(piece) + 1 > max_chars:
                flush()
            current = f"{current}\n{piece}".strip()
    flush()
    return chunks


async def list_voices(locale: str | None) -> None:
    import edge_tts

    voices = await edge_tts.list_voices()
    for voice in voices:
        if locale and voice.get("Locale") != locale:
            continue
        short = voice.get("ShortName", "")
        gender = voice.get("Gender", "")
        friendly = voice.get("FriendlyName", "")
        print(f"{short:<30} {voice.get('Locale', ''):<8} {gender:<6} {friendly}")


async def stream_tts_chunk(
    text: str,
    out,
    voice: str,
    rate: str,
    pitch: str,
    volume: str,
    retries: int = TTS_RETRIES,
) -> None:
    import edge_tts

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate,
                pitch=pitch,
                volume=volume,
            )
            async for message in communicate.stream():
                if message["type"] == "audio":
                    out.write(message["data"])
            return
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            await asyncio.sleep(1.5 * attempt)
    assert last_error is not None
    raise last_error


async def write_tts_mp3(
    text: str,
    mp3_path: Path,
    voice: str,
    rate: str,
    pitch: str,
    volume: str,
    max_chars: int,
) -> None:
    chunks = split_text(text, max_chars=max_chars)
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = mp3_path.with_name(mp3_path.name + ".part")
    try:
        with temp_path.open("wb") as out:
            for index, chunk in enumerate(chunks, start=1):
                await stream_tts_chunk(chunk, out, voice, rate, pitch, volume)
                print(f"    chunk {index}/{len(chunks)}")
        temp_path.replace(mp3_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def write_text_preview(book: Book, output_dir: Path, chapters: list[Chapter] | None = None) -> Path:
    preview_path = output_dir / "book_text_preview.txt"
    preview_chapters = chapters if chapters is not None else book.chapters
    with preview_path.open("w", encoding="utf-8") as f:
        f.write(book.title + "\n\n")
        for i, chapter in enumerate(preview_chapters, start=1):
            f.write(f"## {i:03d} {chapter.title}\n")
            f.write(f"Source: {chapter.source}\n\n")
            f.write(chapter.text[:2000])
            f.write("\n\n")
    return preview_path


def concat_mp3_with_ffmpeg(chapter_files: Iterable[Path], output_file: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False

    files = list(chapter_files)
    if not files:
        return False

    with tempfile.TemporaryDirectory() as temp_dir:
        list_path = Path(temp_dir) / "concat.txt"
        with list_path.open("w", encoding="utf-8") as f:
            for file in files:
                escaped = file.resolve().as_posix().replace("'", r"'\''")
                f.write(f"file '{escaped}'\n")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c",
                "copy",
                str(output_file),
            ],
            check=True,
        )
    return True


async def convert(args: argparse.Namespace) -> None:
    epub_path = Path(args.epub).resolve()
    if not epub_path.exists():
        raise FileNotFoundError(epub_path)

    book = parse_epub(epub_path, min_chars=args.min_chars)
    output_root = Path(args.output).resolve() if args.output else epub_path.with_suffix("")
    output_root.mkdir(parents=True, exist_ok=True)
    chapters_dir = output_root / "chapters"

    print(f"Book: {book.title}")
    chapters = select_chapters(book.chapters, args)

    print(f"Chapters: {len(chapters)} selected / {len(book.chapters)} extracted")
    print(f"Voice: {args.voice}")
    print(f"Output: {output_root}")
    preview = write_text_preview(book, output_root, chapters)
    print(f"Text preview: {preview}")

    chapter_files: list[Path] = []
    for index, chapter in enumerate(chapters, start=1):
        filename = safe_filename(f"{index:03d} {chapter.title}", fallback=f"{index:03d}") + ".mp3"
        mp3_path = chapters_dir / filename
        chapter_files.append(mp3_path)
        if mp3_path.exists() and not args.overwrite:
            print(f"[skip] {mp3_path.name}")
            continue
        print(f"[tts] {index:03d}/{len(chapters):03d} {chapter.title}")
        await write_tts_mp3(
            chapter.text,
            mp3_path,
            voice=args.voice,
            rate=args.rate,
            pitch=args.pitch,
            volume=args.volume,
            max_chars=args.max_chars,
        )

    playlist = output_root / "chapters.m3u"
    with playlist.open("w", encoding="utf-8") as f:
        for file in chapter_files:
            f.write(file.resolve().as_posix() + "\n")
    print(f"Playlist: {playlist}")

    if not args.no_merge:
        merged = output_root / (safe_filename(book.title, epub_path.stem) + ".mp3")
        if concat_mp3_with_ffmpeg(chapter_files, merged):
            print(f"Merged MP3: {merged}")
        else:
            print("ffmpeg not found; skipped full-book merge.")


def inspect_epub(args: argparse.Namespace) -> None:
    epub_path = Path(args.epub).resolve()
    if not epub_path.exists():
        raise FileNotFoundError(epub_path)

    book = parse_epub(epub_path, min_chars=args.min_chars)
    output_root = Path(args.output).resolve() if args.output else epub_path.with_suffix("")
    output_root.mkdir(parents=True, exist_ok=True)

    print(f"Book: {book.title}")
    chapters = select_chapters(book.chapters, args)
    preview = write_text_preview(book, output_root, chapters)

    print(f"Chapters: {len(chapters)} selected / {len(book.chapters)} extracted")
    print(f"Text preview: {preview}")
    for index, chapter in enumerate(chapters[: args.limit], start=1):
        print(f"{index:03d}. {chapter.title} ({len(chapter.text)} chars) [{chapter.source}]")
    if len(chapters) > args.limit:
        print(f"... {len(chapters) - args.limit} more")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert an EPUB book to MP3 files with Edge TTS.")
    subparsers = parser.add_subparsers(dest="command")

    def add_chapter_filter_args(target: argparse.ArgumentParser) -> None:
        target.add_argument("--start-index", type=int, default=1, help="First extracted chapter to use, 1-based.")
        target.add_argument("--end-index", type=int, help="Last extracted chapter to use, 1-based and inclusive.")
        target.add_argument("--exclude-regex", help="Skip chapters whose title or source path matches this regex.")

    voices = subparsers.add_parser("voices", help="List available Edge TTS voices.")
    voices.add_argument("--locale", default="zh-CN", help="Voice locale filter, e.g. zh-CN, zh-TW, en-US. Use empty string for all.")

    convert_parser = subparsers.add_parser("convert", help="Convert one EPUB file to MP3.")
    convert_parser.add_argument("epub", help="Path to the EPUB file.")
    convert_parser.add_argument("-o", "--output", help="Output folder. Default: folder named after the EPUB.")
    convert_parser.add_argument("--voice", default=DEFAULT_VOICE, help=f"TTS voice. Default: {DEFAULT_VOICE}")
    convert_parser.add_argument("--rate", default=DEFAULT_RATE, help="Speech rate, e.g. +10%, -10%.")
    convert_parser.add_argument("--pitch", default=DEFAULT_PITCH, help="Speech pitch, e.g. +5Hz, -5Hz.")
    convert_parser.add_argument("--volume", default=DEFAULT_VOLUME, help="Speech volume, e.g. +0%, -10%.")
    convert_parser.add_argument("--max-chars", type=int, default=MAX_TTS_CHARS, help="Max characters per TTS request.")
    convert_parser.add_argument("--min-chars", type=int, default=30, help="Skip EPUB sections shorter than this.")
    convert_parser.add_argument("--overwrite", action="store_true", help="Regenerate existing chapter MP3 files.")
    convert_parser.add_argument("--no-merge", action="store_true", help="Do not merge chapter MP3 files into one book MP3.")
    add_chapter_filter_args(convert_parser)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect EPUB text extraction without generating audio.")
    inspect_parser.add_argument("epub", help="Path to the EPUB file.")
    inspect_parser.add_argument("-o", "--output", help="Output folder for the text preview.")
    inspect_parser.add_argument("--min-chars", type=int, default=30, help="Skip EPUB sections shorter than this.")
    inspect_parser.add_argument("--limit", type=int, default=20, help="How many chapters to print.")
    add_chapter_filter_args(inspect_parser)

    return parser


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "voices":
        locale = args.locale or None
        await list_voices(locale)
    elif args.command == "convert":
        await convert(args)
    elif args.command == "inspect":
        inspect_epub(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
