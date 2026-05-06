from setuptools import setup, find_packages
import json
import os

# Load optional config defaults (timeouts, logging, etc.)
config_path = os.path.join("physprops", "config.json")
if os.path.exists(config_path):
    with open(config_path, "r") as f:
        config = json.load(f)
else:
    config = {}

setup(
    name="physprops",
    version="1.0.0",
    description="Physical Properties Retrieval App (PubChem + RDKit + fallbacks)",
    author="Volkert de Villeneuve",
    packages=find_packages(where="."),
    python_requires=">=3.8",

    # RDKit is installed via conda, not pip
    install_requires=[
        "pandas>=1.5.0",
        "requests>=2.25.0",
        "openpyxl>=3.0.0",
    ],

    include_package_data=True,
    package_data={
        "physprops": ["config.json"],
    },

    entry_points={
        "console_scripts": [
            "physprops=physprops.main:cli",
        ]
    },

    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Chemistry",
        "License :: OSI Approved :: MIT License",
    ],
)