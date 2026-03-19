from setuptools import setup, find_packages

# Read version from src/__init__.py without importing
version = "0.2.0"
with open('src/__init__.py', 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('__version__'):
            version = line.split('=')[1].strip().strip('"').strip("'")
            break

setup(
    name="sheppard",
    version=version,
    packages=find_packages(),
    install_requires=[
        'aiohttp>=3.9.1',
        'python-dotenv>=1.0.0',
        'pydantic>=2.5.2',
        'rich>=13.7.0',
        'redis>=5.0.1',
        'aioredis>=2.0.1',
        'chromadb>=0.4.18',
        'selenium>=4.15.2',
        'beautifulsoup4>=4.12.2',
        'webdriver-manager>=4.0.1'
    ],
    python_requires='>=3.8',
    description="A chat system with persistent memory and LLM integration",
    author="Your Name",
    author_email="your.email@example.com",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
