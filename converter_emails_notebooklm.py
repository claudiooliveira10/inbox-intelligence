#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import email
import html
import os
import re
import sys
from email import policy
from pathlib import Path
from typing import Iterable

DEFAULT_INPUT_DIR = Path(__file__).resolve().parent / "input"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
DEFAULT_BUNDLE_MB = 150


def sanitize_filename(name: str, max_len: int = 140) -> str:
    name = name.strip() if name else "sem_nome"
    name = re.sub(r'[\\/*?:"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        name = "sem_nome"
    return name[:max_len]


def safe_text(value: str | None) -> str:
    if value is None:
        return ""
    value = str(value)
    value = html.unescape(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(email.header.make_header(email.header.decode_header(value)))
    except Exception:
        return str(value)


def strip_html(raw_html: str) -> str:
    text = raw_html

    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"(?i)<li\s*>", "• ", text)

    text = re.sub(r"(?is)<script.*?>.*?</script>", "", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", "", text)
    text = re.sub(r"(?is)<head.*?>.*?</head>", "", text)

    text = re.sub(r"(?is)<[^>]+>", "", text)

    return safe_text(text)


def is_likely_inline_attachment(part: email.message.EmailMessage) -> bool:
    content_disposition = str(part.get("Content-Disposition", "")).lower()
    content_type = part.get_content_type().lower()
    filename = decode_header_value(part.get_filename() or "").lower()
    content_id = str(part.get("Content-ID", "")).strip()

    inline_types = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/webp",
        "image/svg+xml",
    }

    if "inline" in content_disposition and content_type in inline_types:
        return True

    if content_id and content_type in inline_types:
        return True

    inline_name_patterns = (
        "image",
        "logo",
        "signature",
        "assinatura",
        "facebook",
        "instagram",
        "linkedin",
        "twitter",
        "whatsapp",
        "banner",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".svg",
    )

    if filename and content_type in inline_types:
        if any(pattern in filename for pattern in inline_name_patterns):
            return True

    return False


def is_meaningful_attachment(part: email.message.EmailMessage) -> bool:
    filename = part.get_filename()
    if not filename:
        return False

    payload = part.get_payload(decode=True)
    if payload is None:
        return False

    if is_likely_inline_attachment(part):
        return False

    return True


def extract_body(msg: email.message.EmailMessage) -> tuple[str, str]:
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get("Content-Disposition", "")).lower()
            content_type = part.get_content_type()

            if "attachment" in disposition:
                continue

            try:
                payload = part.get_content()
            except Exception:
                try:
                    payload_bytes = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    payload = payload_bytes.decode(charset, errors="replace") if payload_bytes else ""
                except Exception:
                    payload = ""

            if not payload:
                continue

            if content_type == "text/plain":
                plain_parts.append(safe_text(str(payload)))
            elif content_type == "text/html":
                html_parts.append(strip_html(str(payload)))
    else:
        content_type = msg.get_content_type()
        try:
            payload = msg.get_content()
        except Exception:
            try:
                payload_bytes = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or "utf-8"
                payload = payload_bytes.decode(charset, errors="replace") if payload_bytes else ""
            except Exception:
                payload = ""

        if payload:
            if content_type == "text/plain":
                plain_parts.append(safe_text(str(payload)))
            elif content_type == "text/html":
                html_parts.append(strip_html(str(payload)))

    for item in plain_parts:
        if item:
            return item, "text/plain"

    for item in html_parts:
        if item:
            return item, "text/html"

    return "(sem conteúdo legível)", "unknown"


def save_attachments(
    msg: email.message.EmailMessage,
    attachments_root: Path,
    email_stem: str,
) -> list[str]:
    saved: list[str] = []
    attachments_root.mkdir(parents=True, exist_ok=True)

    counter = 1
    for part in msg.walk():
        if not is_meaningful_attachment(part):
            continue

        filename = part.get_filename()
        payload = part.get_payload(decode=True)

        filename = decode_header_value(filename)
        filename = sanitize_filename(filename, max_len=180)

        final_name = f"{email_stem}__{counter:03d}__{filename}"
        final_path = attachments_root / final_name

        try:
            with open(final_path, "wb") as f:
                f.write(payload)
            saved.append(final_name)
            counter += 1
        except Exception:
            continue

    return saved


