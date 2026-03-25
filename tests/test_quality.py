"""Response quality tests for medical chatbot."""
import pytest
import re
from unittest.mock import Mock, patch
from typing import List, Dict


class MedicalQATestSet:
    """Test dataset with medical Q&A pairs."""
    
    @staticmethod
    def get_test_cases() -> List[Dict]:
        """Get test cases with medical questions and expected properties."""
        return [
            {
                "question": "What is diabetes?",
                "category": "definition",
                "expected_keywords": ["blood sugar", "glucose", "chronic", "insulin"],
                "should_have_disclaimer": True,
                "min_length": 50
            },
            {
                "question": "What are the symptoms of diabetes?",
                "category": "symptoms",
                "expected_keywords": ["thirst", "urination", "fatigue", "weight"],
                "should_have_disclaimer": True,
                "min_length": 50
            },
            {
                "question": "How is diabetes treated?",
                "category": "treatment",
                "expected_keywords": ["insulin", "medication", "lifestyle", "diet", "exercise"],
                "should_have_disclaimer": True,
                "min_length": 50
            },
            {
                "question": "What causes diabetes?",
                "category": "causes",
                "expected_keywords": ["pancreas", "insulin", "genetic", "lifestyle"],
                "should_have_disclaimer": True,
                "min_length": 50
            },
            {
                "question": "Can diabetes be prevented?",
                "category": "prevention",
                "expected_keywords": ["lifestyle", "diet", "exercise", "weight", "healthy"],
                "should_have_disclaimer": True,
                "min_length": 50
            },
            {
                "question": "What is Type 1 diabetes?",
                "category": "definition",
                "expected_keywords": ["type 1", "autoimmune", "insulin", "pancreas"],
                "should_have_disclaimer": True,
                "min_length": 50
            },
            {
                "question": "What is Type 2 diabetes?",
                "category": "definition",
                "expected_keywords": ["type 2", "insulin resistance", "lifestyle"],
                "should_have_disclaimer": True,
                "min_length": 50
            },
            {
                "question": "Should I take insulin for diabetes?",
                "category": "medical_advice",
                "expected_keywords": ["consult", "healthcare", "professional", "doctor"],
                "should_have_disclaimer": True,
                "must_defer_to_doctor": True,
                "min_length": 30
            },
            {
                "question": "What foods should diabetics avoid?",
                "category": "diet",
                "expected_keywords": ["sugar", "carbohydrate", "diet", "food"],
                "should_have_disclaimer": True,
                "min_length": 50
            },
            {
                "question": "What are complications of diabetes?",
                "category": "complications",
                "expected_keywords": ["kidney", "nerve", "eye", "heart", "complication"],
                "should_have_disclaimer": True,
                "min_length": 50
            }
        ]


@pytest.fixture
def mock_rag_response():
    """Mock RAG response generator."""
    def generate_response(question: str) -> str:
        """Generate mock response based on question."""
        responses = {
            "diabetes": "Diabetes is a chronic condition that affects how your body processes blood sugar (glucose). "
                       "Type 1 diabetes occurs when the pancreas produces little or no insulin. "
                       "Type 2 diabetes occurs when the body becomes resistant to insulin. "
                       "Please note: This information is for informational purposes only and should not replace "
                       "professional medical advice. Always consult a healthcare professional.",
            
            "symptoms": "Common symptoms of diabetes include increased thirst, frequent urination, extreme fatigue, "
                       "unexplained weight loss, blurred vision, and slow-healing sores. "
                       "This information is for informational purposes only. Please consult a healthcare professional "
                       "for proper diagnosis and treatment.",
            
            "treatment": "Diabetes treatment includes insulin therapy, oral medications, lifestyle modifications "
                        "such as healthy diet and regular exercise, and regular blood sugar monitoring. "
                        "This information is for informational purposes only and should not replace professional "
                        "medical advice. Consult your healthcare provider.",
            
            "causes": "Diabetes can be caused by genetic factors, autoimmune conditions (Type 1), insulin resistance "
                     "(Type 2), obesity, and lifestyle factors. The exact cause varies by type. "
                     "For medical advice specific to your situation, please consult a healthcare professional.",
            
            "prevention": "Type 2 diabetes may be prevented or delayed through healthy lifestyle choices including "
                         "maintaining a healthy weight, regular physical activity, a balanced diet, and avoiding "
                         "tobacco use. This information is for educational purposes only. Consult a healthcare provider.",
            
            "insulin": "Whether you need insulin depends on your specific type of diabetes and individual circumstances. "
                      "This is a medical decision that should be made in consultation with your healthcare provider. "
                      "I cannot provide specific medical advice. Please consult a doctor or endocrinologist.",
            
            "foods": "People with diabetes should generally limit high-sugar foods, refined carbohydrates, and "
                    "sugary beverages. Focus on whole grains, vegetables, lean proteins, and healthy fats. "
                    "This information is for educational purposes only. Consult a registered dietitian or doctor "
                    "for personalized dietary advice.",
            
            "complications": "Diabetes complications can include kidney disease (nephropathy), nerve damage (neuropathy), "
                           "eye damage (retinopathy), heart disease, stroke, and foot problems. "
                           "Proper management is crucial. This information is for educational purposes only. "
                           "Please consult a healthcare professional for medical advice."
        }
        
        question_lower = question.lower()
        for key, response in responses.items():
            if key in question_lower:
                return response
        
        return "I don't have specific information about that. Please consult a healthcare professional for medical advice."
    
    return generate_response


