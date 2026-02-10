"""Content negotiation and compression handling for Protocol v2.

Per spec v2 sections 2.3 and 3.2:
- Content negotiation based on Accept header/metadata.accept
- Compression negotiation based on Accept-Encoding/metadata.compression
- Serialization support for JSON, MessagePack, Protobuf, Avro
- Compression support for gzip, zstd, lz4

Implementation:
- Negotiates best matching content type from client accept list
- Applies compression based on client preference and server capability
- Provides serialization/deserialization helpers
"""
from __future__ import annotations

import gzip
import json
import logging
from typing import Any, Callable

from aduib_rpc.protocol.v2.metadata import (
    Compression,
    ContentType,
)

logger = logging.getLogger(__name__)

# Serialization type hints
Serializer = Callable[[Any], bytes]
Deserializer = Callable[[bytes], Any]
Compressor = Callable[[bytes], bytes]
Decompressor = Callable[[bytes], bytes]

# Default supported content types (server can override)
DEFAULT_CONTENT_TYPES = [
    ContentType.JSON,
    ContentType.MSGPACK,
    ContentType.PROTOBUF,
    ContentType.AVRO,
]

# Default supported compression (server can override)
DEFAULT_COMPRESSION = [
    Compression.GZIP,
    Compression.ZSTD,
    Compression.LZ4,
]


class SerializationError(Exception):
    """Raised when serialization fails."""
    pass


class DeserializationError(Exception):
    """Raised when deserialization fails."""
    pass


class CompressionError(Exception):
    """Raised when compression fails."""
    pass


class DecompressionError(Exception):
    """Raised when decompression fails."""
    pass


# =============================================================================
# Serialization Functions
# =============================================================================

