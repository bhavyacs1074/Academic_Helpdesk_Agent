import csv
import hashlib
import logging
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

if __package__:
    from scripts.rag import DB_DIR, EMBEDDING_MODEL, embed_texts, get_collection
else:
    from rag import DB_DIR, EMBEDDING_MODEL, embed_texts, get_collection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data"
BATCH_SIZE = 100

collection = get_collection(persist_dir=DB_DIR, model=EMBEDDING_MODEL)


def chunks(text: str, size: int = 250, overlap: int = 50) -> list[str]:
    """Split text into word-based chunks with overlap."""
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("size must be positive and overlap must be in [0, size)")

    words = text.split()
    step = size - overlap
    return [
        " ".join(words[index : index + size])
        for index in range(0, len(words), step)
    ]


def main() -> None:
    if not PDF_DIR.is_dir():
        raise SystemExit(f"Document directory {PDF_DIR} does not exist.")

    documents_by_type = {
        ".csv": sorted(
            path
            for path in PDF_DIR.rglob("*")
            if path.is_file() and path.suffix.lower() == ".csv"
        ),
        ".md": sorted(
            path
            for path in PDF_DIR.rglob("*")
            if path.is_file() and path.suffix.lower() == ".md"
        ),
        ".pdf": sorted(
            path
            for path in PDF_DIR.rglob("*")
            if path.is_file() and path.suffix.lower() == ".pdf"
        ),
    }

    if not any(documents_by_type.values()):
        raise SystemExit(f"No CSV, Markdown, or PDF files found in {PDF_DIR}.")

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str | int]] = []
    failures = 0
    indexed_chunks = 0

    def save_batch() -> None:
        if not ids:
            return
        embeddings = embed_texts(documents, model=EMBEDDING_MODEL)
        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        ids.clear()
        documents.clear()
        metadatas.clear()

    def add_text(
        source: str,
        text: str,
        file_type: str,
        location_type: str,
        location: str | int,
    ) -> int:
        added = 0
        for chunk_number, text_chunk in enumerate(chunks(text)):
            record_key = (
                f"{file_type}:{source}:{location_type}:{location}:{chunk_number}"
            )
            ids.append(hashlib.sha256(record_key.encode("utf-8")).hexdigest())
            documents.append(text_chunk)
            metadatas.append(
                {
                    "source": source,
                    "file_type": file_type,
                    "chunk_number": chunk_number,
                    location_type: location,
                }
            )
            added += 1
            if len(ids) >= BATCH_SIZE:
                save_batch()
        return added

    for csv_path in documents_by_type[".csv"]:
        source = str(csv_path.relative_to(PDF_DIR))
        try:
            with csv_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
                reader = csv.DictReader(csv_file)
                if not reader.fieldnames:
                    logger.warning("CSV has no header row; skipping %s", source)
                    continue

                file_chunks = 0
                for row_index, row in enumerate(reader, start=1):
                    text = "\n".join(
                        f"{key}: {value or ''}"
                        for key, value in row.items()
                        if key is not None
                    ).strip()
                    if text:
                        file_chunks += add_text(
                            source, text, "csv", "row_index", row_index
                        )
                indexed_chunks += file_chunks
                logger.info("Indexed %d chunks from CSV %s", file_chunks, source)
        except (OSError, UnicodeError, csv.Error):
            failures += 1
            logger.exception("Failed to process CSV %s", source)

    for markdown_path in documents_by_type[".md"]:
        source = str(markdown_path.relative_to(PDF_DIR))
        try:
            text = markdown_path.read_text(encoding="utf-8")
            file_chunks = (
                add_text(source, text, "markdown", "location", "document")
                if text.strip()
                else 0
            )
            indexed_chunks += file_chunks
            logger.info("Indexed %d chunks from Markdown %s", file_chunks, source)
        except (OSError, UnicodeError):
            failures += 1
            logger.exception("Failed to process Markdown %s", source)

    for pdf_path in documents_by_type[".pdf"]:
        source = str(pdf_path.relative_to(PDF_DIR))
        try:
            reader = PdfReader(str(pdf_path))
            file_chunks = 0
            for page_number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if not text.strip():
                    logger.warning(
                        "No extractable text in PDF %s page %d",
                        source,
                        page_number,
                    )
                    continue
                file_chunks += add_text(
                    source, text, "pdf", "page_number", page_number
                )
            indexed_chunks += file_chunks
            logger.info("Indexed %d chunks from PDF %s", file_chunks, source)
        except (OSError, PdfReadError):
            failures += 1
            logger.exception("Failed to process PDF %s", source)

    save_batch()
    logger.info(
        "Finished ingestion: indexed %d chunks; failed files: %d",
        indexed_chunks,
        failures,
    )


if __name__ == "__main__":
    main()
