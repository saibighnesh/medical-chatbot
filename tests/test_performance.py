"""Performance and load tests for medical chatbot."""
import pytest
import time
import os
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict
import statistics


# Skip performance tests if FAISS index doesn't exist
FAISS_INDEX_PATH = "faiss_index"
FAISS_EXISTS = os.path.exists(FAISS_INDEX_PATH)


class PerformanceMetrics:
    """Track and analyze performance metrics."""
    
    def __init__(self):
        self.response_times = []
        self.success_count = 0
        self.error_count = 0
    
    def add_result(self, response_time: float, success: bool):
        """Add a test result."""
        self.response_times.append(response_time)
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
    
    def get_statistics(self) -> Dict:
        """Get performance statistics."""
        if not self.response_times:
            return {}
        
        return {
            "min": min(self.response_times),
            "max": max(self.response_times),
            "mean": statistics.mean(self.response_times),
            "median": statistics.median(self.response_times),
            "stdev": statistics.stdev(self.response_times) if len(self.response_times) > 1 else 0,
            "p95": sorted(self.response_times)[int(len(self.response_times) * 0.95)],
            "p99": sorted(self.response_times)[int(len(self.response_times) * 0.99)],
            "total_requests": len(self.response_times),
            "success_rate": self.success_count / len(self.response_times) if self.response_times else 0
        }


@pytest.fixture
def performance_metrics():
    """Create performance metrics tracker."""
    return PerformanceMetrics()


class TestResponseTime:
    """Test response time performance."""
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_single_query_response_time(self):
        """Test response time for a single query is under 5 seconds."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})
        
        query = "What is diabetes?"
        
        start_time = time.time()
        docs = retriever.invoke(query)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        print(f"\nSingle query response time: {response_time:.3f}s")
        
        # Retrieval should be fast (under 2 seconds for FAISS)
        assert response_time < 2.0, f"Retrieval too slow: {response_time:.3f}s"
        assert len(docs) > 0
    
    def test_mock_rag_chain_response_time(self):
        """Test mock RAG chain response time."""
        with patch('app.rag_chain') as mock_chain:
            mock_chain.invoke.return_value = {
                "answer": "Test response about diabetes."
            }
            
            start_time = time.time()
            response = mock_chain.invoke({"input": "What is diabetes?"})
            end_time = time.time()
            
            response_time = end_time - start_time
            
            # Mock should be very fast
            assert response_time < 0.1, f"Mock response too slow: {response_time:.3f}s"
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_embedding_generation_time(self):
        """Test time to generate embeddings."""
        from src.helper import download_hugging_face_embeddings
        
        embeddings = download_hugging_face_embeddings()
        test_text = "What is diabetes and how is it treated?"
        
        start_time = time.time()
        embedding = embeddings.embed_query(test_text)
        end_time = time.time()
        
        embedding_time = end_time - start_time
        
        print(f"\nEmbedding generation time: {embedding_time:.3f}s")
        
        # Embedding should be fast (under 1 second)
        assert embedding_time < 1.0, f"Embedding generation too slow: {embedding_time:.3f}s"
        assert len(embedding) == 384
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_multiple_queries_average_response_time(self, performance_metrics):
        """Test average response time across multiple queries."""
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
            "What causes diabetes?",
            "Can it be prevented?"
        ]
        
        for query in queries:
            start_time = time.time()
            docs = retriever.invoke(query)
            end_time = time.time()
            
            response_time = end_time - start_time
            performance_metrics.add_result(response_time, len(docs) > 0)
        
        stats = performance_metrics.get_statistics()
        
        print(f"\nAverage response time: {stats['mean']:.3f}s")
        print(f"Median response time: {stats['median']:.3f}s")
        print(f"95th percentile: {stats['p95']:.3f}s")
        
        # Average should be under 2 seconds
        assert stats['mean'] < 2.0, f"Average response time too high: {stats['mean']:.3f}s"


class TestFAISSPerformance:
    """Test FAISS vector store performance."""
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_faiss_search_latency(self):
        """Test FAISS similarity search latency."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        
        # Generate embedding once
        query_embedding = embeddings.embed_query("diabetes treatment")
        
        # Test FAISS search time
        start_time = time.time()
        results = docsearch.similarity_search_by_vector(query_embedding, k=3)
        end_time = time.time()
        
        search_time = end_time - start_time
        
        print(f"\nFAISS search latency: {search_time:.4f}s")
        
        # FAISS search should be very fast (under 0.1 seconds)
        assert search_time < 0.1, f"FAISS search too slow: {search_time:.4f}s"
        assert len(results) > 0
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_faiss_batch_search_performance(self):
        """Test FAISS performance with batch searches."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        
        queries = [
            "diabetes", "treatment", "symptoms", "causes", "prevention",
            "insulin", "blood sugar", "medication", "diet", "exercise"
        ]
        
        total_time = 0
        for query in queries:
            start_time = time.time()
            results = docsearch.similarity_search(query, k=3)
            end_time = time.time()
            total_time += (end_time - start_time)
        
        avg_time = total_time / len(queries)
        
        print(f"\nAverage FAISS search time (10 queries): {avg_time:.4f}s")
        
        # Average should be fast
        assert avg_time < 0.5, f"Average FAISS search too slow: {avg_time:.4f}s"
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_faiss_load_time(self):
        """Test time to load FAISS index."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        
        start_time = time.time()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        end_time = time.time()
        
        load_time = end_time - start_time
        
        print(f"\nFAISS index load time: {load_time:.3f}s")
        
        # Load time should be reasonable (under 5 seconds)
        assert load_time < 5.0, f"FAISS load time too high: {load_time:.3f}s"


