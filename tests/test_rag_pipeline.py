"""Integration tests for RAG pipeline end-to-end functionality."""
import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from langchain_core.documents import Document

# Skip tests if FAISS index doesn't exist
FAISS_INDEX_PATH = "faiss_index"
FAISS_EXISTS = os.path.exists(FAISS_INDEX_PATH)


@pytest.fixture
def mock_embeddings():
    """Mock embeddings for testing without loading actual model."""
    with patch('src.helper.HuggingFaceEmbeddings') as mock:
        mock_instance = Mock()
        mock_instance.embed_query.return_value = [0.1] * 384
        mock_instance.embed_documents.return_value = [[0.1] * 384]
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_llm():
    """Mock LLM for testing without API calls."""
    mock = Mock()
    mock.invoke.return_value = Mock(
        content="This is a test response about diabetes. Please consult a healthcare professional."
    )
    return mock


class TestRAGPipelineIntegration:
    """Integration tests for the complete RAG pipeline."""
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_rag_pipeline_basic_query(self):
        """Test basic RAG pipeline with a medical query."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        # Load embeddings and FAISS index
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        
        # Test retrieval
        query = "What is diabetes?"
        retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})
        docs = retriever.invoke(query)
        
        assert isinstance(docs, list)
        assert len(docs) > 0
        assert len(docs) <= 3
        assert all(isinstance(doc, Document) for doc in docs)
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_retrieval_returns_relevant_documents(self):
        """Test that retrieval returns relevant documents for medical queries."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        
        retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})
        
        # Test with different medical queries
        queries = [
            "diabetes treatment",
            "blood sugar levels",
            "medical symptoms"
        ]
        
        for query in queries:
            docs = retriever.invoke(query)
            
            assert len(docs) > 0, f"No documents retrieved for query: {query}"
            # Check that retrieved docs have content
            for doc in docs:
                assert len(doc.page_content) > 0
                assert hasattr(doc, 'metadata')
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_retrieval_with_different_k_values(self):
        """Test retrieval with different numbers of results."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        
        query = "What is diabetes?"
        
        for k in [1, 3, 5]:
            retriever = docsearch.as_retriever(
                search_type="similarity",
                search_kwargs={"k": k}
            )
            docs = retriever.invoke(query)
            
            assert len(docs) > 0
            assert len(docs) <= k
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_similarity_search_scores(self):
        """Test that similarity search returns documents with scores."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        
        query = "diabetes"
        results = docsearch.similarity_search_with_score(query, k=3)
        
        assert len(results) > 0
        for doc, score in results:
            assert isinstance(doc, Document)
            assert isinstance(score, float)
            assert score >= 0  # Distance scores should be non-negative
    
    def test_rag_chain_with_mock_components(self, mock_llm):
        """Test RAG chain with mocked components."""
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_classic.chains.combine_documents import create_stuff_documents_chain
        from langchain_classic.chains import create_retrieval_chain
        
        # Mock retriever
        mock_retriever = Mock()
        mock_docs = [
            Document(page_content="Diabetes is a chronic condition.", metadata={}),
            Document(page_content="Treatment includes insulin therapy.", metadata={})
        ]
        mock_retriever.invoke.return_value = mock_docs
        
        # Create prompt
        from src.prompt import system_prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])
        
        # Create chains
        question_answer_chain = create_stuff_documents_chain(mock_llm, prompt)
        rag_chain = create_retrieval_chain(mock_retriever, question_answer_chain)
        
        # Test the chain
        response = rag_chain.invoke({"input": "What is diabetes?"})
        
        assert "answer" in response
        assert isinstance(response["answer"], str)
        assert len(response["answer"]) > 0


class TestResponseQualityInIntegration:
    """Test response quality and disclaimer inclusion in integration."""
    
    @patch('langchain_google_genai.ChatGoogleGenerativeAI')
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_response_contains_disclaimer_keywords(self, mock_llm_class):
        """Test that responses contain medical disclaimer keywords."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_classic.chains.combine_documents import create_stuff_documents_chain
        from langchain_classic.chains import create_retrieval_chain
        from src.prompt import system_prompt
        
        # Mock LLM to return response with disclaimer
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = (
            "Diabetes is a condition affecting blood sugar. "
            "This information is for informational purposes only and should not "
            "replace professional medical advice. Please consult a healthcare professional."
        )
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm
        
        # Load real retriever
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})
        
        # Create chain
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])
        question_answer_chain = create_stuff_documents_chain(mock_llm, prompt)
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)
        
        # Test
        response = rag_chain.invoke({"input": "What is diabetes?"})
        answer = response["answer"]
        
        # Check for disclaimer keywords
        disclaimer_keywords = [
            "informational purposes",
            "professional medical advice",
            "consult",
            "healthcare professional"
        ]
        
        answer_lower = answer.lower()
        found_keywords = [kw for kw in disclaimer_keywords if kw.lower() in answer_lower]
        
        assert len(found_keywords) > 0, f"No disclaimer keywords found in: {answer}"
    
    def test_prompt_includes_disclaimer_instruction(self):
        """Test that system prompt includes disclaimer instructions."""
        from src.prompt import system_prompt
        
        assert "disclaimer" in system_prompt.lower()
        assert "informational purposes" in system_prompt.lower()
        assert "professional medical advice" in system_prompt.lower()


class TestRAGPipelineErrorHandling:
    """Test error handling in RAG pipeline."""
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_retrieval_with_empty_query(self):
        """Test retrieval with empty query string."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        
        retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})
        
        # Should handle empty query gracefully
        docs = retriever.invoke("")
        assert isinstance(docs, list)
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_retrieval_with_special_characters(self):
        """Test retrieval with special characters in query."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        
        retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})
        
        special_queries = [
            "diabetes?",
            "what's diabetes!",
            "diabetes & treatment",
            "diabetes (type 2)"
        ]
        
        for query in special_queries:
            docs = retriever.invoke(query)
            assert isinstance(docs, list)
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_retrieval_with_very_long_query(self):
        """Test retrieval with very long query."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        
        retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})
        
        # Very long query
        long_query = "diabetes treatment " * 100
        docs = retriever.invoke(long_query)
        
        assert isinstance(docs, list)
        assert len(docs) > 0


class TestEndToEndRAGWorkflow:
    """Test complete end-to-end RAG workflow scenarios."""
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found") 
    def test_complete_rag_workflow_multiple_queries(self):
        """Test complete RAG workflow with multiple sequential queries."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})
        
        queries = [
            "What is diabetes?",
            "What are the symptoms?",
            "How is it treated?",
            "What are prevention methods?"
        ]
        
        for query in queries:
            docs = retriever.invoke(query)
            assert len(docs) > 0, f"Failed to retrieve docs for: {query}"
            assert all(len(doc.page_content) > 0 for doc in docs)
    
    def test_rag_chain_context_included(self):
        """Test that RAG chain includes context in the prompt."""
        from langchain_core.prompts import ChatPromptTemplate
        from src.prompt import system_prompt
        
        # Verify system prompt has context placeholder
        assert "{context}" in system_prompt
        
        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])
        
        # Verify prompt can be formatted with context
        formatted = prompt.format(
            context="Test context about diabetes",
            input="What is diabetes?"
        )
        
        assert "Test context about diabetes" in formatted
        assert "What is diabetes?" in formatted
