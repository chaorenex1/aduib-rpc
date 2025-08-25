"""
json_to_proto.py — Generate .proto from JSON **example** or JSON **Schema**.

Usage examples:
  # From a JSON example document
  python json_to_proto.py -i example.json -o example.proto -m Example -p demo.example

  # From a JSON Schema
  python json_to_proto.py -i schema.json -o out.proto -m Root -p my.pkg --schema

Notes:
- Targets proto3 syntax.
- Field numbers are auto-assigned deterministically (sorted by field name).
- Arrays become `repeated` fields. Arrays of objects become repeated nested messages.
- Maps are detected when object keys are all strings and values share a scalar type.
- Enums are generated from JSON Schema `enum` definitions (string/number enums only).
- Mixed-type arrays/values fall back to `string` with a comment.
- `null` is represented by `optional` fields; when no other type info exists, fallback is `string`.
"""

from __future__ import annotations
import argparse
import json
import keyword
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

PROTO_RESERVED = {
    # From https://protobuf.dev/reference/protobuf/proto3-spec/#reserved
    "syntax","import","weak","public","package","option","enum","message","service",
    "rpc","returns","extend","extensions","to","max","reserved","oneof","map",
    "repeated","optional","double","float","int32","int64","uint32",
    "uint64","sint32","sint64","fixed32","fixed64","sfixed32","sfixed64","bool",
    "string","bytes","true","false"
}

# ------------- Utilities -------------

def pascal_case(name: str) -> str:
    name = re.sub(r"[^0-9A-Za-z_]+", " ", name)
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "X"
    s = "".join(p[:1].upper() + p[1:] for p in parts)
    if s[0].isdigit():
        s = "X" + s
    if s in PROTO_RESERVED:
        s += "Msg"
    return s