class TestConcurrentUsers:
    """Test performance with concurrent users."""
    
    def test_concurrent_api_requests_mock(self):
        """Test concurrent API requests with mocked components."""
        from flask import Flask
        
        with patch('app.rag_chain') as mock_chain:
            mock_chain.invoke.return_value = {
                "answer": "Test response"
            }
            
            # Import after mocking
            with patch('app.download_hugging_face_embeddings'), \
                 patch('app.FAISS'), \
                 patch('app.ChatGoogleGenerativeAI'):
                from app import app
                app.config['TESTING'] = True
                client = app.test_client()
            
            def make_request(query_id):
                """Make a single request."""
                start_time = time.time()
                response = client.post('/get', data={'msg': f'Query {query_id}'})
                end_time = time.time()
                return {
                    'query_id': query_id,
                    'status': response.status_code,
                    'time': end_time - start_time,
                    'success': response.status_code == 200
                }
            
            # Simulate 10 concurrent users
            num_users = 10
            
            with ThreadPoolExecutor(max_workers=num_users) as executor:
                futures = [executor.submit(make_request, i) for i in range(num_users)]
                results = [future.result() for future in as_completed(futures)]
            
            # Check results
            successful = sum(1 for r in results if r['success'])
            avg_time = sum(r['time'] for r in results) / len(results)
            max_time = max(r['time'] for r in results)
            
            print(f"\nConcurrent users: {num_users}")
            print(f"Success rate: {successful}/{num_users}")
            print(f"Average response time: {avg_time:.3f}s")
            print(f"Max response time: {max_time:.3f}s")
            
            # All requests should succeed
            assert successful == num_users, f"Only {successful}/{num_users} succeeded"
            
            # Average time should be reasonable
            assert avg_time < 1.0, f"Average response time too high: {avg_time:.3f}s"
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_concurrent_retrieval_operations(self):
        """Test concurrent retrieval operations."""
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
            "diabetes", "symptoms", "treatment", "causes", "prevention"
        ]
        
        def search_query(query):
            """Perform a search."""
            start_time = time.time()
            docs = retriever.invoke(query)
            end_time = time.time()
            return {
                'query': query,
                'time': end_time - start_time,
                'num_results': len(docs),
                'success': len(docs) > 0
            }
        
        # Run 5 concurrent searches
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(search_query, q) for q in queries]
            results = [future.result() for future in as_completed(futures)]
        
        # All searches should succeed
        successful = sum(1 for r in results if r['success'])
        avg_time = sum(r['time'] for r in results) / len(results)
        
        print(f"\nConcurrent searches: {len(queries)}")
        print(f"Success rate: {successful}/{len(queries)}")
        print(f"Average time: {avg_time:.3f}s")
        
        assert successful == len(queries), f"Only {successful}/{len(queries)} succeeded"
        assert avg_time < 2.0, f"Average time too high: {avg_time:.3f}s"
    
    def test_sustained_load_mock(self):
        """Test sustained load with mock components."""
        with patch('app.rag_chain') as mock_chain:
            mock_chain.invoke.return_value = {"answer": "Test"}
            
            with patch('app.download_hugging_face_embeddings'), \
                 patch('app.FAISS'), \
                 patch('app.ChatGoogleGenerativeAI'):
                from app import app
                app.config['TESTING'] = True
                client = app.test_client()
            
            num_requests = 50
            results = []
            
            start_time = time.time()
            for i in range(num_requests):
                req_start = time.time()
                response = client.post('/get', data={'msg': f'Query {i}'})
                req_end = time.time()
                
                results.append({
                    'success': response.status_code == 200,
                    'time': req_end - req_start
                })
            end_time = time.time()
            
            total_time = end_time - start_time
            throughput = num_requests / total_time
            success_rate = sum(1 for r in results if r['success']) / num_requests
            avg_response_time = sum(r['time'] for r in results) / num_requests
            
            print(f"\nSustained load test:")
            print(f"Total requests: {num_requests}")
            print(f"Total time: {total_time:.2f}s")
            print(f"Throughput: {throughput:.2f} req/s")
            print(f"Success rate: {success_rate:.2%}")
            print(f"Avg response time: {avg_response_time:.4f}s")
            
            assert success_rate >= 0.95, f"Success rate too low: {success_rate:.2%}"


