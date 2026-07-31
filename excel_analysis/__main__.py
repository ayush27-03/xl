"""Enable ``python -m excel_analysis <file.xlsx>``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