def iter_email_files(input_dir: Path) -> Iterable[Path]:
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        yield path


def matches_filter(text: str, terms: list[str]) -> bool:
    if not terms:
        return True
    low = text.lower()
    return any(term.lower() in low for term in terms)


def write_email_txt(
    src: Path,
    output_dir: Path,
    attachments_dir: Path | None,
    filter_terms: list[str],
) -> tuple[bool, dict | None]:
    with open(src, "rb") as fp:
        msg = email.message_from_binary_file(fp, policy=policy.default)

    subject = decode_header_value(msg.get("Subject", "(sem assunto)"))
    from_ = decode_header_value(msg.get("From", ""))
    to_ = decode_header_value(msg.get("To", ""))
    cc_ = decode_header_value(msg.get("Cc", ""))
    date_ = decode_header_value(msg.get("Date", ""))

    body, body_source = extract_body(msg)

    searchable = "\n".join([subject, from_, to_, cc_, date_, body])
    if not matches_filter(searchable, filter_terms):
        return False, None

    email_stem = sanitize_filename(src.name)
    txt_name = f"{email_stem}.txt"
    txt_path = output_dir / txt_name

    saved_attachments: list[str] = []
    skipped_inline_attachments = 0
    for part in msg.walk():
        if part.get_filename() and not is_meaningful_attachment(part):
            skipped_inline_attachments += 1
    if attachments_dir is not None:
        saved_attachments = save_attachments(msg, attachments_dir, email_stem)

    lines: list[str] = [
        f"Ficheiro original: {src.name}",
        f"De: {from_}",
        f"Para: {to_}",
        f"CC: {cc_}",
        f"Data: {date_}",
        f"Assunto: {subject}",
        f"Origem do corpo: {body_source}",
        f"Anexos inline ignorados: {skipped_inline_attachments}",
        "",
    ]

    if saved_attachments:
        lines.append("Anexos extraídos:")
        for name in saved_attachments:
            lines.append(f"- {name}")
        lines.append("")

    lines.append("Mensagem:")
    lines.append(body)
    lines.append("")

    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path.write_text("\n".join(lines), encoding="utf-8")

    meta = {
        "original_file": src.name,
        "txt_file": txt_name,
        "from": from_,
        "to": to_,
        "cc": cc_,
        "date": date_,
        "subject": subject,
        "body_source": body_source,
        "attachments_count": len(saved_attachments),
        "inline_attachments_skipped": skipped_inline_attachments,
        "attachments": " | ".join(saved_attachments),
        "txt_size_bytes": txt_path.stat().st_size,
    }
    return True, meta