class TestMemoryUsage:
    """Test memory efficiency."""
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_repeated_queries_no_memory_leak(self):
        """Test that repeated queries don't cause memory issues."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})
        
        # Run many queries
        for i in range(100):
            docs = retriever.invoke("diabetes")
            assert len(docs) > 0
        
        # If we get here without memory errors, test passes
        assert True
    
    def test_embedding_model_reuse(self):
        """Test that embedding model is reused efficiently."""
        from src.helper import download_hugging_face_embeddings
        
        # Load embeddings once
        embeddings = download_hugging_face_embeddings()
        
        # Use multiple times
        queries = ["diabetes", "treatment", "symptoms"] * 10
        
        start_time = time.time()
        for query in queries:
            embedding = embeddings.embed_query(query)
            assert len(embedding) == 384
        end_time = time.time()
        
        total_time = end_time - start_time
        avg_time = total_time / len(queries)
        
        print(f"\nAverage embedding time (30 queries): {avg_time:.4f}s")
        
        # Should be efficient with model reuse
        assert avg_time < 0.5, f"Embedding time too high: {avg_time:.4f}s"


class TestScalability:
    """Test scalability with varying loads."""
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_increasing_k_values_performance(self):
        """Test performance with increasing k values."""
        from src.helper import download_hugging_face_embeddings
        from langchain_community.vectorstores import FAISS
        
        embeddings = download_hugging_face_embeddings()
        docsearch = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        
        query = "diabetes treatment"
        k_values = [1, 3, 5, 10, 20]
        
        for k in k_values:
            start_time = time.time()
            results = docsearch.similarity_search(query, k=k)
            end_time = time.time()
            
            search_time = end_time - start_time
            
            print(f"k={k}: {search_time:.4f}s, {len(results)} results")
            
            # Time should scale reasonably with k
            assert search_time < 0.5, f"Search with k={k} too slow: {search_time:.4f}s"
    
    @pytest.mark.skipif(not FAISS_EXISTS, reason="FAISS index not found")
    def test_varying_query_lengths(self):
        """Test performance with varying query lengths."""
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
            "diabetes",  # Short
            "What is diabetes treatment?",  # Medium
            "What are the symptoms and treatment options for diabetes mellitus?",  # Long
            "Can you explain in detail what diabetes is, what causes it, and how it should be treated?"  # Very long
        ]
        
        for query in queries:
            start_time = time.time()
            docs = retriever.invoke(query)
            end_time = time.time()
            
            response_time = end_time - start_time
            
            print(f"Query length {len(query)}: {response_time:.3f}s")
            
            assert response_time < 2.0, f"Query too slow: {response_time:.3f}s"
            assert len(docs) > 0


class TestPerformanceBenchmarks:
    """Performance benchmark tests."""
    
    def test_performance_summary(self, performance_metrics):
        """Run comprehensive performance test and generate summary."""
        with patch('app.rag_chain') as mock_chain:
            mock_chain.invoke.return_value = {"answer": "Test response"}
            
            with patch('app.download_hugging_face_embeddings'), \
                 patch('app.FAISS'), \
                 patch('app.ChatGoogleGenerativeAI'):
                from app import app
                app.config['TESTING'] = True
                client = app.test_client()
            
            # Run varied test scenarios
            test_scenarios = [
                ("Short query", "diabetes"),
                ("Medium query", "What is diabetes?"),
                ("Long query", "What are the symptoms and treatment for diabetes?"),
                ("Medical advice", "Should I take insulin?"),
                ("General info", "Tell me about diabetes")
            ]
            
            for scenario_name, query in test_scenarios:
                start_time = time.time()
                response = client.post('/get', data={'msg': query})
                end_time = time.time()
                
                response_time = end_time - start_time
                success = response.status_code == 200
                
                performance_metrics.add_result(response_time, success)
            
            stats = performance_metrics.get_statistics()
            
            print("\n" + "="*50)
            print("PERFORMANCE BENCHMARK SUMMARY")
            print("="*50)
            print(f"Total Requests: {stats['total_requests']}")
            print(f"Success Rate: {stats['success_rate']:.2%}")
            print(f"Mean Response Time: {stats['mean']:.3f}s")
            print(f"Median Response Time: {stats['median']:.3f}s")
            print(f"Min Response Time: {stats['min']:.3f}s")
            print(f"Max Response Time: {stats['max']:.3f}s")
            print(f"95th Percentile: {stats['p95']:.3f}s")
            print(f"99th Percentile: {stats['p99']:.3f}s")
            print("="*50)
            
            # Performance criteria
            assert stats['success_rate'] >= 0.95
            assert stats['p95'] < 5.0  # 95% of requests under 5 seconds
