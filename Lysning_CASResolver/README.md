# Lysning CAS Resolver

Multi-source CAS number to SMILES resolver with offline caching and API placeholders.

## Installation
```
pip install -e .
```

## Usage
```
lysning_casresolver input.xlsx -o output.xlsx
```
You need an Excel or CSV file where the first column lists CAS numbers. The resolver will look up values in a local cache (cas_smiles_output.xlsx) by default.

### Configuration
Update `config.json` to specify API keys or alternate cache file.
