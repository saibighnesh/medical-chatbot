import logging
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from PyPDF2 import PdfReader
except ImportError:
    from pypdf import PdfReader

logger = logging.getLogger(__name__)


def validate_pdf_files(data_dir):
    """
    Validate PDF files before ingestion.

    Args:
        data_dir: Directory containing PDF files

    Returns:
        tuple: (list of valid file paths, list of (invalid file path, reason) tuples)
    """
    valid_files = []
    invalid_files = []

    pdf_files = list(Path(data_dir).glob("*.pdf"))

    if not pdf_files:
        logger.warning(f"No PDF files found in {data_dir}")
        return valid_files, invalid_files

    for pdf_path in pdf_files:
        try:
            # Check if file exists and is readable
            if not pdf_path.is_file():
                invalid_files.append((str(pdf_path), "File not found or not a file"))
                continue

            # Check file size (min 1KB, max 50MB)
            file_size = pdf_path.stat().st_size
            if file_size < 1024:
                invalid_files.append((str(pdf_path), f"File too small ({file_size} bytes)"))
                continue
            if file_size > 50 * 1024 * 1024:
                invalid_files.append((str(pdf_path), f"File too large ({file_size / (1024*1024):.2f} MB)"))
                continue

            # Try to read PDF and validate
            try:
                pdf_reader = PdfReader(str(pdf_path))
                num_pages = len(pdf_reader.pages)

                if num_pages == 0:
                    invalid_files.append((str(pdf_path), "PDF has no pages"))
                    continue

                # Try to extract text from first page to verify it works
                first_page_text = pdf_reader.pages[0].extract_text()
                if not first_page_text or len(first_page_text.strip()) == 0:
                    logger.warning(f"{pdf_path.name}: First page has no extractable text (might be image-based)")

                # File is valid
                valid_files.append(str(pdf_path))
                logger.info(f"✓ {pdf_path.name}: Valid ({num_pages} pages, {file_size / 1024:.2f} KB)")

            except Exception as e:
                invalid_files.append((str(pdf_path), f"PDF corruption or read error: {str(e)}"))
                continue

        except Exception as e:
            invalid_files.append((str(pdf_path), f"Unexpected error: {str(e)}"))
            continue

    return valid_files, invalid_files


def load_pdf_file(data):
    loader = DirectoryLoader(data, glob="*.pdf", loader_cls=PyPDFLoader)
    documents = loader.load()
    return documents


def text_split(extracted_data):
    # Optimized parameters based on evaluation:
    # - chunk_size=700: Better context completeness
    # - chunk_overlap=100: Ensures continuity between chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=700, chunk_overlap=100, length_function=len, separators=["\n\n", "\n", " ", ""]
    )
    text_chunks = text_splitter.split_documents(extracted_data)
    return text_chunks


def download_hugging_face_embeddings():
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    return embeddings
