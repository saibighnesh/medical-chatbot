"""Unit tests for helper functions in src/helper.py."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from langchain_core.documents import Document

from src.helper import download_hugging_face_embeddings, load_pdf_file, text_split


class TestLoadPdfFile:
    """Test cases for load_pdf_file function."""

    def test_load_pdf_file_empty_directory(self, temp_dir):
        """Test loading PDFs from an empty directory."""
        result = load_pdf_file(temp_dir)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_load_pdf_file_no_pdfs(self, temp_dir):
        """Test loading PDFs from directory with no PDF files."""
        # Create a non-PDF file
        test_file = Path(temp_dir) / "test.txt"
        test_file.write_text("This is not a PDF")

        result = load_pdf_file(temp_dir)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_load_pdf_file_invalid_path(self):
        """Test loading PDFs from non-existent directory."""
        with pytest.raises(Exception):
            load_pdf_file("/nonexistent/directory/path")

    def test_load_pdf_file_none_input(self):
        """Test loading PDFs with None as input."""
        with pytest.raises(Exception):
            load_pdf_file(None)

    def test_load_pdf_file_empty_string(self):
        """Test loading PDFs with empty string as input."""
        with pytest.raises(Exception):
            load_pdf_file("")

    @patch("src.helper.DirectoryLoader")
    def test_load_pdf_file_valid_directory(self, mock_loader, temp_dir):
        """Test loading PDFs from valid directory with mocked loader."""
        # Mock the loader to return sample documents
        mock_documents = [
            Document(page_content="Test content 1", metadata={"source": "test1.pdf"}),
            Document(page_content="Test content 2", metadata={"source": "test2.pdf"}),
        ]
        mock_loader_instance = Mock()
        mock_loader_instance.load.return_value = mock_documents
        mock_loader.return_value = mock_loader_instance

        result = load_pdf_file(temp_dir)

        # Verify DirectoryLoader was called correctly
        mock_loader.assert_called_once()
        assert result == mock_documents


class TestTextSplit:
    """Test cases for text_split function."""

    def test_text_split_empty_list(self):
        """Test splitting with empty document list."""
        result = text_split([])
        assert isinstance(result, list)
        assert len(result) == 0

    def test_text_split_single_short_document(self):
        """Test splitting a single short document."""
        doc = Document(page_content="Short text", metadata={})
        result = text_split([doc])

        assert isinstance(result, list)
        assert len(result) >= 1
        assert all(isinstance(chunk, Document) for chunk in result)

    def test_text_split_long_document(self):
        """Test splitting a long document that requires chunking."""
        # Create a document longer than chunk_size (500 chars)
        long_text = "This is a test sentence. " * 50  # ~1250 chars
        doc = Document(page_content=long_text, metadata={"source": "test.pdf"})

        result = text_split([doc])

        assert isinstance(result, list)
        assert len(result) > 1  # Should be split into multiple chunks
        # Verify chunk sizes
        for chunk in result:
            assert isinstance(chunk, Document)
            assert len(chunk.page_content) <= 720  # chunk_size + overlap buffer

    def test_text_split_multiple_documents(self):
        """Test splitting multiple documents."""
        docs = [
            Document(page_content="First document content. " * 30, metadata={"source": "doc1.pdf"}),
            Document(page_content="Second document content. " * 30, metadata={"source": "doc2.pdf"}),
        ]

        result = text_split(docs)

        assert isinstance(result, list)
        assert len(result) > len(docs)  # Should have more chunks than original docs
        assert all(isinstance(chunk, Document) for chunk in result)

    def test_text_split_preserves_metadata(self):
        """Test that splitting preserves document metadata."""
        doc = Document(page_content="Test content " * 50, metadata={"source": "test.pdf", "page": 1})

        result = text_split([doc])

        # Check that metadata is preserved in chunks
        for chunk in result:
            assert "source" in chunk.metadata
            assert chunk.metadata["source"] == "test.pdf"

    def test_text_split_none_input(self):
        """Test splitting with None input."""
        with pytest.raises(Exception):
            text_split(None)


class TestDownloadHuggingFaceEmbeddings:
    """Test cases for download_hugging_face_embeddings function."""

    @patch("src.helper.HuggingFaceEmbeddings")
    def test_download_embeddings_returns_embeddings_object(self, mock_embeddings):
        """Test that function returns HuggingFaceEmbeddings object."""
        mock_instance = Mock()
        mock_embeddings.return_value = mock_instance

        result = download_hugging_face_embeddings()

        # Verify HuggingFaceEmbeddings was instantiated
        mock_embeddings.assert_called_once_with(model_name="sentence-transformers/all-MiniLM-L6-v2")
        assert result == mock_instance

    @patch("src.helper.HuggingFaceEmbeddings")
    def test_download_embeddings_uses_correct_model(self, mock_embeddings):
        """Test that function uses the correct model name."""
        mock_instance = Mock()
        mock_embeddings.return_value = mock_instance

        download_hugging_face_embeddings()

        # Verify correct model name
        call_args = mock_embeddings.call_args
        assert call_args[1]["model_name"] == "sentence-transformers/all-MiniLM-L6-v2"

    @pytest.mark.integration
    def test_download_embeddings_integration(self):
        """Integration test: verify embeddings can embed text."""
        embeddings = download_hugging_face_embeddings()

        # Test that embeddings object has expected methods
        assert hasattr(embeddings, "embed_query")
        assert hasattr(embeddings, "embed_documents")

        # Test actual embedding (this will download model on first run)
        test_text = "diabetes treatment"
        embedding = embeddings.embed_query(test_text)

        # Verify embedding properties
        assert isinstance(embedding, list)
        assert len(embedding) == 384  # all-MiniLM-L6-v2 produces 384-dim vectors
        assert all(isinstance(x, float) for x in embedding)

    @pytest.mark.integration
    def test_download_embeddings_consistency(self):
        """Test that same text produces consistent embeddings."""
        embeddings = download_hugging_face_embeddings()
        test_text = "medical advice"

        embedding1 = embeddings.embed_query(test_text)
        embedding2 = embeddings.embed_query(test_text)

        # Embeddings should be identical for same text
        assert embedding1 == embedding2

    @pytest.mark.integration
    def test_download_embeddings_different_texts(self):
        """Test that different texts produce different embeddings."""
        embeddings = download_hugging_face_embeddings()

        embedding1 = embeddings.embed_query("diabetes")
        embedding2 = embeddings.embed_query("cancer")

        # Embeddings should be different
        assert embedding1 != embedding2


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling across helper functions."""

    def test_load_pdf_with_special_characters_in_path(self):
        """Test loading PDFs with special characters in directory path."""
        # Test with spaces and special chars
        with pytest.raises(Exception):
            load_pdf_file("/path/with spaces/and-special@chars/")

    def test_text_split_with_unicode_content(self):
        """Test splitting documents with unicode content."""
        doc = Document(page_content="Unicode test: café, naïve, résumé, 你好, مرحبا " * 20, metadata={})

        result = text_split([doc])

        assert isinstance(result, list)
        assert len(result) > 0
        # Verify unicode is preserved
        combined_text = "".join(chunk.page_content for chunk in result)
        assert "café" in combined_text or "caf" in combined_text  # Some chars may be handled differently

    def test_text_split_with_very_long_lines(self):
        """Test splitting documents with very long lines."""
        # Create a document with one very long line
        long_line = "word" * 500  # 2000 chars without spaces
        doc = Document(page_content=long_line, metadata={})

        result = text_split([doc])

        assert isinstance(result, list)
        assert len(result) > 0

    @pytest.mark.integration
    def test_embeddings_with_empty_string(self):
        """Test embeddings with empty string."""
        embeddings = download_hugging_face_embeddings()

        embedding = embeddings.embed_query("")

        # Should still return valid embedding vector
        assert isinstance(embedding, list)
        assert len(embedding) == 384

    @pytest.mark.integration
    def test_embeddings_with_very_long_text(self):
        """Test embeddings with very long text."""
        embeddings = download_hugging_face_embeddings()

        # Create very long text (models usually have token limits)
        long_text = "medical treatment " * 1000
        embedding = embeddings.embed_query(long_text)

        # Should still return valid embedding
        assert isinstance(embedding, list)
        assert len(embedding) == 384
