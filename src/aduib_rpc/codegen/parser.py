"""Proto file parser for aduib_rpc code generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ProtoEnum",
    "ProtoField",
    "ProtoFile",
    "ProtoImport",
    "ProtoMessage",
    "ProtoRpc",
    "ProtoService",
    "ProtoParseError",
    "parse_proto",
]


@dataclass(frozen=True, slots=True)
class ProtoField:
    name: str
    type_name: str
    number: int
    label: str | None = None


@dataclass(frozen=True, slots=True)
class ProtoEnumValue:
    name: str
    number: int


@dataclass(frozen=True, slots=True)
class ProtoEnum:
    name: str
    values: tuple[ProtoEnumValue, ...]


@dataclass(frozen=True, slots=True)
class ProtoMessage:
    name: str
    fields: tuple[ProtoField, ...]
    messages: tuple[ProtoMessage, ...] = ()
    enums: tuple[ProtoEnum, ...] = ()


@dataclass(frozen=True, slots=True)
class ProtoRpc:
    name: str
    request_type: str
    response_type: str
    client_streaming: bool = False
    server_streaming: bool = False


@dataclass(frozen=True, slots=True)
class ProtoService:
    name: str
    rpcs: tuple[ProtoRpc, ...]


@dataclass(frozen=True, slots=True)
class ProtoImport:
    path: str
    kind: str | None = None


@dataclass(frozen=True, slots=True)
class ProtoFile:
    path: Path
    imports: tuple[ProtoImport, ...]
    services: tuple[ProtoService, ...]
    messages: tuple[ProtoMessage, ...]
    enums: tuple[ProtoEnum, ...]
    package: str | None = None
    syntax: str | None = None


class ProtoParseError(ValueError):
    """Raised when a proto file cannot be parsed."""


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str
    line: int
    column: int


def parse_proto(file_path: Path) -> ProtoFile:
    """Parse a .proto file and return its AST representation."""
    source = file_path.read_text(encoding="utf-8")
    tokens = _tokenize(source)
    parser = _Parser(tokens)
    return parser.parse(file_path)


def _tokenize(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    length = len(source)
    index = 0
    line = 1
    column = 1

    def advance() -> str:
        nonlocal index, line, column
        ch = source[index]
        index += 1
        if ch == "\n":
            line += 1
            column = 1
        else:
            column += 1
        return ch

    while index < length:
        ch = source[index]
        if ch.isspace():
            advance()
            continue
        if ch == "/" and index + 1 < length:
            next_ch = source[index + 1]
            if next_ch == "/":
                advance()
                advance()
                while index < length and source[index] != "\n":
                    advance()
                continue
            if next_ch == "*":
                advance()
                advance()
                while index < length:
                    if source[index] == "*" and index + 1 < length and source[index + 1] == "/":
                        advance()
                        advance()
                        break
                    advance()
                continue
        if ch in "{}()[]=;<>.,":  # single-char tokens
            tokens.append(_Token("symbol", ch, line, column))
            advance()
            continue
        if ch in ("\"", "'"):
            quote = advance()
            value_chars: list[str] = []
            while index < length:
                current = advance()
                if current == quote:
                    break
                if current == "\\" and index < length:
                    escape = advance()
                    value_chars.append(
                        {
                            "n": "\n",
                            "r": "\r",
                            "t": "\t",
                            "\\": "\\",
                            "\"": "\"",
                            "'": "'",
                        }.get(escape, escape)
                    )
                else:
                    value_chars.append(current)
            else:
                raise ProtoParseError(f"Unterminated string at line {line} column {column}")
            tokens.append(_Token("string", "".join(value_chars), line, column))
            continue
        if ch == "-" and index + 1 < length and source[index + 1].isdigit():
            start_line, start_column = line, column
            value_chars = [advance()]
            while index < length and (
                source[index].isdigit() or source[index] in "xXabcdefABCDEF"
            ):
                value_chars.append(advance())
            tokens.append(_Token("number", "".join(value_chars), start_line, start_column))
            continue
        if ch.isdigit():
            start_line, start_column = line, column
            value_chars = [advance()]
            while index < length and (
                source[index].isdigit() or source[index] in "xXabcdefABCDEF"
            ):
                value_chars.append(advance())
            tokens.append(_Token("number", "".join(value_chars), start_line, start_column))
            continue
        if ch.isalpha() or ch == "_":
            start_line, start_column = line, column
            value_chars = [advance()]
            while index < length and (source[index].isalnum() or source[index] == "_"):
                value_chars.append(advance())
            tokens.append(_Token("ident", "".join(value_chars), start_line, start_column))
            continue
        raise ProtoParseError(f"Unexpected character {ch!r} at line {line} column {column}")

    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._index = 0

    def parse(self, path: Path) -> ProtoFile:
        imports: list[ProtoImport] = []
        services: list[ProtoService] = []
        messages: list[ProtoMessage] = []
        enums: list[ProtoEnum] = []
        package: str | None = None
        syntax: str | None = None

        while self._peek() is not None:
            token = self._peek()
            if token is None:
                break
            if token.kind == "ident" and token.value == "import":
                imports.append(self._parse_import())
                continue
            if token.kind == "ident" and token.value == "message":
                messages.append(self._parse_message())
                continue
            if token.kind == "ident" and token.value == "enum":
                enums.append(self._parse_enum())
                continue
            if token.kind == "ident" and token.value == "service":
                services.append(self._parse_service())
                continue
            if token.kind == "ident" and token.value == "package":
                package = self._parse_package()
                continue
            if token.kind == "ident" and token.value == "syntax":
                syntax = self._parse_syntax()
                continue
            if token.value == ";":
                self._consume()
                continue
            self._skip_statement()

        return ProtoFile(
            path=path,
            imports=tuple(imports),
            services=tuple(services),
            messages=tuple(messages),
            enums=tuple(enums),
            package=package,
            syntax=syntax,
        )

    def _parse_import(self) -> ProtoImport:
        self._expect_value("import")
        kind = None
        if self._peek() and self._peek().kind == "ident" and self._peek().value in {"weak", "public"}:
            kind = self._consume().value
        path_token = self._expect_kind("string")
        self._expect_value(";")
        return ProtoImport(path=path_token.value, kind=kind)

    def _parse_package(self) -> str:
        self._expect_value("package")
        package_name = self._parse_type_name(allow_leading_dot=False)
        self._expect_value(";")
        return package_name

    def _parse_syntax(self) -> str:
        self._expect_value("syntax")
        self._expect_value("=")
        syntax = self._expect_kind("string").value
        self._expect_value(";")
        return syntax

    def _parse_message(self) -> ProtoMessage:
        self._expect_value("message")
        name = self._expect_kind("ident").value
        self._expect_value("{")
        fields: list[ProtoField] = []
        messages: list[ProtoMessage] = []
        enums: list[ProtoEnum] = []

        while self._peek() is not None:
            token = self._peek()
            if token is None:
                break
            if token.value == "}":
                self._consume()
                break
            if token.kind == "ident" and token.value == "message":
                messages.append(self._parse_message())
                continue
            if token.kind == "ident" and token.value == "enum":
                enums.append(self._parse_enum())
                continue
            if token.kind == "ident" and token.value == "oneof":
                fields.extend(self._parse_oneof())
                continue
            if token.kind == "ident" and token.value in {"reserved", "option", "extensions", "extend"}:
                self._skip_statement()
                continue
            field = self._parse_field_safe()
            if field is not None:
                fields.append(field)
                continue
            self._skip_statement()

        return ProtoMessage(
            name=name,
            fields=tuple(fields),
            messages=tuple(messages),
            enums=tuple(enums),
        )

    def _parse_oneof(self) -> list[ProtoField]:
        self._expect_value("oneof")
        self._expect_kind("ident")
        self._expect_value("{")
        fields: list[ProtoField] = []

        while self._peek() is not None:
            token = self._peek()
            if token is None:
                break
            if token.value == "}":
                self._consume()
                break
            if token.kind == "ident" and token.value in {"option", "reserved"}:
                self._skip_statement()
                continue
            field = self._parse_field_safe(allow_label=False)
            if field is not None:
                fields.append(field)
                continue
            self._skip_statement()

        return fields

    def _parse_enum(self) -> ProtoEnum:
        self._expect_value("enum")
        name = self._expect_kind("ident").value
        self._expect_value("{")
        values: list[ProtoEnumValue] = []

        while self._peek() is not None:
            token = self._peek()
            if token is None:
                break
            if token.value == "}":
                self._consume()
                break
            if token.kind == "ident" and token.value in {"option", "reserved"}:
                self._skip_statement()
                continue
            value_name = self._expect_kind("ident").value
            self._expect_value("=")
            value_number = self._parse_number()
            if self._match_value("["):
                self._skip_bracketed("[", "]")
            self._expect_value(";")
            values.append(ProtoEnumValue(name=value_name, number=value_number))

        return ProtoEnum(name=name, values=tuple(values))

    def _parse_service(self) -> ProtoService:
        self._expect_value("service")
        name = self._expect_kind("ident").value
        self._expect_value("{")
        rpcs: list[ProtoRpc] = []

        while self._peek() is not None:
            token = self._peek()
            if token is None:
                break
            if token.value == "}":
                self._consume()
                break
            if token.kind == "ident" and token.value == "rpc":
                rpcs.append(self._parse_rpc())
                continue
            if token.kind == "ident" and token.value == "option":
                self._skip_statement()
                continue
            self._skip_statement()

        return ProtoService(name=name, rpcs=tuple(rpcs))

    def _parse_rpc(self) -> ProtoRpc:
        self._expect_value("rpc")
        name = self._expect_kind("ident").value
        self._expect_value("(")
        client_streaming = self._match_keyword("stream")
        request_type = self._parse_type_name()
        self._expect_value(")")
        self._expect_value("returns")
        self._expect_value("(")
        server_streaming = self._match_keyword("stream")
        response_type = self._parse_type_name()
        self._expect_value(")")
        if self._match_value(";"):
            return ProtoRpc(
                name=name,
                request_type=request_type,
                response_type=response_type,
                client_streaming=client_streaming,
                server_streaming=server_streaming,
            )
        if self._match_value("{"):
            self._skip_bracketed("{", "}")
        return ProtoRpc(
            name=name,
            request_type=request_type,
            response_type=response_type,
            client_streaming=client_streaming,
            server_streaming=server_streaming,
        )

    def _parse_field_safe(self, allow_label: bool = True) -> ProtoField | None:
        start_index = self._index
        try:
            return self._parse_field(allow_label=allow_label)
        except ProtoParseError:
            self._index = start_index
            return None

    def _parse_field(self, allow_label: bool = True) -> ProtoField:
        label = None
        if allow_label and self._peek() and self._peek().kind == "ident":
            if self._peek().value in {"repeated", "optional", "required"}:
                label = self._consume().value
        if self._peek() and self._peek().kind == "ident" and self._peek().value == "map":
            type_name = self._parse_map_type()
        else:
            type_name = self._parse_type_name()
        name = self._expect_kind("ident").value
        self._expect_value("=")
        number = self._parse_number()
        if self._match_value("["):
            self._skip_bracketed("[", "]")
        self._expect_value(";")
        return ProtoField(name=name, type_name=type_name, number=number, label=label)

    def _parse_map_type(self) -> str:
        self._expect_value("map")
        self._expect_value("<")
        key_type = self._parse_type_name()
        self._expect_value(",")
        value_type = self._parse_type_name()
        self._expect_value(">")
        return f"map<{key_type}, {value_type}>"

    def _parse_type_name(self, allow_leading_dot: bool = True) -> str:
        leading_dot = False
        if allow_leading_dot and self._match_value("."):
            leading_dot = True
        parts = [self._expect_kind("ident").value]
        while self._match_value("."):
            parts.append(self._expect_kind("ident").value)
        name = ".".join(parts)
        return f".{name}" if leading_dot else name

    def _parse_number(self) -> int:
        token = self._expect_kind("number")
        try:
            return int(token.value, 0)
        except ValueError as exc:
            raise ProtoParseError(
                f"Invalid number {token.value!r} at line {token.line} column {token.column}"
            ) from exc

    def _skip_statement(self) -> None:
        stack: list[str] = []
        while self._peek() is not None:
            if self._peek().value == "}" and not stack:
                return
            token = self._consume()
            if token.value in {"{", "[", "("}:
                stack.append({"{": "}", "[": "]", "(": ")"}[token.value])
                continue
            if token.value in {"}", "]", ")"}:
                if stack and token.value == stack[-1]:
                    stack.pop()
                    if not stack and token.value == "}":
                        return
                continue
            if token.value == ";" and not stack:
                return

    def _skip_bracketed(self, opening: str, closing: str) -> None:
        depth = 1
        while self._peek() is not None:
            token = self._consume()
            if token.value == opening:
                depth += 1
            elif token.value == closing:
                depth -= 1
                if depth == 0:
                    return
        raise ProtoParseError(f"Unterminated block starting with {opening!r}")

    def _match_keyword(self, value: str) -> bool:
        if self._peek() and self._peek().kind == "ident" and self._peek().value == value:
            self._consume()
            return True
        return False

    def _match_value(self, value: str) -> bool:
        if self._peek() and self._peek().value == value:
            self._consume()
            return True
        return False

    def _expect_value(self, value: str) -> _Token:
        token = self._consume()
        if token.value != value:
            raise ProtoParseError(
                f"Expected {value!r} at line {token.line} column {token.column}, got {token.value!r}"
            )
        return token

    def _expect_kind(self, kind: str) -> _Token:
        token = self._consume()
        if token.kind != kind:
            raise ProtoParseError(
                f"Expected {kind} at line {token.line} column {token.column}, got {token.kind}"
            )
        return token

    def _consume(self) -> _Token:
        if self._index >= len(self._tokens):
            raise ProtoParseError("Unexpected end of input")
        token = self._tokens[self._index]
        self._index += 1
        return token

    def _peek(self) -> _Token | None:
        if self._index >= len(self._tokens):
            return None
        return self._tokens[self._index]
