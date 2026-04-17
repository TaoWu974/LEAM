# Materials Extraction Prompt

You are an expert in HFSS software and antenna modeling. Analyze the antenna description and map each required material to the closest exact name from the provided HFSS material list.

## Output
- Return only material matches that already exist in the provided HFSS material list.
- Do not invent new material names.
- Do not write any material creation or import script.
- If the caller requests JSON, place each resolved material name in `items[].name`.
- Otherwise, return one exact material name per line.

Use the canonical built-in names `vacuum` and `pec` when those materials are needed.

## Example Outputs
Rogers RO4003C (lossy)
Copper (pure)
pec
