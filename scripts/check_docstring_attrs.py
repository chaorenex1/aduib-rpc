#!/usr/bin/env python
"""Check class docstring Attributes sections against class fields."""

from __future__ import annotations

import argparse
import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path


ATTRIBUTE_HEADER = re.compile(r"^\s*Attributes\s*:\s*$")
SECTION_HEADER = re.compile(
    r"^\s*(Args|Arguments|Parameters|Returns|Raises|Yields|Examples|Notes|See Also|Properties)\s*:\s*$"
)


@dataclass
class Mismatch:
    path: Path
    class_name: str
    line: int
    missing: list[str]
    extra: list[str]


def parse_attributes_section(docstring: str | None) -> list[str]:
    if not docstring:
        return []
    lines = docstring.splitlines()
    for idx, line in enumerate(lines):
        if ATTRIBUTE_HEADER.match(line):
            attrs: list[str] = []
            i = idx + 1
            while i < len(lines):
                current = lines[i]
                if SECTION_HEADER.match(current) or ATTRIBUTE_HEADER.match(current):
                    break
                if current.strip() == "":
                    i += 1
                    if i < len(lines) and lines[i].strip() == "":
                        break
                    continue
                match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*", current)
                if match:
                    attrs.append(match.group(1))
                i += 1
            return attrs
    return []


def is_classvar(annotation: ast.AST | None) -> bool:
    if annotation is None:
        return False
    node = annotation
    if isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id == "ClassVar"
    if isinstance(node, ast.Attribute):
        return node.attr == "ClassVar"
    return False


def collect_class_fields(node: ast.ClassDef) -> list[str]:
    fields: list[str] = []
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            if is_classvar(stmt.annotation):
                continue
            fields.append(stmt.target.id)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    fields.append(target.id)
    return fields


def iter_py_files(root: Path, exclude_dirs: set[str]) -> list[Path]:
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for filename in filenames:
            if filename.endswith(".py"):
                results.append(Path(dirpath) / filename)
    return results


def check_paths(paths: list[Path], exclude_dirs: set[str]) -> tuple[list[Mismatch], list[Path]]:
    mismatches: list[Mismatch] = []
    parse_errors: list[Path] = []
    for path in paths:
        if path.is_dir():
            py_files = iter_py_files(path, exclude_dirs)
        elif path.suffix == ".py":
            py_files = [path]
        else:
            continue
        for py_file in py_files:
            try:
                source = py_file.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                parse_errors.append(py_file)
                continue
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                doc = ast.get_docstring(node)
                attrs = parse_attributes_section(doc)
                if not attrs:
                    continue
                fields = [f for f in collect_class_fields(node) if not f.startswith("_")]
                missing = sorted(set(fields) - set(attrs))
                extra = sorted(set(attrs) - set(fields))
                if missing or extra:
                    mismatches.append(
                        Mismatch(
                            path=py_file,
                            class_name=node.name,
                            line=node.lineno,
                            missing=missing,
                            extra=extra,
                        )
                    )
    return mismatches, parse_errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Check class Attributes docstrings against class fields.")
    parser.add_argument(
        "paths",
        nargs="*",
        default=["src"],
        help="Files or directories to scan (default: src).",
    )
    parser.add_argument(
        "--include-generated",
        action="store_true",
        help="Include generated code directories such as thrift_v2 and grpc.",
    )
    args = parser.parse_args()

    exclude_dirs = {
        ".git",
        ".venv",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        "dist",
        "build",
    }
    if not args.include_generated:
        exclude_dirs.update({"thrift_v2", "grpc"})

    paths = [Path(p) for p in args.paths]
    mismatches, parse_errors = check_paths(paths, exclude_dirs)

    if mismatches:
        print("Docstring attribute mismatches:")
        for mismatch in mismatches:
            rel = mismatch.path.as_posix()
            print(f"- {rel}:{mismatch.line}::{mismatch.class_name}")
            if mismatch.missing:
                print(f"  missing_in_doc: {', '.join(mismatch.missing)}")
            if mismatch.extra:
                print(f"  extra_in_doc: {', '.join(mismatch.extra)}")

    if parse_errors:
        print("Parse errors:")
        for path in parse_errors:
            print(f"- {path.as_posix()}")

    if mismatches:
        return 1
    if parse_errors:
        return 2
    print("No docstring attribute mismatches found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
