from setuptools import find_packages, setup

setup(
    name="medical-chatbot",
    version="0.0.1",
    author="Medical Chatbot",
    packages=find_packages(),
    install_requires=[
        "flask",
        "langchain",
        "langchain-google-genai",
        "langchain-community",
        "langchain-huggingface",
        "faiss-cpu",
        "python-dotenv",
        "pypdf",
        "sentence-transformers",
    ]
)
