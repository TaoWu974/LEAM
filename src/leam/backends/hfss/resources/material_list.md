# Material List (HFSS)

This project does not ship HFSS/AEDT material library data. Material names are enumerated at runtime from your local AEDT installation.

How it works:
- LEAM first tries to auto-detect the local AEDT install through PyAEDT-compatible installation discovery and `ANSYSEM_ROOT*` environment variables.
- `hfss_path` in `config.json` and `HFSS_PATH` remain available as advanced overrides when auto-detection is not enough.
- LEAM scans local AEDT SysLibrary material files under the resolved AEDT root's `syslib` directory.
- Only local `.amat` material library files are read; no HFSS material database is bundled with the package.
- HFSS material extraction resolves required antenna materials to existing AEDT material names and writes those resolved names to `materials.json`.
- The normal HFSS flow reuses those resolved names directly during geometry creation. It does not generate a separate material import script.
- Built-in materials such as `vacuum` and `pec` are handled as canonical names and do not need custom definitions.

If HFSS/AEDT is not installed or the SysLibrary folder cannot be found, material extraction returns an empty list.
