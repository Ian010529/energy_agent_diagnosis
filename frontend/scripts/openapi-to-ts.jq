def refname: .["$ref"] | split("/") | last;
def ts:
  if has("$ref") then "components[\"schemas\"][\"" + refname + "\"]"
  elif has("const") then (.const | tojson)
  elif has("enum") then ([.enum[] | tojson] | join(" | "))
  elif has("anyOf") then ([.anyOf[] | ts] | join(" | "))
  elif has("oneOf") then ([.oneOf[] | ts] | join(" | "))
  elif has("allOf") then ([.allOf[] | ts] | join(" & "))
  elif .type == "array" then "(" + (.items | ts) + ")[]"
  elif .type == "object" or has("properties") then
    . as $schema |
    "{ " + (
      [(.properties // {} | to_entries[] | . as $entry | $entry.key as $key |
        ($key | tojson) +
        (if (($schema.required // []) | index($key)) then ": " else "?: " end) +
        ($entry.value | ts) + ";"
      )] +
      (if (.additionalProperties | type) == "object" then
        ["[key: string]: " + (.additionalProperties | ts) + ";"]
       elif .additionalProperties == true then ["[key: string]: unknown;"]
       else [] end)
      | join(" ")
    ) + " }"
  elif .type == "string" then "string"
  elif .type == "integer" or .type == "number" then "number"
  elif .type == "boolean" then "boolean"
  elif .type == "null" then "null"
  else "unknown"
  end;

"// AUTO-GENERATED from frontend/openapi/backend.json.\n" +
"export interface components {\n  schemas: {\n" +
([.components.schemas | to_entries[] | "    " + (.key | tojson) + ": " + (.value | ts) + ";"] | join("\n")) +
"\n  };\n}\n"
