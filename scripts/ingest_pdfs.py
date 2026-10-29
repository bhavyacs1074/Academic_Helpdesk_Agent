from pathlib import Path
import hashlib
import logging 

import chromadb
from pypdf import PdfReader 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "raw"
DB_DIR = ROOT / "chroma_db"
BATCH_SIZE = 100

client = chromadb.PersistentClient(path=str(DB_DIR))
collection = client.get_or_create_collection("pdfs")


def chunks(text : str , size : int = 250 , overlap : int = 50):
    """Yield successive chunks of text with overlap."""
    words = text.split()
    step = size - overlap
    return [" ".join(words[i:i + size]) for i in range(0, len(words), step)]

def main() -> None:
    if not PDF_DIR.exists():
        raise SystemExit(f"PDF directory {PDF_DIR} does not exist.")
    pdfs = sorted(
        path for path in PDF_DIR.rglob("*") if path.is_file() and path.suffix().lower() == ".pdf"
    )

    if not pdfs:
        raise SystemExit(f"No PDF files found in {PDF_DIR}.")

    ids: list[str] = []
    documents : list[str] = []
    metadatas : list[dict[str,str | int ]] = []
    failure = 0


    def save_batch():
        if ids:
            collection.add(
                
            )