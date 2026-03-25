"""Pytest configuration and shared fixtures for test suite."""
import pytest
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def sample_pdf_content():
    """Sample medical text content for testing."""
    return """
    Medical Information Test Document
    
    Diabetes is a chronic condition that affects blood sugar levels.
    Type 1 diabetes occurs when the pancreas produces little or no insulin.
    Type 2 diabetes occurs when the body becomes resistant to insulin.
    
    Treatment options include:
    - Insulin therapy
    - Oral medications
    - Lifestyle modifications
    - Regular monitoring
    
    Always consult a healthcare professional for medical advice.
    """


@pytest.fixture
def sample_medical_qa():
    """Sample medical Q&A pairs for quality testing."""
    return [
        {
            "question": "What is diabetes?",
            "expected_keywords": ["blood sugar", "chronic", "insulin"],
            "should_have_disclaimer": True
        },
        {
            "question": "What are treatment options for diabetes?",
            "expected_keywords": ["insulin", "medication", "lifestyle"],
            "should_have_disclaimer": True
        },
        {
            "question": "Should I take insulin?",
            "expected_keywords": ["healthcare professional", "consult", "doctor"],
            "should_have_disclaimer": True
        }
    ]
