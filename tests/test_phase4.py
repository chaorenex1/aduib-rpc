"""Tests for Phase 4: Developer Experience enhancements.

Tests CLI tool, code generator, and documentation components.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from aduib_rpc.cli import build_parser, main
from aduib_rpc.cli.commands.health import _parse_target, EXIT_HEALTHY
from aduib_rpc.cli.commands.discover import _get_registry, _print_instances_json
from aduib_rpc.cli.commands.config import _get_nested_value, _set_nested_value, _validate_config_structure
from aduib_rpc.codegen import (
    ProtoEnum,
    ProtoEnumValue,
    ProtoField,
    ProtoFile,
    ProtoImport,
    ProtoMessage,
    ProtoRpc,
    ProtoService,
    parse_proto,
)
from aduib_rpc.codegen.generators import (
    generate_client_code,
    generate_server_code,
    generate_type_code,
)


class TestCLIParser:
    """Test CLI parser construction."""

    def test_build_parser_creates_subparsers(self) -> None:
        """Test that parser has all expected subcommands."""
        parser = build_parser()

        # Test help without arguments
        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])

    def test_health_command_parsing(self) -> None:
        """Test health command argument parsing."""
        parser = build_parser()
        args = parser.parse_args(["health", "localhost:8080"])

        assert args.command == "health"
        assert args.target == "localhost:8080"
        assert args.protocol == "http"  # default
        assert args.path == "/health"  # default

    def test_health_command_with_options(self) -> None:
        """Test health command with all options."""
        parser = build_parser()
        args = parser.parse_args([
            "health", "localhost:9090",
            "--protocol", "grpc",
            "--timeout", "10",
            "--path", "/healthz",
            "--format", "json",
        ])

        assert args.target == "localhost:9090"
        assert args.protocol == "grpc"
        assert args.timeout == 10.0
        assert args.path == "/healthz"
        assert args.format == "json"

    def test_discover_list_command_parsing(self) -> None:
        """Test discover list command parsing."""
        parser = build_parser()
        args = parser.parse_args(["discover", "list", "my-service"])

        assert args.command == "discover"
        assert args.subcommand == "list"
        assert args.service_name == "my-service"

    def test_discover_services_command_parsing(self) -> None:
        """Test discover services command parsing."""
        parser = build_parser()
        args = parser.parse_args(["discover", "services"])

        assert args.command == "discover"
        assert args.subcommand == "services"

    def test_config_validate_command_parsing(self) -> None:
        """Test config validate command parsing."""
        parser = build_parser()
        args = parser.parse_args(["config", "validate", "config.yaml"])

        assert args.command == "config"
        assert args.subcommand == "validate"
        assert isinstance(args.config_file, Path)

    def test_config_get_command_parsing(self) -> None:
        """Test config get command parsing."""
        parser = build_parser()
        args = parser.parse_args(["config", "get", "aduib.rpc.timeout"])

        assert args.command == "config"
        assert args.subcommand == "get"
        assert args.key == "aduib.rpc.timeout"

    def test_config_set_command_parsing(self) -> None:
        """Test config set command parsing."""
        parser = build_parser()
        args = parser.parse_args([
            "config", "set",
            "aduib.rpc.timeout",
            "30000",
            "--config-file", "config.yaml",
        ])

        assert args.command == "config"
        assert args.subcommand == "set"
        assert args.key == "aduib.rpc.timeout"
        assert args.value == "30000"


class TestHealthCommand:
    """Test health command utilities."""

    def test_parse_target_valid(self) -> None:
        """Test parsing valid host:port targets."""
        assert _parse_target("localhost:8080") == ("localhost", 8080)
        assert _parse_target("example.com:443") == ("example.com", 443)
        assert _parse_target("192.168.1.1:80") == ("192.168.1.1", 80)

    def test_parse_target_invalid_format(self) -> None:
        """Test parsing invalid target format."""
        with pytest.raises(ValueError, match="Invalid target"):
            _parse_target("localhost")

    def test_parse_target_invalid_port(self) -> None:
        """Test parsing invalid port."""
        with pytest.raises(ValueError, match="Invalid port"):
            _parse_target("localhost:abc")

        with pytest.raises(ValueError, match="must be between 1 and 65535"):
            _parse_target("localhost:0")

        with pytest.raises(ValueError, match="must be between 1 and 65535"):
            _parse_target("localhost:99999")


class TestDiscoverCommand:
    """Test discover command utilities."""

    def test_get_registry_memory(self) -> None:
        """Test getting in-memory registry."""
        registry = _get_registry("memory")
        assert registry is not None
        assert hasattr(registry, "list_instances")

    def test_print_instances_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test JSON output format for instances."""
        instance = Mock()
        instance.host = "localhost"
        instance.port = 8080
        instance.service_name = "test-service"
        instance.weight = 1
        instance.protocol = "http"
        instance.scheme = "http"
        instance.metadata = {"version": "1.0"}

        _print_instances_json([instance], show_metadata=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert len(data) == 1
        assert data[0]["host"] == "localhost"
        assert data[0]["port"] == 8080
        assert data[0]["metadata"]["version"] == "1.0"


class TestConfigCommand:
    """Test config command utilities."""

    def test_get_nested_value_simple(self) -> None:
        """Test getting simple nested value."""
        data = {"aduib_rpc": {"timeout": 30}}
        assert _get_nested_value(data, "aduib_rpc.timeout") == 30

    def test_get_nested_value_deep(self) -> None:
        """Test getting deeply nested value."""
        data = {"level1": {"level2": {"level3": "value"}}}
        assert _get_nested_value(data, "level1.level2.level3") == "value"

    def test_get_nested_value_missing(self) -> None:
        """Test getting missing nested value."""
        data = {"level1": {"level2": {}}}
        assert _get_nested_value(data, "level1.level2.missing") is None

    def test_set_nested_value_simple(self) -> None:
        """Test setting simple nested value."""
        data = {}
        _set_nested_value(data, "aduib_rpc.timeout", 30)
        assert data["aduib_rpc"]["timeout"] == 30

    def test_set_nested_value_existing(self) -> None:
        """Test setting existing nested value."""
        data = {"aduib_rpc": {"timeout": 10}}
        _set_nested_value(data, "aduib_rpc.timeout", 30)
        assert data["aduib_rpc"]["timeout"] == 30

    def test_validate_config_structure_valid(self) -> None:
        """Test validation of valid configuration."""
        data = {
            "aduib_rpc": {
                "runtime": {
                    "timeout_ms": 30000,
                    "max_connections": 100,
                }
            }
        }
        errors = _validate_config_structure(data)
        assert len(errors) == 0

    def test_validate_config_structure_invalid_timeout(self) -> None:
        """Test validation with invalid timeout."""
        data = {
            "aduib_rpc": {
                "runtime": {
                    "timeout_ms": -100,
                }
            }
        }
        errors = _validate_config_structure(data)
        assert len(errors) > 0
        assert any("timeout_ms" in e for e in errors)

    def test_validate_config_structure_invalid_type(self) -> None:
        """Test validation with wrong top-level type."""
        errors = _validate_config_structure("not a dict")
        assert len(errors) == 1
        assert "must be a dictionary" in errors[0]


class TestProtoParser:
    """Test Proto file parser."""

    def test_parse_simple_service(self, tmp_path: Path) -> None:
        """Test parsing a simple service definition."""
        proto_file = tmp_path / "test.proto"
        proto_file.write_text("""
syntax = "proto3";

service TestService {
    rpc GetData (GetDataRequest) returns (GetDataResponse);
    rpc SetValue (SetValueRequest) returns (Empty);
}

message GetDataRequest {
    string id = 1;
}

message GetDataResponse {
    string data = 1;
}

message SetValueRequest {
    string id = 1;
    string value = 2;
}

message Empty {}
""")

        result = parse_proto(proto_file)

        assert result.syntax == "proto3"
        assert len(result.services) == 1
        assert result.services[0].name == "TestService"
        assert len(result.services[0].rpcs) == 2

        # Check first RPC
        rpc = result.services[0].rpcs[0]
        assert rpc.name == "GetData"
        assert rpc.request_type == "GetDataRequest"
        assert rpc.response_type == "GetDataResponse"

    def test_parse_message_with_fields(self, tmp_path: Path) -> None:
        """Test parsing message with various field types."""
        proto_file = tmp_path / "test.proto"
        proto_file.write_text("""
syntax = "proto3";

message ComplexMessage {
    string name = 1;
    int32 count = 2;
    bool flag = 3;
    repeated string items = 4;
    map<string, int32> values = 5;
}
""")

        result = parse_proto(proto_file)

        assert len(result.messages) == 1
        msg = result.messages[0]
        assert msg.name == "ComplexMessage"
        assert len(msg.fields) == 5

        # Check field types
        field_types = {f.name: f.type_name for f in msg.fields}
        assert field_types["name"] == "string"
        assert field_types["count"] == "int32"
        assert field_types["flag"] == "bool"
        assert field_types["items"] == "string"  # repeated prefix in type
        assert "map<string, int32>" in field_types["values"]

    def test_parse_enum(self, tmp_path: Path) -> None:
        """Test parsing enum definition."""
        proto_file = tmp_path / "test.proto"
        proto_file.write_text("""
syntax = "proto3";

enum Status {
    UNKNOWN = 0;
    OK = 1;
    ERROR = 2;
}
""")

        result = parse_proto(proto_file)

        assert len(result.enums) == 1
        enum = result.enums[0]
        assert enum.name == "Status"
        assert len(enum.values) == 3

        value_names = {v.name: v.number for v in enum.values}
        assert value_names["UNKNOWN"] == 0
        assert value_names["OK"] == 1
        assert value_names["ERROR"] == 2

    def test_parse_imports(self, tmp_path: Path) -> None:
        """Test parsing import statements."""
        proto_file = tmp_path / "test.proto"
        proto_file.write_text("""
syntax = "proto3";

import "common.proto";
import public "api.proto";
""")

        result = parse_proto(proto_file)

        assert len(result.imports) == 2
        import_paths = {i.path for i in result.imports}
        assert "common.proto" in import_paths
        assert "api.proto" in import_paths


class TestCodegenClient:
    """Test client code generator."""

    def test_generate_client_code_simple(self) -> None:
        """Test generating simple client code."""
        methods = [
            {"name": "GetData", "request_type": "GetDataRequest", "response_type": "GetDataResponse"},
            {"name": "SetValue", "request_type": "SetValueRequest", "response_type": "Empty"},
        ]

        code = generate_client_code("TestService", methods)

        assert "class TestServiceClient:" in code
        assert "async def GetData(" in code
        assert "async def SetValue(" in code
        assert "GetDataRequest" in code
        assert "GetDataResponse" in code

    def test_generate_client_includes_context_manager(self) -> None:
        """Test that generated client includes async context manager."""
        methods = [{"name": "Ping", "request_type": "Empty", "response_type": "Empty"}]

        code = generate_client_code("PingService", methods)

        assert "async def __aenter__" in code
        assert "async def __aexit__" in code
        assert "async def close" in code


class TestCodegenServer:
    """Test server code generator."""

    def test_generate_server_abstract_class(self) -> None:
        """Test generating abstract service class."""
        methods = [
            {"name": "GetData", "request_type": "GetDataRequest", "response_type": "GetDataResponse"},
        ]

        code = generate_server_code("TestService", methods, generate_impl=False)

        assert "class TestServiceService(ABC):" in code
        assert "@abstractmethod" in code
        assert "raise NotImplementedError" in code

    def test_generate_server_impl_class(self) -> None:
        """Test generating implementation class."""
        methods = [
            {"name": "Process", "request_type": "Request", "response_type": "Response"},
        ]

        code = generate_server_code("ProcessorService", methods, generate_impl=True)

        assert "class ProcessorServiceImpl(" in code
        assert "# TODO: Implement Process" in code


class TestCodegenTypes:
    """Test type code generator."""

    def test_generate_pydantic_models(self) -> None:
        """Test generating Pydantic models."""
        messages = [
            {
                "name": "User",
                "fields": [
                    {"name": "id", "type": "string", "default": '""'},
                    {"name": "age", "type": "int32", "default": "0"},
                    {"name": "active", "type": "bool", "default": "true"},
                ],
            }
        ]

        code = generate_type_code(messages, use_pydantic=True)

        assert "from pydantic import BaseModel" in code
        assert "class User(BaseModel):" in code

    def test_generate_dataclasses(self) -> None:
        """Test generating dataclasses."""
        messages = [
            {
                "name": "Point",
                "fields": [
                    {"name": "x", "type": "double", "default": "0.0"},
                    {"name": "y", "type": "double", "default": "0.0"},
                ],
            }
        ]

        code = generate_type_code(messages, use_pydantic=False)

        assert "@dataclass" in code
        assert "class Point:" in code

    def test_generate_enums(self) -> None:
        """Test generating enums."""
        enums = [
            {
                "name": "Status",
                "values": [
                    {"name": "UNKNOWN", "number": 0},
                    {"name": "OK", "number": 1},
                    {"name": "ERROR", "number": 2},
                ],
            }
        ]

        code = generate_type_code(messages=[], enums=enums, use_pydantic=False)

        assert "class Status(str):" in code
        assert 'UNKNOWN = "UNKNOWN"' in code
        assert 'OK = "OK"' in code