def snake_case(name: str) -> str:
    name = re.sub(r"[^0-9A-Za-z_]+", "_", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = name.lower().strip("_") or "field"
    if name[0].isdigit():
        name = "f_" + name
    if name in PROTO_RESERVED:
        name += "_"
    if keyword.iskeyword(name):
        name += "_"
    return name

# ------------- Type system -------------

Scalar = str  # proto scalar name

@dataclass
class EnumSpec:
    name: str
    values: List[Union[str, int]]

@dataclass
class FieldSpec:
    name: str
    type_name: str  # proto scalar or message/enum name
    number: int
    repeated: bool = False
    optional: bool = False
    is_map: bool = False
    map_key_type: Optional[str] = None
    map_value_type: Optional[str] = None
    comment: Optional[str] = None

@dataclass
class MessageSpec:
    name: str
    fields: List[FieldSpec] = field(default_factory=list)
    nested_messages: List['MessageSpec'] = field(default_factory=list)
    nested_enums: List[EnumSpec] = field(default_factory=list)

@dataclass
class FileSpec:
    package: Optional[str]
    messages: List[MessageSpec]
    enums: List[EnumSpec]
    options: Dict[str, str] = field(default_factory=dict)

# ------------- Inference from JSON example -------------

def infer_scalar(value: Any) -> Tuple[Scalar, Optional[str]]:
    """Infer proto scalar type for a Python value. Returns (type, comment)."""
    if isinstance(value, bool):
        return "bool", None
    if isinstance(value, int) and not isinstance(value, bool):
        # Heuristic: use int64 by default (safe for most cases)
        return "int64", None
    if isinstance(value, float):
        return "double", None
    if value is None:
        return "string", "nullable: fell back to string"
    return "string", None

_counter = 0

def fresh_name(prefix: str = "Msg") -> str:
    global _counter
    _counter += 1
    return f"{pascal_case(prefix)}{_counter}"


def unify_scalars(types: List[Scalar]) -> Tuple[Scalar, Optional[str]]:
    tset = set(types)
    if len(tset) == 1:
        return types[0], None
    # mixed numeric -> double
    if tset.issubset({"int64","double"}):
        return "double", "mixed numeric -> double"
    # otherwise string
    return "string", f"mixed types {sorted(tset)} -> string"


def detect_map(obj: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Detect map<string, T> when all keys are strings and values share scalar type.
    Returns (key_type, value_type) or None.
    """
    if not obj:
        return None
    key_types = {type(k) for k in obj.keys()}
    if key_types != {str}:
        return None
    value_types = []
    for v in obj.values():
        if isinstance(v, (dict, list)):
            return None
        scalar, _ = infer_scalar(v)
        value_types.append(scalar)
    vtype, _ = unify_scalars(value_types)
    return ("string", vtype)


def build_from_example(name: str, data: Any) -> MessageSpec:
    msg = MessageSpec(name=pascal_case(name))

    def add_field(fname: str, fval: Any, idx: int):
        nonlocal msg
        field_name = snake_case(fname)
        comment: Optional[str] = None
        repeated = False
        optional = False
        is_map = False
        map_key_type = None
        map_value_type = None
        type_name = "string"

        if isinstance(fval, list):
            repeated = True
            # infer from elements
            if not fval:
                type_name = "string"
                comment = "empty array -> repeated string"
            else:
                # all dicts?
                if all(isinstance(x, dict) for x in fval):
                    # build nested message from union of keys (use first element as template)
                    nested = merge_objects([x for x in fval if isinstance(x, dict)])
                    nested_msg = build_from_example(pascal_case(fname), nested)
                    msg.nested_messages.append(nested_msg)
                    type_name = nested_msg.name
                elif all(not isinstance(x, (dict, list)) for x in fval):
                    scalars = [infer_scalar(x)[0] for x in fval]
                    type_name, note = unify_scalars(scalars)
                    if note:
                        comment = note
                else:
                    type_name = "string"
                    comment = "mixed array -> repeated string"
        elif isinstance(fval, dict):
            maybe_map = detect_map(fval)
            if maybe_map:
                is_map = True
                map_key_type, map_value_type = maybe_map
                type_name = "map<%s, %s>" % (map_key_type, map_value_type)
            else:
                nested_msg = build_from_example(pascal_case(fname), fval)
                msg.nested_messages.append(nested_msg)
                type_name = nested_msg.name
        else:
            type_name, note = infer_scalar(fval)
            if note:
                comment = note
                optional = True
        fs = FieldSpec(
            name=field_name,
            type_name=type_name,
            number=idx,
            repeated=repeated,
            optional=optional,
            is_map=is_map,
            map_key_type=map_key_type,
            map_value_type=map_value_type,
            comment=comment,
        )
        msg.fields.append(fs)

    if isinstance(data, dict):
        for i, key in enumerate(sorted(data.keys()), start=1):
            add_field(key, data[key], i)
    elif isinstance(data, list):
        # Wrap: Root has repeated Item
        wrapper = MessageSpec(name=msg.name)
        if data and all(isinstance(x, dict) for x in data):
            merged = merge_objects([x for x in data if isinstance(x, dict)])
            item = build_from_example("Item", merged)
            wrapper.nested_messages.append(item)
            wrapper.fields.append(FieldSpec(
                name="items", type_name=item.name, number=1, repeated=True
            ))
            msg = wrapper
        else:
            # repeated scalars -> items
            if data:
                scalars = [infer_scalar(x)[0] for x in data if not isinstance(x, (dict, list))]
                t, note = unify_scalars(scalars or ["string"])
            else:
                t, note = ("string", "empty array -> string")
            msg.fields.append(FieldSpec(name="items", type_name=t, number=1, repeated=True, comment=note))
    else:
        # scalar root -> single field 'value'
        t, note = infer_scalar(data)
        msg.fields.append(FieldSpec(name="value", type_name=t, number=1, optional=True, comment=note))

    return msg


def merge_objects(objs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Union of keys; pick first non-null for sample; nested dicts are merged recursively."""
    out: Dict[str, Any] = {}
    for o in objs:
        for k, v in o.items():
            if k not in out:
                out[k] = v
            else:
                if isinstance(out[k], dict) and isinstance(v, dict):
                    out[k] = merge_objects([out[k], v])
                # prefer non-null illustrative value
                elif out[k] is None and v is not None:
                    out[k] = v
    return out

# ------------- From JSON Schema -------------

def from_schema(name: str, schema: Dict[str, Any]) -> MessageSpec:
    title = schema.get("title") or name
    msg = MessageSpec(name=pascal_case(title))
    required = set(schema.get("required", []))
    props = schema.get("properties", {})

    # Enums at the root
    if "enum" in schema:
        enum_name = pascal_case(title)
        enum_vals = schema["enum"]
        enum = EnumSpec(name=enum_name, values=enum_vals)
        msg.nested_enums.append(enum)
        msg.fields.append(FieldSpec(name="value", type_name=enum_name, number=1))
        return msg

    def handle_schema_field(fname: str, s: Dict[str, Any], index: int):
        nonlocal msg
        field_name = snake_case(fname)
        repeated = False
        optional = fname not in required
        comment: Optional[str] = None
        is_map = False
        map_key_type = None
        map_value_type = None
        type_name = "string"

        stype = s.get("type")
        if isinstance(stype, list):
            # remove null
            types_wo_null = [t for t in stype if t != "null"]
            optional = optional or ("null" in stype)
            stype = types_wo_null[0] if types_wo_null else None

        if s.get("enum") is not None:
            ename = pascal_case(fname)
            enum = EnumSpec(name=ename, values=s["enum"])
            msg.nested_enums.append(enum)
            type_name = ename
        elif stype == "array":
            repeated = True
            items = s.get("items", {})
            if items.get("type") == "object" or items.get("properties"):
                nested = from_schema(fname, items)
                msg.nested_messages.append(nested)
                type_name = nested.name
            else:
                type_name = map_schema_scalar(items)
        elif stype == "object" or s.get("properties"):
            # map detection: additionalProperties with scalar
            addl = s.get("additionalProperties")
            if isinstance(addl, dict) and addl and addl.get("type") in {"string","number","integer","boolean"}:
                is_map = True
                map_key_type, map_value_type = "string", map_schema_scalar(addl)
                type_name = f"map<{map_key_type}, {map_value_type}>"
            else:
                nested = from_schema(fname, s)
                msg.nested_messages.append(nested)
                type_name = nested.name
        else:
            type_name = map_schema_scalar(s)

        fs = FieldSpec(
            name=field_name,
            type_name=type_name,
            number=index,
            repeated=repeated,
            optional=optional,
            is_map=is_map,
            map_key_type=map_key_type,
            map_value_type=map_value_type,
            comment=comment,
        )
        msg.fields.append(fs)

    for i, key in enumerate(sorted(props.keys()), start=1):
        handle_schema_field(key, props[key], i)

    return msg


def map_schema_scalar(s: Dict[str, Any]) -> Scalar:
    t = s.get("type")
    if isinstance(t, list):
        t = [x for x in t if x != "null"]
        t = t[0] if t else None
    fmt = s.get("format")
    if t == "boolean":
        return "bool"
    if t == "integer":
        # choose int64 by default; inspect format if present
        if fmt in {"int32","int16","int8"}:
            return "int32"
        return "int64"
    if t == "number":
        # use double for general number, float for format=float
        return "float" if fmt == "float" else "double"
    if t == "string":
        # special-cases could be bytes, but we keep string
        return "string"
    return "string"

# ------------- Emission -------------

def emit(filespec: FileSpec) -> str:
    lines: List[str] = []
    lines.append("syntax = \"proto3\";")
    if filespec.package:
        lines.append(f"package {filespec.package};")
    for k, v in filespec.options.items():
        lines.append(f"option {k} = {json.dumps(v)};")
    lines.append("")

    for e in filespec.enums:
        lines.extend(emit_enum(e, indent=0))
        lines.append("")

    for m in filespec.messages:
        lines.extend(emit_message(m, indent=0))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def emit_enum(enum: EnumSpec, indent: int) -> List[str]:
    ind = "  " * indent
    lines = [f"{ind}enum {enum.name} {{"]
    # Ensure a 0 value; if values are strings, create UPPER_SNAKE identifiers
    if enum.values:
        # Generate deterministic names
        for i, v in enumerate(enum.values):
            if isinstance(v, str):
                ident = re.sub(r"[^0-9A-Za-z]+", "_", v).upper().strip("_") or f"VALUE_{i}"
                if ident[0].isdigit():
                    ident = "V_" + ident
                lines.append(f"{ind}  {ident} = {i}; // {json.dumps(v)}")
            else:
                ident = f"VALUE_{v}" if isinstance(v, int) else f"VALUE_{i}"
                lines.append(f"{ind}  {ident} = {i};")
    else:
        lines.append(f"{ind}  VALUE_0 = 0;")
    lines.append(f"{ind}}}")
    return lines


def emit_message(msg: MessageSpec, indent: int) -> List[str]:
    ind = "  " * indent
    lines: List[str] = [f"{ind}message {msg.name} {{"]

    # nested enums first
    for e in msg.nested_enums:
        lines.extend(emit_enum(e, indent + 1))
        lines.append("")

    # nested messages next
    for nm in msg.nested_messages:
        lines.extend(emit_message(nm, indent + 1))
        lines.append("")

    # fields
    for f in sorted(msg.fields, key=lambda x: x.number):
        field_prefix = "repeated " if f.repeated else ("optional " if f.optional else "")
        if f.is_map:
            decl = f"map<{f.map_key_type}, {f.map_value_type}> {f.name} = {f.number};"
        else:
            decl = f"{field_prefix}{f.type_name} {f.name} = {f.number};"
        if f.comment:
            lines.append(f"{ind}  {decl} // {f.comment}")
        else:
            lines.append(f"{ind}  {decl}")

    lines.append(f"{ind}}}")
    return lines

# ------------- CLI -------------

def gen(input_data: str, output_path: str, root_message: str, package: Optional[str], is_schema: bool):
    if is_schema:
        data = json.loads(input_data)
        root = from_schema(root_message, data)
    else:
        data = json.loads(input_data)
        root = build_from_example(root_message, data)

    filespec = FileSpec(package=package, messages=[root], enums=[])
    proto_text = emit(filespec)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(proto_text)
    print(f"Wrote {output_path}\nRoot message: {root.name}")

def main():
    ap = argparse.ArgumentParser(description="Generate .proto from JSON example or JSON Schema")
    ap.add_argument("-i", "--input", required=True, help="Path to JSON file (example or schema)")
    ap.add_argument("-o", "--output", required=True, help="Path to write .proto")
    ap.add_argument("-m", "--message", default="Root", help="Root message name")
    ap.add_argument("-p", "--package", default=None, help="Proto package name")
    ap.add_argument("--schema", action="store_true", help="Treat input as JSON Schema instead of example JSON")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    if args.schema:
        root = from_schema(args.message, data)
    else:
        root = build_from_example(args.message, data)

    filespec = FileSpec(package=args.package, messages=[root], enums=[])
    proto_text = emit(filespec)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(proto_text)
    print(f"Wrote {args.output}\nRoot message: {root.name}")

if __name__ == "__main__":
    gen(
        input_data=json.dumps({}), output_path="../src/aduib_rpc/proto/chat_completion.proto", root_message="chatCompletion", package="src.aduib_rpc.proto", is_schema=False
    )