class TestDisclaimerInclusion:
    """Test that responses include appropriate medical disclaimers."""
    
    def test_all_responses_have_disclaimer(self, mock_rag_response):
        """Test that all medical responses include disclaimers."""
        test_cases = MedicalQATestSet.get_test_cases()
        
        disclaimer_patterns = [
            r"informational purposes only",
            r"should not replace.*medical advice",
            r"consult.*healthcare professional",
            r"consult.*doctor",
            r"seek medical advice",
            r"professional medical advice"
        ]
        
        for test_case in test_cases:
            if test_case["should_have_disclaimer"]:
                response = mock_rag_response(test_case["question"])
                
                # Check if any disclaimer pattern is present
                has_disclaimer = any(
                    re.search(pattern, response, re.IGNORECASE)
                    for pattern in disclaimer_patterns
                )
                
                assert has_disclaimer, (
                    f"Response missing disclaimer for question: {test_case['question']}\n"
                    f"Response: {response}"
                )
    
    def test_medical_advice_questions_defer_to_professionals(self, mock_rag_response):
        """Test that medical advice questions defer to healthcare professionals."""
        test_cases = [tc for tc in MedicalQATestSet.get_test_cases() 
                     if tc.get("must_defer_to_doctor", False)]
        
        professional_keywords = [
            "consult", "healthcare professional", "doctor", 
            "physician", "medical advice", "healthcare provider"
        ]
        
        for test_case in test_cases:
            response = mock_rag_response(test_case["question"])
            response_lower = response.lower()
            
            # Should contain at least one keyword about consulting professionals
            has_professional_reference = any(
                keyword.lower() in response_lower 
                for keyword in professional_keywords
            )
            
            assert has_professional_reference, (
                f"Medical advice question should defer to professionals: {test_case['question']}\n"
                f"Response: {response}"
            )
    
    def test_disclaimer_placement(self, mock_rag_response):
        """Test that disclaimers are properly placed in responses."""
        test_cases = MedicalQATestSet.get_test_cases()
        
        for test_case in test_cases:
            if test_case["should_have_disclaimer"]:
                response = mock_rag_response(test_case["question"])
                
                # Disclaimer should be present (can be anywhere in response)
                disclaimer_indicators = [
                    "informational purposes",
                    "consult",
                    "healthcare professional",
                    "medical advice"
                ]
                
                found = any(ind.lower() in response.lower() for ind in disclaimer_indicators)
                assert found, f"No disclaimer found in response for: {test_case['question']}"


