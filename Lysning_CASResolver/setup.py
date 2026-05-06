from setuptools import setup, find_packages
import pathlib

# Project root
HERE = pathlib.Path(__file__).parent

# Read README if present
README = ""
readme_file = HERE / "README.md"
if readme_file.exists():
    README = readme_file.read_text(encoding="utf-8")

setup(
    name="lysning_casresolver",
    version="1.0.0",
    description="Multi-source CAS → SMILES resolver with PubChem, ChemSpider, Cactus, OPSIN, and RDKit fallback",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Lysning Innovation Consultants",
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.9",
    install_requires=[
        "requests>=2.20",
        "pandas>=1.4",
        "openpyxl>=3.0",
        # RDKit is typically installed via conda, not pip:
        # "rdkit" is intentionally omitted here.
    ],
    entry_points={
        "console_scripts": [
            "casresolver=lysning_casresolver.main:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Chemistry",
        "License :: OSI Approved :: MIT License",
    ],
)