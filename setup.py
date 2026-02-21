from setuptools import setup, find_packages

setup(
    name="bpm4b",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="MP3 to M4B Audiobook Converter - Convert MP3 files to M4B format with chapter support",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/bpm4b",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "bpm4b": [
            "templates/*.html",
        ],
    },
    install_requires=[
        line.strip()
        for line in open("requirements.txt", encoding="utf-8")
        if line.strip() and not line.startswith("#")
    ],
    entry_points={
        "console_scripts": [
            "bpm4b=bpm4b.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Sound/Audio :: Conversion",
        "Topic :: Utilities",
    ],
    python_requires=">=3.8",
    keywords="mp3 m4b audiobook converter audio flask",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/bpm4b/issues",
        "Source": "https://github.com/yourusername/bpm4b",
    },
)
