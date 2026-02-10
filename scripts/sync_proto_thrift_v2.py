#!/usr/bin/env python3
"""
sync_proto_thrift_v2.py

Syncs the v2 wire schema across:
  - src/aduib_rpc/proto/aduib_rpc_v2.proto (source of truth)
  - src/aduib_rpc/proto/aduib_rpc_v2.thrift
  - src/aduib_rpc/protocol/v2/*.py model fields

Default behavior is "check" mode (no writes). Use --apply to write changes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PROTO_PATH = REPO_ROOT / "src" / "aduib_rpc" / "proto" / "aduib_rpc_v2.proto"
THRIFT_PATH = REPO_ROOT / "src" / "aduib_rpc" / "proto" / "aduib_rpc_v2.thrift"


PROTO_SCALARS = {
    "string": "str",
    "int32": "int",
    "int64": "int",
    "double": "float",
    "bool": "bool",
}

PROTO_TO_THRIFT_SCALARS = {
    "string": "string",
    "int32": "i32",
    "int64": "i64",
    "double": "double",
    "bool": "bool",
}

PROTO_SPECIAL_PY = {
    "google.protobuf.Struct": "dict[str, Any]",
    "google.protobuf.Value": "Any",
}

PROTO_SPECIAL_THRIFT = {
    "google.protobuf.Struct": "string",
    "google.protobuf.Value": "string",
}


@dataclass
class ProtoField:
    name: str
    type_name: str
    number: int
    repeated: bool = False
    optional: bool = False
    is_map: bool = False
    map_key: str | None = None
    map_value: str | None = None
    oneof: str | None = None


@dataclass
class ProtoMessage:
    name: str
    fields: list[ProtoField] = field(default_factory=list)
    oneofs: dict[str, list[ProtoField]] = field(default_factory=dict)


@dataclass
class ProtoEnum:
    name: str
    values: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class ProtoSchema:
    messages: dict[str, ProtoMessage] = field(default_factory=dict)
    enums: dict[str, ProtoEnum] = field(default_factory=dict)
    services: dict[str, "ProtoService"] = field(default_factory=dict)


@dataclass
class ProtoRpc:
    name: str
    request_type: str
    response_type: str
    request_stream: bool = False
    response_stream: bool = False


@dataclass
class ProtoService:
    name: str
    rpcs: list[ProtoRpc] = field(default_factory=list)


def _strip_comment(line: str) -> str:
    if "//" in line:
        line = line.split("//", 1)[0]
    return line.strip()


def parse_proto(path: Path) -> ProtoSchema:
    schema = ProtoSchema()
    ctx_stack: list[tuple[str, str]] = []
    current_message: ProtoMessage | None = None
    current_enum: ProtoEnum | None = None
    current_oneof: str | None = None
    current_service: ProtoService | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = _strip_comment(raw)
        if not line:
            continue

        if line.startswith("message "):
            name = line.split()[1]
            name = name.rstrip("{").strip()
            current_message = ProtoMessage(name=name)
            schema.messages[name] = current_message
            ctx_stack.append(("message", name))
            continue

        if line.startswith("enum "):
            name = line.split()[1]
            name = name.rstrip("{").strip()
            current_enum = ProtoEnum(name=name)
            schema.enums[name] = current_enum
            ctx_stack.append(("enum", name))
            continue

        if line.startswith("oneof "):
            if current_message is None:
                continue
            name = line.split()[1]
            name = name.rstrip("{").strip()
            current_oneof = name
            current_message.oneofs.setdefault(name, [])
            ctx_stack.append(("oneof", name))
            continue

        if line.startswith("service "):
            name = line.split()[1].rstrip("{").strip()
            current_service = ProtoService(name=name)
            schema.services[name] = current_service
            ctx_stack.append(("service", name))
            continue

        if line.startswith("}"):
            if not ctx_stack:
                continue
            ctx, _ = ctx_stack.pop()
            if ctx == "message":
                current_message = None
            elif ctx == "enum":
                current_enum = None
            elif ctx == "oneof":
                current_oneof = None
            elif ctx == "service":
                current_service = None
            continue

        # enum values
        if current_enum is not None:
            m = re.match(r"^([A-Za-z0-9_]+)\s*=\s*([0-9]+)", line)
            if m:
                current_enum.values.append((m.group(1), int(m.group(2))))
            continue

        # service RPCs
        if current_service is not None:
            rpc = _parse_proto_rpc(line)
            if rpc:
                current_service.rpcs.append(rpc)
            continue

        # message fields
        if current_message is None:
            continue

        field = _parse_proto_field(line)
        if field is None:
            continue
        if current_oneof:
            field.oneof = current_oneof
            current_message.oneofs[current_oneof].append(field)
        current_message.fields.append(field)

    return schema


def _parse_proto_field(line: str) -> ProtoField | None:
    map_re = re.compile(
        r"^(optional\s+|repeated\s+)?map\s*<\s*([^,]+)\s*,\s*([^>]+)\s*>\s+([A-Za-z0-9_]+)\s*=\s*([0-9]+)"
    )
    m = map_re.match(line)
    if m:
        optional = (m.group(1) or "").strip() == "optional"
        repeated = (m.group(1) or "").strip() == "repeated"
        return ProtoField(
            name=m.group(4),
            type_name="map",
            number=int(m.group(5)),
            optional=optional,
            repeated=repeated,
            is_map=True,
            map_key=m.group(2).strip(),
            map_value=m.group(3).strip(),
        )

    field_re = re.compile(
        r"^(optional\s+|repeated\s+)?([A-Za-z0-9_.]+)\s+([A-Za-z0-9_]+)\s*=\s*([0-9]+)"
    )
    m = field_re.match(line)
    if not m:
        return None
    optional = (m.group(1) or "").strip() == "optional"
    repeated = (m.group(1) or "").strip() == "repeated"
    return ProtoField(
        name=m.group(3),
        type_name=m.group(2),
        number=int(m.group(4)),
        optional=optional,
        repeated=repeated,
    )


def _parse_proto_rpc(line: str) -> ProtoRpc | None:
    rpc_re = re.compile(
        r"^rpc\s+([A-Za-z0-9_]+)\s*\(\s*(stream\s+)?([A-Za-z0-9_.]+)\s*\)\s*returns\s*\(\s*(stream\s+)?([A-Za-z0-9_.]+)\s*\)"
    )
    m = rpc_re.match(line)
    if not m:
        return None
    return ProtoRpc(
        name=m.group(1),
        request_type=m.group(3),
        response_type=m.group(5),
        request_stream=bool(m.group(2)),
        response_stream=bool(m.group(4)),
    )


def generate_thrift(schema: ProtoSchema) -> str:
    lines: list[str] = []
    lines.append("// Thrift v2 wire definition for Aduib RPC.")
    lines.append("//")
    lines.append("// This file mirrors src/aduib_rpc/proto/aduib_rpc_v2.proto.")
    lines.append("// Notes:")
    lines.append("// - google.protobuf.Struct/Value are represented as JSON strings.")
    lines.append("// - Thrift has no streaming; stream RPCs are modeled with list inputs/outputs.")
    lines.append("")
    lines.append("namespace py aduib_rpc.thrift_v2")
    lines.append("")
    lines.append("typedef map<string, string> StringMap")
    lines.append("")

    # Enums first
    for enum in schema.enums.values():
        lines.append(f"enum {enum.name} {{")
        for name, value in enum.values:
            lines.append(f"  {name} = {value},")
        lines.append("}")
        lines.append("")

    # Oneof unions (currently only Response.payload)
    oneof_unions: list[tuple[str, list[ProtoField]]] = []
    for msg in schema.messages.values():
        for oneof_name, fields in msg.oneofs.items():
            union_name = _oneof_union_name(msg.name, oneof_name)
            oneof_unions.append((union_name, fields))

    for union_name, fields in oneof_unions:
        lines.append(f"union {union_name} {{")
        for idx, field in enumerate(fields, start=1):
            thrift_type = thrift_type_for(field)
            comment = thrift_json_comment(field)
            if comment:
                lines.append(f"  {comment}")
            lines.append(f"  {idx}: {thrift_type} {field.name},")
        lines.append("}")
        lines.append("")

    # Structs
    for msg in schema.messages.values():
        lines.append(f"struct {msg.name} {{")
        if msg.oneofs:
            # Insert oneof wrapper fields using the smallest field number as the id.
            for oneof_name, fields in msg.oneofs.items():
                union_name = _oneof_union_name(msg.name, oneof_name)
                field_id = min(f.number for f in fields)
                lines.append(f"  {field_id}: optional {union_name} {oneof_name},")

        for field in msg.fields:
            if field.oneof:
                continue
            thrift_type = thrift_type_for(field)
            comment = thrift_json_comment(field)
            if comment:
                lines.append(f"  {comment}")
            optional_prefix = "optional " if field.optional else ""
            lines.append(
                f"  {field.number}: {optional_prefix}{thrift_type} {field.name},"
            )
        lines.append("}")
        lines.append("")

    # Services from proto
    for service in schema.services.values():
        lines.extend(_emit_thrift_service(service))
    return "\n".join(lines).rstrip() + "\n"


def _oneof_union_name(message: str, oneof_name: str) -> str:
    if message == "Response" and oneof_name == "payload":
        return "ResponsePayload"
    return f"{message}{oneof_name.capitalize()}"


def thrift_json_comment(field: ProtoField) -> str | None:
    if field.type_name == "google.protobuf.Struct":
        return "// JSON-encoded google.protobuf.Struct"
    if field.type_name == "google.protobuf.Value":
        return "// JSON-encoded google.protobuf.Value"
    return None


def thrift_type_for(field: ProtoField) -> str:
    if field.is_map:
        key = thrift_scalar_for(field.map_key or "string")
        value = thrift_scalar_for(field.map_value or "string")
        if key == "string" and value == "string":
            return "StringMap"
        return f"map<{key}, {value}>"
    if field.type_name in PROTO_SPECIAL_THRIFT:
        base = PROTO_SPECIAL_THRIFT[field.type_name]
    else:
        base = thrift_scalar_for(field.type_name)
    if field.repeated:
        return f"list<{base}>"
    return base


def thrift_scalar_for(proto_type: str) -> str:
    if proto_type in PROTO_TO_THRIFT_SCALARS:
        return PROTO_TO_THRIFT_SCALARS[proto_type]
    return proto_type


def _emit_thrift_service(service: ProtoService) -> list[str]:
    lines: list[str] = [f"service {service.name} {{"]
    for rpc in service.rpcs:
        comment = _rpc_stream_comment(rpc)
        if comment:
            lines.append(f"  // {comment}")
        req_type = rpc.request_type
        resp_type = rpc.response_type
        if rpc.request_stream:
            req_type = f"list<{req_type}>"
            req_arg = "requests"
        else:
            req_arg = "request"
        if rpc.response_stream:
            resp_type = f"list<{resp_type}>"
        lines.append(f"  {resp_type} {rpc.name}(1: {req_type} {req_arg}),")
    lines.append("}")
    lines.append("")
    return lines


def _rpc_stream_comment(rpc: ProtoRpc) -> str | None:
    if rpc.request_stream and rpc.response_stream:
        return "Bidirectional (modeled as lists in Thrift)"
    if rpc.request_stream:
        return "Client-streaming (modeled as list in Thrift)"
    if rpc.response_stream:
        return "Server-streaming (modeled as list in Thrift)"
    return None


@dataclass
class ModelTarget:
    proto_name: str
    file_path: Path
    class_name: str
    local_types: set[str] = field(default_factory=set)


PROTO_TO_PY_CLASS: dict[str, str] = {}
PROTO_ENUM_TO_PY: dict[str, str] = {}


def discover_model_targets(schema: ProtoSchema) -> list[ModelTarget]:
    v2_dir = REPO_ROOT / "src" / "aduib_rpc" / "protocol" / "v2"
    class_re = re.compile(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*:")
    targets: list[ModelTarget] = []
    PROTO_TO_PY_CLASS.clear()
    PROTO_ENUM_TO_PY.clear()
    per_file_classes: dict[Path, set[str]] = {}
    per_file_enums: dict[Path, set[str]] = {}
    proto_message_names = set(schema.messages.keys())
    proto_enum_names = set(schema.enums.keys())

    for path in sorted(v2_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        classes: set[str] = set()
        enums: set[str] = set()
        for raw in path.read_text(encoding="utf-8").splitlines():
            m = class_re.match(raw.strip())
            if not m:
                continue
            name = m.group(1)
            bases = [b.strip() for b in m.group(2).split(",") if b.strip()]
            if "BaseModel" in bases:
                classes.add(name)
            elif any(base.endswith("Enum") or base.endswith("StrEnum") or base.endswith("IntEnum") for base in bases):
                enums.add(name)
        per_file_classes[path] = classes
        per_file_enums[path] = enums

    # Build mapping for enums (only those that actually exist in proto).
    for path, enums in per_file_enums.items():
        for enum_name in enums:
            if enum_name in proto_enum_names:
                PROTO_ENUM_TO_PY[enum_name] = enum_name

    for path, classes in per_file_classes.items():
        local_types = set(classes) | per_file_enums.get(path, set())
        for class_name in sorted(classes):
            if class_name in proto_message_names:
                proto_name = class_name
            elif class_name.startswith("AduibRpc"):
                candidate = class_name[len("AduibRpc") :]
                proto_name = candidate if candidate in proto_message_names else None
            else:
                proto_name = None
            if not proto_name:
                continue
            PROTO_TO_PY_CLASS[proto_name] = class_name
            targets.append(
                ModelTarget(
                    proto_name=proto_name,
                    file_path=path,
                    class_name=class_name,
                    local_types=local_types,
                )
            )

    return targets


def sync_models(schema: ProtoSchema, apply: bool, update_types: bool) -> list[str]:
    targets = discover_model_targets(schema)
    by_file: dict[Path, list[ModelTarget]] = {}
    for target in targets:
        by_file.setdefault(target.file_path, []).append(target)

    changes: list[str] = []
    for file_path, targets in by_file.items():
        if not file_path.exists():
            changes.append(f"missing model file: {file_path}")
            continue
        lines = file_path.read_text(encoding="utf-8").splitlines()
        updated = False
        for target in targets:
            if target.proto_name not in schema.messages:
                changes.append(
                    f"missing proto message: {target.proto_name} for {target.class_name}"
                )
                continue
            new_lines, changed = sync_model_class(
                lines, schema.messages[target.proto_name], target, update_types
            )
            if changed:
                updated = True
                lines = new_lines
        if updated:
            changes.append(str(file_path))
            if apply:
                file_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return changes


def sync_model_class(
    lines: list[str],
    message: ProtoMessage,
    target: ModelTarget,
    update_types: bool,
) -> tuple[list[str], bool]:
    start, end = find_class_block(lines, target.class_name)
    if start is None:
        return lines, False
    class_body_start = find_class_body_start(lines, start, end)

    proto_field_order = [f.name for f in message.fields]
    proto_fields_by_name = {f.name: f for f in message.fields}

    field_re = re.compile(r"^\s{4}([A-Za-z_][A-Za-z0-9_]*)\s*:\s*")

    existing_fields: dict[str, str] = {}

    new_body: list[str] = []
    for line in lines[class_body_start:end]:
        m = field_re.match(line)
        if not m:
            new_body.append(line)
            continue
        name = m.group(1)
        if name in proto_fields_by_name:
            existing_fields[name] = line
            continue
        # field not in proto -> drop
        continue

    # Rebuild fields in proto order.
    managed_lines: list[str] = []
    for field_name in proto_field_order:
        field = proto_fields_by_name[field_name]
        if not update_types and field_name in existing_fields:
            managed_lines.append(existing_fields[field_name])
            continue
        managed_lines.append(render_field_line(field, target))

    if managed_lines:
        # Ensure a single blank line after fields when body continues.
        if new_body and new_body[0].strip() != "":
            managed_lines.append("")
        new_body = managed_lines + new_body

    updated_lines = lines[:class_body_start] + new_body + lines[end:]
    return updated_lines, updated_lines != lines


def render_field_line(field: ProtoField, target: ModelTarget) -> str:
    type_hint = python_type_for(field, target)
    optional = field.optional or field.repeated or field.is_map
    if optional and "None" not in type_hint:
        type_hint = f"{type_hint} | None"

    default = ""
    if optional:
        default = " = None"
    return f"    {field.name}: {type_hint}{default}"


def python_type_for(field: ProtoField, target: ModelTarget) -> str:
    if field.is_map:
        key = python_scalar_for(field.map_key or "string", target)
        value = python_scalar_for(field.map_value or "string", target)
        return f"dict[{key}, {value}]"
    base = python_scalar_for(field.type_name, target)
    if field.repeated:
        return f"list[{base}]"
    return base


def python_scalar_for(proto_type: str, target: ModelTarget) -> str:
    if proto_type in PROTO_SCALARS:
        return PROTO_SCALARS[proto_type]
    if proto_type in PROTO_SPECIAL_PY:
        return PROTO_SPECIAL_PY[proto_type]
    if proto_type in PROTO_ENUM_TO_PY:
        name = PROTO_ENUM_TO_PY[proto_type]
        return name if name in target.local_types else "Any"
    if proto_type in PROTO_TO_PY_CLASS:
        name = PROTO_TO_PY_CLASS[proto_type]
        return name if name in target.local_types else "Any"
    return "Any"


def find_class_block(lines: list[str], class_name: str) -> tuple[int | None, int | None]:
    class_re = re.compile(rf"^class\s+{re.escape(class_name)}\b")
    start = None
    for i, line in enumerate(lines):
        if class_re.match(line):
            start = i
            break
    if start is None:
        return None, None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("class "):
            end = i
            break
    return start, end


def find_class_body_start(lines: list[str], start: int, end: int) -> int:
    i = start + 1
    # Skip empty lines
    while i < end and lines[i].strip() == "":
        i += 1
    # Docstring handling
    if i < end and lines[i].lstrip().startswith(('"""', "'''")):
        quote = '"""' if '"""' in lines[i] else "'''"
        if lines[i].count(quote) >= 2:
            return i + 1
        i += 1
        while i < end:
            if quote in lines[i]:
                return i + 1
            i += 1
    return i


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync proto/thrift fields and v2 protocol models.")
    ap.add_argument("--proto", default=str(PROTO_PATH), help="Path to v2 proto file.")
    ap.add_argument("--thrift", default=str(THRIFT_PATH), help="Path to v2 thrift file.")
    ap.add_argument("--apply", action="store_true", help="Apply updates to files.")
    ap.add_argument("--update-types", action="store_true", help="Update model field type hints.")
    args = ap.parse_args()

    proto_path = Path(args.proto)
    thrift_path = Path(args.thrift)

    schema = parse_proto(proto_path)
    thrift_text = generate_thrift(schema)

    changes: list[str] = []
    if thrift_path.exists():
        current = thrift_path.read_text(encoding="utf-8")
        if current != thrift_text:
            changes.append(str(thrift_path))
            if args.apply:
                thrift_path.write_text(thrift_text, encoding="utf-8")
    else:
        changes.append(str(thrift_path))
        if args.apply:
            thrift_path.write_text(thrift_text, encoding="utf-8")

    model_changes = sync_models(schema, args.apply, args.update_types)
    changes.extend(model_changes)

    if changes:
        print("Changes detected:")
        for item in changes:
            print(f" - {item}")
        if not args.apply:
            print("Run with --apply to write updates.")
        return 1 if not args.apply else 0

    print("No changes needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
