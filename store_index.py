from src.helper import load_pdf_file, text_split, download_hugging_face_embeddings, validate_pdf_files
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv
from tqdm import tqdm
import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

def rebuild_index(data_dir="Data/"):
    """Rebuild FAISS index from PDFs in the specified directory."""
    try:
        logger.info(f"Starting index rebuild from {data_dir}")
        
        # Validate PDFs before processing
        logger.info("Validating PDF files...")
        valid_files, invalid_files = validate_pdf_files(data_dir)
        
        if invalid_files:
            logger.warning(f"Found {len(invalid_files)} invalid/problematic PDFs:")
            for file_path, reason in invalid_files:
                logger.warning(f"  - {file_path}: {reason}")
        
        if not valid_files:
            logger.error("No valid PDF files found to index!")
            return False
        
        logger.info(f"Processing {len(valid_files)} valid PDF files")
        
        # Load and process PDFs
        extracted_data = load_pdf_file(data=data_dir)
        if not extracted_data:
            logger.error("No data extracted from PDFs!")
            return False
            
        logger.info(f"Loaded {len(extracted_data)} pages from PDFs")
        
        # Split into chunks
        text_chunks = text_split(extracted_data)
        logger.info(f"Created {len(text_chunks)} text chunks")
        
        # Load embeddings model
        embeddings = download_hugging_face_embeddings()
        logger.info("Embeddings model loaded")
        
        # Build FAISS index in batches so we can show a progress bar.
        # Embedding all chunks in one shot is silent and looks frozen on large corpora.
        BATCH_SIZE = 50
        logger.info(f"Embedding {len(text_chunks)} chunks in batches of {BATCH_SIZE}…")

        first_batch = text_chunks[:BATCH_SIZE]
        docsearch = FAISS.from_documents(first_batch, embeddings)

        remaining = text_chunks[BATCH_SIZE:]
        if remaining:
            batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
            for batch in tqdm(batches, desc="Embedding batches", unit="batch"):
                batch_store = FAISS.from_documents(batch, embeddings)
                docsearch.merge_from(batch_store)

        # Save index
        docsearch.save_local("faiss_index")
        logger.info("FAISS index saved to faiss_index/")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during index rebuild: {str(e)}")
        return False

if __name__ == '__main__':
    success = rebuild_index()
    sys.exit(0 if success else 1)
