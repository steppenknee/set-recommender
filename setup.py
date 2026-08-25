from setuptools import setup, find_packages

setup(
    name="rekordbox-set-recommender",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "google-genai>=0.1.1",
        "typer>=0.9.0",
        "rich>=13.5.0",
        "pydantic>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "rekordbox-set-recommender=set_recommender.cli:app",
        ],
    },
    author="Antigravity",
    description="Intelligent CLI DJ set recommender for Rekordbox XML track libraries.",
    python_requires=">=3.10",
)
