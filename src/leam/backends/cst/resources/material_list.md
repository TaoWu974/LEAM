# Material List (CST)

This project does not ship CST material library data. Material names are enumerated at runtime from your local CST installation.

How it works:
- LEAM first tries to auto-detect the local CST install.
- `cst_path` in `config.json` and `CST_PATH` remain available as advanced overrides when auto-detection is not enough.
- LEAM reads the resolved CST install root's `Library\Materials` directory and uses only files ending in `.mtd`.
- Non-.mtd entries (e.g., filelist.txt or material library.mal) are ignored.

If CST is not installed or the materials folder cannot be found, material extraction returns an empty list.