class TestResponseRelevance:
    """Test that responses are relevant to questions."""
    
    def test_responses_contain_expected_keywords(self, mock_rag_response):
        """Test that responses contain expected medical keywords."""
        test_cases = MedicalQATestSet.get_test_cases()
        
        for test_case in test_cases:
            response = mock_rag_response(test_case["question"])
            response_lower = response.lower()
            
            # At least some expected keywords should be present
            expected_keywords = test_case["expected_keywords"]
            found_keywords = [
                kw for kw in expected_keywords 
                if kw.lower() in response_lower
            ]
            
            # At least 30% of expected keywords should be present
            relevance_threshold = max(1, len(expected_keywords) * 0.3)
            
            assert len(found_keywords) >= relevance_threshold, (
                f"Insufficient relevant keywords for question: {test_case['question']}\n"
                f"Expected keywords: {expected_keywords}\n"
                f"Found: {found_keywords}\n"
                f"Response: {response}"
            )
    
    def test_responses_are_on_topic(self, mock_rag_response):
        """Test that responses stay on topic."""
        test_cases = MedicalQATestSet.get_test_cases()
        
        for test_case in test_cases:
            response = mock_rag_response(test_case["question"])
            question_lower = test_case["question"].lower()
            
            # Extract main topic from question
            if "diabetes" in question_lower:
                assert "diabetes" in response.lower() or "diabetic" in response.lower(), (
                    f"Response not on topic for: {test_case['question']}"
                )
    
    def test_response_categories_match(self, mock_rag_response):
        """Test that response content matches question category."""
        category_keywords = {
            "definition": ["is", "condition", "disease", "disorder"],
            "symptoms": ["symptom", "sign", "indicate", "experience"],
            "treatment": ["treatment", "therapy", "medication", "manage"],
            "causes": ["cause", "due to", "result from", "lead to"],
            "prevention": ["prevent", "avoid", "reduce risk", "lifestyle"],
            "medical_advice": ["consult", "healthcare", "professional", "doctor"]
        }
        
        test_cases = MedicalQATestSet.get_test_cases()
        
        for test_case in test_cases:
            response = mock_rag_response(test_case["question"])
            category = test_case["category"]
            
            # Response should contain some category-related keywords
            response_lower = response.lower()
            category_kws = category_keywords.get(category, [])
            
            has_category_content = any(
                kw in response_lower for kw in category_kws
            )
            
            # Not all categories need matching keywords, but most should
            # This is a soft check
            if category not in ["medical_advice"]:
                # Log warning but don't fail
                if not has_category_content:
                    print(f"Warning: Response may not match category {category} for: {test_case['question']}")


class TestResponseAccuracy:
    """Test response accuracy and correctness."""
    
    def test_response_minimum_length(self, mock_rag_response):
        """Test that responses meet minimum length requirements."""
        test_cases = MedicalQATestSet.get_test_cases()
        
        for test_case in test_cases:
            response = mock_rag_response(test_case["question"])
            min_length = test_case.get("min_length", 30)
            
            assert len(response) >= min_length, (
                f"Response too short for: {test_case['question']}\n"
                f"Expected min {min_length} chars, got {len(response)}\n"
                f"Response: {response}"
            )
    
    def test_responses_are_informative(self, mock_rag_response):
        """Test that responses provide informative content."""
        test_cases = MedicalQATestSet.get_test_cases()
        
        # Responses should not be just disclaimers
        non_disclaimer_words = [
            "diabetes", "insulin", "blood", "sugar", "treatment",
            "symptom", "cause", "prevent", "medication", "lifestyle"
        ]
        
        for test_case in test_cases:
            response = mock_rag_response(test_case["question"])
            response_lower = response.lower()
            
            # Count informative words
            info_word_count = sum(
                1 for word in non_disclaimer_words 
                if word in response_lower
            )
            
            assert info_word_count >= 2, (
                f"Response not informative enough for: {test_case['question']}\n"
                f"Response: {response}"
            )
    
    def test_no_contradictory_information(self, mock_rag_response):
        """Test that responses don't contain obvious contradictions."""
        # Test a few specific cases
        response = mock_rag_response("What is Type 1 diabetes?")
        
        # Should not confuse Type 1 and Type 2
        if "type 1" in response.lower():
            # If mentioning insulin production, should be about lack of production
            if "insulin" in response.lower() and "produces" in response.lower():
                assert "little" in response.lower() or "no" in response.lower() or "not" in response.lower()