def write_index_csv(index_path: Path, rows: list[dict]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "original_file",
        "txt_file",
        "from",
        "to",
        "cc",
        "date",
        "subject",
        "body_source",
        "attachments_count",
        "inline_attachments_skipped",
        "attachments",
        "txt_size_bytes",
    ]
    with open(index_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def create_notebooklm_bundles(
    txt_dir: Path,
    bundles_dir: Path,
    max_bundle_mb: int,
) -> list[Path]:
    bundles_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = max_bundle_mb * 1024 * 1024

    txt_files = sorted(txt_dir.glob("*.txt"))
    if not txt_files:
        return []

    bundle_paths: list[Path] = []
    bundle_index = 1
    current_bundle = bundles_dir / f"bundle_{bundle_index:03d}.txt"
    current_size = 0

    out = open(current_bundle, "w", encoding="utf-8")
    bundle_paths.append(current_bundle)

    for txt_file in txt_files:
        content = txt_file.read_text(encoding="utf-8", errors="replace")
        block = (
            "\n"
            + "=" * 100
            + "\n"
            + f"FICHEIRO: {txt_file.name}\n"
            + "=" * 100
            + "\n\n"
            + content
            + "\n\n"
        )
        encoded_size = len(block.encode("utf-8"))

        if current_size > 0 and current_size + encoded_size > max_bytes:
            out.close()
            bundle_index += 1
            current_bundle = bundles_dir / f"bundle_{bundle_index:03d}.txt"
            out = open(current_bundle, "w", encoding="utf-8")
            bundle_paths.append(current_bundle)
            current_size = 0

        out.write(block)
        current_size += encoded_size

    out.close()
    return bundle_paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Converter emails raw para TXT limpos, extrair anexos, gerar CSV e bundles prontos para NotebookLM."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT_DIR),
        help=f"Pasta com emails raw (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Pasta raiz de saída (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--contains",
        nargs="*",
        default=[],
        help="Filtrar emails que contenham estas palavras",
    )
    parser.add_argument(
        "--no-attachments",
        action="store_true",
        help="Não extrair anexos",
    )
    parser.add_argument(
        "--bundle-mb",
        type=int,
        default=DEFAULT_BUNDLE_MB,
        help=f"Tamanho máximo de cada bundle para NotebookLM em MB (default: {DEFAULT_BUNDLE_MB})",
    )

    args = parser.parse_args()

    input_dir = Path(args.input).expanduser()
    output_root = Path(args.output).expanduser()

    input_dir = input_dir.resolve()
    output_root = output_root.resolve()

    txt_dir = output_root / "emails_txt"
    attachments_dir = None if args.no_attachments else output_root / "anexos"
    bundles_dir = output_root / "notebooklm_bundles"
    index_csv = output_root / "index.csv"
    errors_log = output_root / "erros.log"

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Erro: pasta de origem inválida: {input_dir}")
        print("Dica: coloca os emails raw dentro da pasta 'input' ao lado deste script, ou usa --input.")
        return 1

    output_root.mkdir(parents=True, exist_ok=True)
    if attachments_dir is not None:
        attachments_dir.mkdir(parents=True, exist_ok=True)
    txt_dir.mkdir(parents=True, exist_ok=True)
    bundles_dir.mkdir(parents=True, exist_ok=True)

    print("Inbox Intelligence")
    print("-" * 60)
    print(f"Input: {input_dir}")
    print(f"Output: {output_root}")
    print(f"Extrair anexos: {'não' if args.no_attachments else 'sim'}")
    print(f"Tamanho máximo bundle: {args.bundle_mb} MB")
    if args.contains:
        print(f"Filtro: {', '.join(args.contains)}")
    print("-" * 60)

    total = 0
    convertidos = 0
    ignorados = 0
    falhados = 0
    rows: list[dict] = []

    with open(errors_log, "w", encoding="utf-8") as err:
        for src in iter_email_files(input_dir):
            total += 1
            try:
                ok, meta = write_email_txt(
                    src=src,
                    output_dir=txt_dir,
                    attachments_dir=attachments_dir,
                    filter_terms=args.contains,
                )
                if ok and meta is not None:
                    rows.append(meta)
                    convertidos += 1
                    print(f"[OK] {src.name}")
                else:
                    ignorados += 1
                    print(f"[SKIP] {src.name}")
            except Exception as e:
                falhados += 1
                err.write(f"{src}\t{e}\n")
                print(f"[ERRO] {src.name}: {e}")

    write_index_csv(index_csv, rows)
    bundles = create_notebooklm_bundles(
        txt_dir=txt_dir,
        bundles_dir=bundles_dir,
        max_bundle_mb=args.bundle_mb,
    )

    print("\nResumo")
    print("-" * 60)
    print(f"Total lidos: {total}")
    print(f"Convertidos: {convertidos}")
    print(f"Ignorados por filtro: {ignorados}")
    print(f"Com erro: {falhados}")
    print(f"TXT: {txt_dir}")
    print(f"CSV: {index_csv}")
    print(f"Bundles NotebookLM: {bundles_dir}")
    print("\nPara correr sem argumentos:")
    print("python3 converter_emails_notebooklm.py")
    if attachments_dir:
        print(f"Anexos: {attachments_dir}")
    print(f"Log de erros: {errors_log}")
    print(f"Número de bundles: {len(bundles)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())