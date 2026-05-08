import argparse
from pathlib import Path

from .io_excel import process_file  # or adjust import to match your structure

def _find_tools_root(start: Path) -> Path:
    """
    Walk upward until we find the Tools repo root (identified by Canonical_DB folder).
    """
    p = start.resolve()
    for parent in [p, *p.parents]:
        if (parent / "Canonical_DB").exists():
            return parent
    return p


def _find_tools_root(start: Path) -> Path:
    """
    Walk upward until we find the Tools repo root (identified by Canonical_DB folder).
    Falls back to the start directory if not found.
    """
    p = start.resolve()
    for parent in [p, *p.parents]:
        if (parent / "Canonical_DB").exists():
            return parent
    return p


def main():
    ap = argparse.ArgumentParser(description="Explode and repair CAS columns from an Excel file.")

    ap.add_argument("input", type=str, help="Path to input .xlsx")
    ap.add_argument("--sheet", type=str, default=None, help="Excel sheet name (default: first sheet)")

    # Output root: default to Tools/output/cas_structurer/
    ap.add_argument(
        "--outdir",
        type=str,
        default=None,
        help="Output directory (default: Tools/output/cas_structurer/)",
    )

    # Required per-file metadata
    ap.add_argument(
        "--customer-id",
        type=str,
        required=True,
        help="Required customer short code, e.g. MANE",
    )

    # Explicit column mapping (strict)
    ap.add_argument("--cas-col", type=str, default="CAS", help="CAS column header (default: 'CAS')")
    ap.add_argument("--code-col", type=str, default="Code Unique", help="Customer code column header (default: 'Code Unique')")
    ap.add_argument("--name-col", type=str, default="Designation", help="Name column header (default: 'Designation')")

    args = ap.parse_args()


    input_path = Path(args.input).resolve()
    tools_root = _find_tools_root(Path(__file__).resolve())

    if args.outdir:
        outdir = Path(args.outdir)
        # If user passes a relative path, make it relative to Tools root, not the current working dir
        if not outdir.is_absolute():
            outdir = (tools_root / outdir).resolve()
    else:
        outdir = (tools_root / "output" / "CAS_Structurer").resolve()

    outdir.mkdir(parents=True, exist_ok=True)


    result = process_file(
        input_path=input_path,
        sheet=args.sheet,
        outdir=outdir,
        customer_id=args.customer_id,
        cas_col=args.cas_col,
        code_col=args.code_col,
        name_col=args.name_col,
        strict=True,
    )

    if result is None:
        raise RuntimeError("process_file() returned None. Check io_excel.process_file for missing return or swallowed exception.")

    if isinstance(result, tuple) and len(result) == 2:
        out1, out2 = result
        out3 = None
    elif isinstance(result, tuple) and len(result) == 3:
        out1, out2, out3 = result
    else:
        raise RuntimeError(f"Unexpected process_file() return value: {result!r}")

    print(f"Wrote: {out1}")
    print(f"Wrote: {out2}")
    if out3 is not None:
        print(f"Wrote: {out3}")


if __name__ == "__main__":
    main()