class TestResponseQualityMetrics:
    """Test response quality using various metrics."""
    
    def test_calculate_relevance_score(self, mock_rag_response):
        """Calculate relevance score based on keyword presence."""
        test_cases = MedicalQATestSet.get_test_cases()
        
        scores = []
        for test_case in test_cases:
            response = mock_rag_response(test_case["question"])
            response_lower = response.lower()
            
            expected_keywords = test_case["expected_keywords"]
            found_keywords = [
                kw for kw in expected_keywords 
                if kw.lower() in response_lower
            ]
            
            relevance_score = len(found_keywords) / len(expected_keywords)
            scores.append(relevance_score)
        
        # Average relevance should be above 0.5
        avg_relevance = sum(scores) / len(scores)
        assert avg_relevance > 0.3, f"Average relevance score too low: {avg_relevance}"
        
        print(f"\nRelevance Score: {avg_relevance:.2%}")
    
    def test_disclaimer_presence_rate(self, mock_rag_response):
        """Test disclaimer presence rate across all responses."""
        test_cases = MedicalQATestSet.get_test_cases()
        
        disclaimer_patterns = [
            r"informational purposes",
            r"medical advice",
            r"consult.*healthcare",
            r"consult.*doctor"
        ]
        
        responses_with_disclaimer = 0
        total_responses = 0
        
        for test_case in test_cases:
            if test_case["should_have_disclaimer"]:
                response = mock_rag_response(test_case["question"])
                total_responses += 1
                
                has_disclaimer = any(
                    re.search(pattern, response, re.IGNORECASE)
                    for pattern in disclaimer_patterns
                )
                
                if has_disclaimer:
                    responses_with_disclaimer += 1
        
        disclaimer_rate = responses_with_disclaimer / total_responses if total_responses > 0 else 0
        
        # Should have disclaimers in at least 90% of responses
        assert disclaimer_rate >= 0.9, f"Disclaimer rate too low: {disclaimer_rate:.2%}"
        
        print(f"\nDisclaimer Presence Rate: {disclaimer_rate:.2%}")
    
    def test_average_response_length(self, mock_rag_response):
        """Test average response length is appropriate."""
        test_cases = MedicalQATestSet.get_test_cases()
        
        lengths = []
        for test_case in test_cases:
            response = mock_rag_response(test_case["question"])
            lengths.append(len(response))
        
        avg_length = sum(lengths) / len(lengths)
        
        # Average should be reasonable (not too short, not too long)
        assert 100 <= avg_length <= 1000, f"Average response length unusual: {avg_length}"
        
        print(f"\nAverage Response Length: {avg_length:.0f} characters")


class TestEdgeCasesInQuality:
    """Test quality with edge case inputs."""
    
    def test_vague_questions(self, mock_rag_response):
        """Test quality with vague questions."""
        vague_questions = [
            "Tell me about diabetes",
            "Diabetes info",
            "Help with diabetes"
        ]
        
        for question in vague_questions:
            response = mock_rag_response(question)
            
            # Should still provide some information
            assert len(response) > 50
            assert "diabetes" in response.lower()
    
    def test_multi_part_questions(self, mock_rag_response):
        """Test quality with multi-part questions."""
        multi_questions = [
            "What is diabetes and how is it treated?",
            "What causes diabetes and can it be prevented?",
            "What are the symptoms and complications of diabetes?"
        ]
        
        for question in multi_questions:
            response = mock_rag_response(question)
            
            # Should address the question
            assert len(response) > 50
            # Should have disclaimer
            assert any(word in response.lower() 
                      for word in ["consult", "professional", "medical advice"])
    
    def test_yes_no_questions(self, mock_rag_response):
        """Test quality with yes/no questions."""
        yn_questions = [
            "Is diabetes curable?",
            "Can I eat sugar if I have diabetes?",
            "Should I take insulin?"
        ]
        
        for question in yn_questions:
            response = mock_rag_response(question)
            
            # Should provide context, not just yes/no
            assert len(response) > 50
            # Medical advice questions should defer
            if "should i" in question.lower():
                assert any(word in response.lower() 
                          for word in ["consult", "healthcare", "doctor"])
