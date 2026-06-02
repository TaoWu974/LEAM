# Validation And Safety

## Check Solid Review

Report only concrete problems that make the solid list inconsistent with the description, parameters, or materials.

Focus on:

- Missing or contradictory solids.
- Wrong functional role or material.
- Dimensions or placement that contradict the source.
- Parameter names or material names that do not match context.
- Boolean intent that references nonexistent or implausible solids.

Ignore:

- Air box, ports, monitors, boundaries, solver setup.
- Naming preferences when geometry is still correct.
- Downstream modeling details not needed for `solids.json`.
- Built-in materials: CST `Vacuum`/`PEC`, HFSS `vacuum`/`pec`.

Issue report shape:

```json
{
  "status": "issues",
  "issues": [
    {
      "category": "materials",
      "severity": "error",
      "solid": "Substrate",
      "path": "solids[0].material",
      "route_to": "materials",
      "issue": "Substrate uses a material not listed in materials context."
    }
  ],
  "issue_counts": {"total": 1, "errors": 1, "warnings": 0}
}
```

Use `status: "ok"` and zero counts when all issues are warnings or there are no issues.

Route to exactly one of `parameters`, `materials`, or `solids`.

## Engineering Limits

This skill can produce modeling artifacts and, when a usable backend and execution capability are available, run simulator-facing workflow steps. Neither generated artifacts nor executed workflow steps are validated antenna performance by themselves.

Do not promise:

- S-parameters, impedance match, gain, radiation pattern, efficiency, bandwidth, or optimization results.
- Fabrication-ready correctness.
- That CST/HFSS will run the generated code without manual review.

Always state major assumptions and recommend simulator validation before design decisions.

## Missing Data Handling

If information is missing:

- For exact reconstruction tasks, ask for the missing figure/table/value when it materially changes geometry.
- For conceptual design tasks, introduce named parameters and mark assumptions.
- Do not fabricate material properties.
- Do not invent exact dimensions from performance goals unless using a known approximation; label those as first-pass estimates.

## Attachment Awareness

If the agent has access to images/PDFs, extract:

- Coordinate system and origin.
- Parameter symbols and table values.
- Layer stack and thicknesses.
- Slot/patch/ground/feed relationships.
- Corrections or inconsistencies in figures.

If images are referenced but unavailable, ask for them or proceed with clearly marked assumptions.

Attachment handling rules:

- Readable text-like files can be used as prompt context even when the extension is uncommon.
- PDF files can be used as document context.
- Use the agent's available image tools to inspect, convert, or extract information from image attachments as needed.
- If forwarding images directly through LEAM model input, PNG, JPG, and JPEG are the native image formats; otherwise the agent may preprocess other image formats before modeling.
- Binary project files such as `.cst` and `.aedt` are local artifacts, not ordinary prompt text.

## Simulator Availability Boundary

Before generating backend-specific artifacts, the agent must detect which simulator backends are usable in the current environment.

- CST is usable only when a local CST install and its Python interface/material library can be reached.
- HFSS is usable only when a local AEDT/HFSS install is present and PyAEDT (`ansys.aedt.core`) is importable.
- If the user explicitly requested an unavailable backend, exit the agent loop and report the failed availability condition.
- If the user did not specify a backend, choose an available backend. If neither backend is available, exit the agent loop and report that no usable CST/HFSS backend was detected.

If the user asks to execute or simulate:

- Execute only when the selected backend is available and the agent can run the simulator workflow in the current environment.
- Do not claim execution, S-parameters, gain, radiation patterns, optimization, or measured performance unless those results were actually produced by a simulator run in the current environment.
- If execution is unavailable, provide the generated code/artifacts and validation checklist, then explain the missing backend or execution capability.
