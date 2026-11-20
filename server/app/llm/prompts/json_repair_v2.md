# Unpack: JSON repair (prompt v2)

You are given a reply that a program could not accept, the error it reported, and the JSON Schema the reply must satisfy. Return the same reply, fixed.

Rules:
1. Keep the meaning and the wording of every value that is already valid. Change only what is needed to satisfy the schema.
2. Remove anything that is not part of the JSON object: markdown fences, text before or after, comments.
3. Fix syntax: double quotes, escaped quotes and line breaks inside strings, no trailing commas, balanced brackets. If the reply was cut off, close it and drop the last item if it is incomplete.
4. Fix structure: use the exact field names and nesting of the schema. A missing required field gets an empty value of the right type (`""`, `[]`, `null` where the schema allows it). Remove fields the schema does not have.
5. Fix enumerations: a value outside the allowed list becomes the closest allowed value (all lowercase). If none is close, drop that item.
6. Never invent content, never add new items, and never change a quote: quotes are checked against a transcript you cannot see.
7. Reply with the JSON object only.

JSON Schema the reply must satisfy:

```json
{{JSON_SCHEMA}}
```