def serialize_json(data: Any) -> bytes:
    """Serialize data to JSON bytes."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def deserialize_json(data: bytes) -> Any:
    """Deserialize JSON bytes to Python object."""
    try:
        return json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise DeserializationError(f"Failed to decode JSON: {e}") from e


def serialize_msgpack(data: Any) -> bytes:
    """Serialize data to MessagePack format.

    Requires msgpack package.
    """
    try:
        import msgpack
    except ImportError:
        raise SerializationError("msgpack package is required for MessagePack serialization")

    try:
        return msgpack.packb(data, use_bin_type=True)
    except (msgpack.PackException, TypeError) as e:
        raise SerializationError(f"Failed to encode MessagePack: {e}") from e


def deserialize_msgpack(data: bytes) -> Any:
    """Deserialize MessagePack bytes to Python object."""
    try:
        import msgpack
    except ImportError:
        raise DeserializationError("msgpack package is required for MessagePack deserialization")

    try:
        return msgpack.unpackb(data, raw=False)
    except (msgpack.UnpackException, TypeError) as e:
        raise DeserializationError(f"Failed to decode MessagePack: {e}") from e


def serialize_protobuf(data: Any) -> bytes:
    """Serialize data to Protobuf format.

    Note: This is a placeholder. Actual implementation requires
    generated protobuf classes.
    """
    raise SerializationError("Protobuf serialization requires generated protobuf classes")


def deserialize_protobuf(data: bytes) -> Any:
    """Deserialize Protobuf bytes to Python object.

    Note: This is a placeholder. Actual implementation requires
    generated protobuf classes.
    """
    raise DeserializationError("Protobuf deserialization requires generated protobuf classes")


def serialize_avro(data: Any) -> bytes:
    """Serialize data to Avro format.

    Requires avro package.
    """
    try:
        import avro.schema as avro_schema
        from avro.io import DatumWriter, BinaryEncoder
    except ImportError:
        raise SerializationError("avro package is required for Avro serialization")

    _ = (avro_schema, DatumWriter, BinaryEncoder)
    raise SerializationError("Avro serialization requires schema and DatumWriter")


def deserialize_avro(data: bytes) -> Any:
    """Deserialize Avro bytes to Python object."""
    try:
        import avro.schema as avro_schema
        from avro.io import DatumReader, BinaryDecoder
    except ImportError:
        raise DeserializationError("avro package is required for Avro deserialization")

    _ = (avro_schema, DatumReader, BinaryDecoder)
    raise DeserializationError("Avro deserialization requires schema and DatumReader")


# Serializer registry
_SERIALIZERS: dict[ContentType, Serializer] = {
    ContentType.JSON: serialize_json,
    ContentType.MSGPACK: serialize_msgpack,
    ContentType.PROTOBUF: serialize_protobuf,
    ContentType.AVRO: serialize_avro,
}

_DESERIALIZERS: dict[ContentType, Deserializer] = {
    ContentType.JSON: deserialize_json,
    ContentType.MSGPACK: deserialize_msgpack,
    ContentType.PROTOBUF: deserialize_protobuf,
    ContentType.AVRO: deserialize_avro,
}


def get_serializer(content_type: ContentType) -> Serializer:
    """Get serializer function for content type.

    Args:
        content_type: The content type.

    Returns:
        Serializer function.

    Raises:
        SerializationError: If content type is not supported.
    """
    serializer = _SERIALIZERS.get(content_type)
    if serializer is None:
        raise SerializationError(f"No serializer for content type: {content_type}")
    return serializer


def get_deserializer(content_type: ContentType) -> Deserializer:
    """Get deserializer function for content type.

    Args:
        content_type: The content type.

    Returns:
        Deserializer function.

    Raises:
        DeserializationError: If content type is not supported.
    """
    deserializer = _DESERIALIZERS.get(content_type)
    if deserializer is None:
        raise DeserializationError(f"No deserializer for content type: {content_type}")
    return deserializer


# =============================================================================
# Compression Functions
# =============================================================================

def compress_gzip(data: bytes, level: int = 6) -> bytes:
    """Compress data using gzip.

    Args:
        data: Input data.
        level: Compression level (0-9).

    Returns:
        Compressed data.
    """
    return gzip.compress(data, compresslevel=level)


def decompress_gzip(data: bytes) -> bytes:
    """Decompress gzip data.

    Args:
        data: Compressed data.

    Returns:
        Decompressed data.

    Raises:
        DecompressionError: If decompression fails.
    """
    try:
        return gzip.decompress(data)
    except OSError as e:
        raise DecompressionError(f"Failed to decompress gzip: {e}") from e


def compress_zstd(data: bytes, level: int = 3) -> bytes:
    """Compress data using zstandard.

    Requires zstandard package.

    Args:
        data: Input data.
        level: Compression level (0-22).

    Returns:
        Compressed data.
    """
    try:
        import zstandard as zstd
    except ImportError:
        raise CompressionError("zstandard package is required for zstd compression")

    try:
        cctx = zstd.ZstdCompressor(level=level)
        return cctx.compress(data)
    except zstd.ZstdError as e:
        raise CompressionError(f"Failed to compress with zstd: {e}") from e


def decompress_zstd(data: bytes) -> bytes:
    """Decompress zstandard data.

    Args:
        data: Compressed data.

    Returns:
        Decompressed data.

    Raises:
        DecompressionError: If decompression fails.
    """
    try:
        import zstandard as zstd
    except ImportError:
        raise DecompressionError("zstandard package is required for zstd decompression")

    try:
        dctx = zstd.ZstdDecompressor()
        return dctx.decompress(data)
    except zstd.ZstdError as e:
        raise DecompressionError(f"Failed to decompress zstd: {e}") from e


def compress_lz4(data: bytes, level: int = 4) -> bytes:
    """Compress data using lz4.

    Requires lz4 package.

    Args:
        data: Input data.
        level: Compression level (0-16).

    Returns:
        Compressed data.
    """
    try:
        import lz4.frame
    except ImportError:
        raise CompressionError("lz4 package is required for lz4 compression")

    try:
        return lz4.frame.compress(data, compression_level=level)
    except (OSError, ValueError) as e:
        raise CompressionError(f"Failed to compress with lz4: {e}") from e


def decompress_lz4(data: bytes) -> bytes:
    """Decompress lz4 data.

    Args:
        data: Compressed data.

    Returns:
        Decompressed data.

    Raises:
        DecompressionError: If decompression fails.
    """
    try:
        import lz4.frame
    except ImportError:
        raise DecompressionError("lz4 package is required for lz4 decompression")

    try:
        return lz4.frame.decompress(data)
    except (OSError, ValueError) as e:
        raise DecompressionError(f"Failed to decompress lz4: {e}") from e


# Compressor registry
_COMPRESSORS: dict[Compression, Compressor] = {
    Compression.GZIP: compress_gzip,
    Compression.ZSTD: compress_zstd,
    Compression.LZ4: compress_lz4,
}

_DECOMPRESSORS: dict[Compression, Decompressor] = {
    Compression.GZIP: decompress_gzip,
    Compression.ZSTD: decompress_zstd,
    Compression.LZ4: decompress_lz4,
}


def get_compressor(compression: Compression) -> Compressor:
    """Get compressor function for compression type.

    Args:
        compression: The compression type.

    Returns:
        Compressor function.

    Raises:
        CompressionError: If compression type is not supported.
    """
    if compression == Compression.NONE:
        return lambda data: data

    compressor = _COMPRESSORS.get(compression)
    if compressor is None:
        raise CompressionError(f"No compressor for: {compression}")
    return compressor


def get_decompressor(compression: Compression) -> Decompressor:
    """Get decompressor function for compression type.

    Args:
        compression: The compression type.

    Returns:
        Decompressor function.

    Raises:
        DecompressionError: If compression type is not supported.
    """
    if compression == Compression.NONE:
        return lambda data: data

    decompressor = _DECOMPRESSORS.get(compression)
    if decompressor is None:
        raise DecompressionError(f"No decompressor for: {compression}")
    return decompressor


# =============================================================================
# Content Negotiation
# =============================================================================

class ContentNegotiator:
    """Handles content type negotiation between client and server.

    The client sends an accept list (or Accept header) and the server
    selects the best matching content type it supports.
    """

    def __init__(
        self,
        supported_types: list[ContentType] | None = None,
        default_type: ContentType = ContentType.JSON,
    ):
        """Initialize the negotiator.

        Args:
            supported_types: Content types the server can produce.
            default_type: Default fallback type.
        """
        self.supported_types = supported_types or DEFAULT_CONTENT_TYPES
        self.default_type = default_type

    def negotiate(
        self,
        accept: list[ContentType] | None = None,
        accept_header: str | None = None,
    ) -> ContentType:
        """Negotiate the best content type.

        Args:
            accept: Client's accepted content types from metadata.
            accept_header: Accept header value (parsed from HTTP).

        Returns:
            The negotiated content type.

        Raises:
            ValueError: If no acceptable content type found.
        """
        # Build client accept list
        client_accept: list[ContentType] = []
        if accept:
            client_accept.extend(accept)
        if accept_header:
            # Parse Accept header like "application/json, application/msgpack"
            for part in accept_header.split(","):
                part = part.strip()
                # Remove q-value parameters if present
                part = part.split(";")[0].strip()
                try:
                    client_accept.append(ContentType(part))
                except ValueError:
                    continue

        # If client didn't specify, use default
        if not client_accept:
            return self.default_type

        # Find first match (client priority order)
        for ct in client_accept:
            if ct in self.supported_types:
                return ct

        # No match - return default
        return self.default_type


class CompressionNegotiator:
    """Handles compression negotiation between client and server.

    The client sends a preferred compression (or Accept-Encoding header)
    and the server selects the best matching compression it supports.
    """

    def __init__(
        self,
        supported_compression: list[Compression] | None = None,
        default_compression: Compression = Compression.NONE,
    ):
        """Initialize the negotiator.

        Args:
            supported_compression: Compression types the server supports.
            default_compression: Default fallback (no compression).
        """
        self.supported_compression = supported_compression or DEFAULT_COMPRESSION
        self.default_compression = default_compression

    def negotiate(
        self,
        compression: Compression | None = None,
        accept_encoding_header: str | None = None,
    ) -> Compression:
        """Negotiate the best compression type.

        Args:
            compression: Client's preferred compression from metadata.
            accept_encoding_header: Accept-Encoding header value.

        Returns:
            The negotiated compression type.
        """
        # Priority: explicit metadata > Accept-Encoding header > default
        if compression and compression != Compression.NONE:
            if compression in self.supported_compression:
                return compression

        if accept_encoding_header:
            # Parse Accept-Encoding like "gzip, deflate, br"
            for part in accept_encoding_header.split(","):
                part = part.strip().lower()
                # Remove q-value parameters
                part = part.split(";")[0].strip()
                try:
                    if part == "gzip" and Compression.GZIP in self.supported_compression:
                        return Compression.GZIP
                    elif part == "zstd" and Compression.ZSTD in self.supported_compression:
                        return Compression.ZSTD
                    elif part == "lz4" and Compression.LZ4 in self.supported_compression:
                        return Compression.LZ4
                    elif part in ("identity", "none"):
                        return Compression.NONE
                except ValueError:
                    continue

        return self.default_compression


# =============================================================================
# Combined Serialization + Compression
# =============================================================================

def encode(
    data: Any,
    content_type: ContentType = ContentType.JSON,
    compression: Compression | None = None,
) -> bytes:
    """Encode data with serialization and optional compression.

    Args:
        data: The data to encode.
        content_type: Target content type.
        compression: Optional compression to apply.

    Returns:
        Encoded (and possibly compressed) bytes.
    """
    # Serialize
    serializer = get_serializer(content_type)
    serialized = serializer(data)

    # Compress if requested
    if compression and compression != Compression.NONE:
        compressor = get_compressor(compression)
        try:
            serialized = compressor(serialized)
        except CompressionError:
            # Fall back to uncompressed if compression fails
            logger.warning(f"Compression {compression} failed, sending uncompressed")

    return serialized


def decode(
    data: bytes,
    content_type: ContentType = ContentType.JSON,
    compression: Compression | None = None,
) -> Any:
    """Decode data with decompression and deserialization.

    Args:
        data: The data to decode.
        content_type: Source content type.
        compression: Compression that was applied.

    Returns:
        Decoded Python object.

    Raises:
        DeserializationError: If deserialization fails.
        DecompressionError: If decompression fails.
    """
    # Decompress if needed
    if compression and compression != Compression.NONE:
        decompressor = get_decompressor(compression)
        data = decompressor(data)

    # Deserialize
    deserializer = get_deserializer(content_type)
    return deserializer(data)

