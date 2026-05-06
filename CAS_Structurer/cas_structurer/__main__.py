import argparse
from pathlib import Path

from .io_excel import process_file


def main():
    ap = argparse.ArgumentParser(description="Explode and repair CAS columns from an Excel file.")
    ap.add_argument("input", type=str, help="Path to input .xlsx")
    ap.add_argument("--sheet", type=str, default=None, help="Excel sheet name (default: first sheet)")
    ap.add_argument("--outdir", type=str, default=None, help="Output directory (default: input folder)")
    args = ap.parse_args()

    input_path = Path(args.input)
    outdir = Path(args.outdir) if args.outdir else input_path.parent

    out1, out2 = process_file(input_path, args.sheet, outdir)
    print(f"Wrote: {out1}")
    print(f"Wrote: {out2}")


if __name__ == "__main__":
    main()