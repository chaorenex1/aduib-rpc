from __future__ import annotations

"""mTLS helpers for configuring SSL contexts and verifying peer certificates.

This module provides:
- TlsConfig for both client and server-side TLS configuration
- Server-side SSL context creation with mTLS support
- Principal extraction from peer certificates
- Certificate information sanitization for audit logging
"""

import enum
import hashlib
import ssl
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
class TlsVersion(str, enum.Enum):
    """Supported TLS protocol versions."""

    TLSv1_2 = "TLSv1.2"
    TLSv1_3 = "TLSv1.3"


_TLS_VERSION_MAP: dict[TlsVersion, ssl.TLSVersion] = {
    TlsVersion.TLSv1_2: ssl.TLSVersion.TLSv1_2,
    TlsVersion.TLSv1_3: ssl.TLSVersion.TLSv1_3,
}


@dataclass(frozen=True, slots=True)
class TlsConfig:
    """TLS configuration for creating client SSL contexts.

    Args:
        ca_cert_path: Optional custom CA bundle to trust.
        client_cert_path: Optional client certificate path for mTLS.
        client_key_path: Optional client private key path for mTLS.
        client_key_password: Optional password for encrypted private keys.
        minimum_version: Minimum TLS version to allow.
        maximum_version: Maximum TLS version to allow.
        check_hostname: Whether to check hostnames during verification.
        verify_mode: SSL verification mode to apply to the context.
        ciphers: Optional OpenSSL cipher string to enforce.
        ca_cert_pem: Optional PEM content for CA certificate. Takes precedence over ca_cert_path.
        client_cert_pem: Optional PEM content for client certificate. Takes precedence over client_cert_path.
        client_key_pem: Optional PEM content for client private key. Takes precedence over client_key_path.
    """

    ca_cert_path: Path | None = None
    client_cert_path: Path | None = None
    client_key_path: Path | None = None
    client_key_password: str | None = None
    minimum_version: TlsVersion = TlsVersion.TLSv1_2
    maximum_version: TlsVersion | None = None
    check_hostname: bool = True
    verify_mode: ssl.VerifyMode = ssl.CERT_REQUIRED
    ciphers: str | None = None
    ca_cert_pem: str | None = None
    client_cert_pem: str | None = None
    client_key_pem: str | None = None


@dataclass(frozen=True, slots=True)
class ServerTlsConfig:
    """TLS configuration for creating server SSL contexts.

    Args:
        server_cert_path: Optional path to the server certificate.
        server_key_path: Optional path to the server private key.
        server_key_password: Optional password for encrypted private keys.
        ca_cert_path: Optional path to CA certificate for client cert verification (mTLS).
        client_cert_verification: SSL verify mode for client certificates.
            - CERT_NONE: No client cert required (TLS only)
            - CERT_OPTIONAL: Client cert optional (mTLS optional)
            - CERT_REQUIRED: Client cert required (mTLS enforced)
        minimum_version: Minimum TLS version to allow.
        maximum_version: Maximum TLS version to allow.
        ciphers: Optional OpenSSL cipher string to enforce.
        server_cert_pem: Optional PEM content for server certificate. Takes precedence over server_cert_path.
        server_key_pem: Optional PEM content for server private key. Takes precedence over server_key_path.
        ca_cert_pem: Optional PEM content for CA certificate. Takes precedence over ca_cert_path.
    """

    server_cert_path: Path | None = None
    server_key_path: Path | None = None
    server_key_password: str | None = None
    ca_cert_path: Path | None = None
    client_cert_verification: ssl.VerifyMode = ssl.CERT_NONE
    minimum_version: TlsVersion = TlsVersion.TLSv1_2
    maximum_version: TlsVersion | None = None
    ciphers: str | None = None
    server_cert_pem: str | None = None
    server_key_pem: str | None = None
    ca_cert_pem: str | None = None

    def __post_init__(self) -> None:
        # Server must always present a certificate/key; allow either PEM strings or paths.
        if self.server_cert_pem is not None or self.server_key_pem is not None:
            if not self.server_cert_pem or not self.server_key_pem:
                raise ValueError("Both server_cert_pem and server_key_pem are required")
            return

        if self.server_cert_path is None or self.server_key_path is None:
            raise ValueError(
                "Either server_cert_path/server_key_path or server_cert_pem/server_key_pem must be set"
            )


    @property
    def mtls_enabled(self) -> bool:
        """Check if mutual TLS is enabled (client cert verification required)."""
        return self.client_cert_verification != ssl.CERT_NONE

    @property
    def mtls_required(self) -> bool:
        """Check if mutual TLS is required (client cert must be presented)."""
        return self.client_cert_verification == ssl.CERT_REQUIRED


@dataclass(slots=True)
class PeerCertificate:
    """Extracted information from a peer certificate.

    Attributes:
        subject: Certificate subject distinguished name.
        issuer: Certificate issuer distinguished name.
        common_name: Common name (CN) from subject.
        san_dns: Subject Alternative Name DNS entries.
        san_uri: Subject Alternative Name URI entries.
        serial_number: Certificate serial number.
        not_before: Validity start time.
        not_after: Validity end time.
        fingerprint: SHA-256 fingerprint of the certificate.
        raw: Raw certificate dict from SSLSocket.getpeercert().
    """

    subject: dict
    issuer: dict
    common_name: str | None = None
    san_dns: list[str] | None = None
    san_uri: list[str] | None = None
    serial_number: str | None = None
    not_before: str | None = None
    not_after: str | None = None
    fingerprint: str | None = None
    raw: dict | None = None


class TlsVerifier:
    """Certificate verification helper for peer certificates."""

    def __init__(
        self,
        *,
        allowed_common_names: Iterable[str] | None = None,
        allowed_san_dns: Iterable[str] | None = None,
        allowed_issuer_common_names: Iterable[str] | None = None,
    ) -> None:
        self._allowed_common_names = set(allowed_common_names or ())
        self._allowed_san_dns = set(allowed_san_dns or ())
        self._allowed_issuer_common_names = set(allowed_issuer_common_names or ())

    def verify(self, cert: dict | None, *, hostname: str | None = None) -> bool:
        """Return True if the certificate passes verification rules.

        Args:
            cert: Certificate mapping from SSLSocket.getpeercert().
            hostname: Optional hostname to validate against the certificate.
        """

        if not cert:
            return False

        if hostname:
            # Python 3.12+ removed ssl.match_hostname, use simple verification
            common_names = _extract_common_names(cert.get("subject", ()))
            san_dns = _extract_san_dns(cert.get("subjectAltName", ()))

            # Check if hostname matches CN or SAN DNS
            if hostname not in common_names and hostname not in san_dns:
                # Try wildcard matching
                wildcard_suffix = hostname.split(".", 1)[-1] if "." in hostname else ""
                has_wildcard = any(
                    cn == "*." + wildcard_suffix for cn in common_names
                ) or any(
                    dns == "*." + wildcard_suffix for dns in san_dns
                )

                if not has_wildcard:
                    return False

        if self._allowed_common_names:
            common_names = _extract_common_names(cert.get("subject", ()))
            if not (common_names & self._allowed_common_names):
                return False

        if self._allowed_san_dns:
            san_dns = _extract_san_dns(cert.get("subjectAltName", ()))
            if not (san_dns & self._allowed_san_dns):
                return False

        if self._allowed_issuer_common_names:
            issuer_names = _extract_common_names(cert.get("issuer", ()))
            if not (issuer_names & self._allowed_issuer_common_names):
                return False

        return True


def _load_pem_to_context(
    context: ssl.SSLContext,
    cert_pem: str,
    key_pem: str,
    *,
    password: str | None = None,
) -> None:
    """Load a certificate/key pair from PEM strings into an SSL context.

    This helper writes PEM strings to temporary files and loads them via
    SSLContext.load_cert_chain(). Temporary files are always removed.

    Note: NamedTemporaryFile(delete=False) is required on Windows because the
    SSL layer re-opens the file path.
    """

    cert_tmp = None
    key_tmp = None
    try:
        cert_tmp = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            suffix=".pem",
        )
        cert_tmp.write(cert_pem)
        cert_tmp.flush()
        cert_tmp.close()

        key_tmp = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            suffix=".pem",
        )
        key_tmp.write(key_pem)
        key_tmp.flush()
        key_tmp.close()

        context.load_cert_chain(
            certfile=cert_tmp.name,
            keyfile=key_tmp.name,
            password=password,
        )
    finally:
        # Best-effort cleanup; leaving a stray tempfile is better than masking the
        # original TLS error.
        if cert_tmp is not None:
            try:
                Path(cert_tmp.name).unlink(missing_ok=True)
            except Exception:  # pragma: no cover - best effort
                pass
        if key_tmp is not None:
            try:
                Path(key_tmp.name).unlink(missing_ok=True)
            except Exception:  # pragma: no cover - best effort
                pass


def load_client_cert_chain(
    context: ssl.SSLContext,
    cert_path: Path | None = None,
    key_path: Path | None = None,
    *,
    cert_pem: str | None = None,
    key_pem: str | None = None,
    password: str | None = None,
) -> None:
    """Load a client certificate chain into the SSL context."""

    if cert_pem is not None or key_pem is not None:
        if not cert_pem or not key_pem:
            raise ValueError("Both cert_pem and key_pem are required for client certificates")
        _load_pem_to_context(context, cert_pem, key_pem, password=password)
        return

    if cert_path is None or key_path is None:
        raise ValueError("cert_path and key_path are required for client certificates")
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path), password=password)


def create_client_ssl_context(config: TlsConfig) -> ssl.SSLContext:
    """Create a client SSLContext based on the provided configuration."""

    # If a CA PEM is provided, write it to a temporary file and pass it as cafile.
    ca_tmp = None
    cafile = None
    if config.ca_cert_pem is not None:
        ca_tmp = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            suffix=".pem",
        )
        ca_tmp.write(config.ca_cert_pem)
        ca_tmp.flush()
        ca_tmp.close()
        cafile = ca_tmp.name
    elif config.ca_cert_path:
        cafile = str(config.ca_cert_path)

    try:
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=cafile)
    finally:
        if ca_tmp is not None:
            try:
                Path(ca_tmp.name).unlink(missing_ok=True)
            except Exception:  # pragma: no cover - best effort
                pass

    context.verify_mode = config.verify_mode
    context.check_hostname = config.check_hostname
    min_version = _to_ssl_version(config.minimum_version)
    max_version = _to_ssl_version(config.maximum_version) if config.maximum_version else None
    if max_version is not None and max_version < min_version:
        raise ValueError("maximum_version cannot be lower than minimum_version")
    context.minimum_version = min_version
    if max_version is not None:
        context.maximum_version = max_version
    if config.ciphers:
        context.set_ciphers(config.ciphers)

    # PEM takes precedence over path if both are provided.
    if config.client_cert_pem is not None or config.client_key_pem is not None:
        if not config.client_cert_pem or not config.client_key_pem:
            raise ValueError("Both client_cert_pem and client_key_pem are required")
        load_client_cert_chain(
            context,
            cert_pem=config.client_cert_pem,
            key_pem=config.client_key_pem,
            password=config.client_key_password,
        )
    elif config.client_cert_path or config.client_key_path:
        if not config.client_cert_path or not config.client_key_path:
            raise ValueError("Both client_cert_path and client_key_path are required")
        load_client_cert_chain(
            context,
            config.client_cert_path,
            config.client_key_path,
            password=config.client_key_password,
        )

    return context


# Backward compatibility alias
create_ssl_context = create_client_ssl_context


def _to_ssl_version(version: TlsVersion) -> ssl.TLSVersion:
    try:
        return _TLS_VERSION_MAP[version]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported TLS version: {version}") from exc


def _extract_common_names(subject: Iterable) -> set[str]:
    values: set[str] = set()
    for rdn in subject:
        for key, value in rdn:
            if key == "commonName":
                values.add(str(value))
    return values


def _extract_san_dns(subject_alt_names: Iterable) -> set[str]:
    values: set[str] = set()
    for name_type, value in subject_alt_names:
        if name_type == "DNS":
            values.add(str(value))
    return values


def _extract_san_uri(subject_alt_names: Iterable) -> list[str]:
    """Extract URI entries from Subject Alternative Names."""
    values: list[str] = []
    for name_type, value in subject_alt_names:
        if name_type == "URI":
            values.append(str(value))
    return values


# =============================================================================
# Server-side TLS functions (Phase 11)
# =============================================================================


def load_server_cert_chain(
    context: ssl.SSLContext,
    cert_path: Path | None = None,
    key_path: Path | None = None,
    *,
    cert_pem: str | None = None,
    key_pem: str | None = None,
    password: str | None = None,
) -> None:
    """Load a server certificate chain into the SSL context.

    Args:
        context: The SSL context to configure.
        cert_path: Path to the server certificate file.
        key_path: Path to the server private key file.
        cert_pem: PEM content for the server certificate (preferred over cert_path).
        key_pem: PEM content for the server private key (preferred over key_path).
        password: Optional password for encrypted private keys.
    """
    if cert_pem is not None or key_pem is not None:
        if not cert_pem or not key_pem:
            raise ValueError("Both cert_pem and key_pem are required for server certificates")
        _load_pem_to_context(context, cert_pem, key_pem, password=password)
        return

    if cert_path is None or key_path is None:
        raise ValueError("cert_path and key_path are required for server certificates")
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path), password=password)


def create_server_ssl_context(config: ServerTlsConfig) -> ssl.SSLContext:
    """Create a server SSLContext based on the provided configuration.

    Args:
        config: Server TLS configuration.

    Returns:
        Configured SSL context for server use.
    """
    # Create server context
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

    # PEM takes precedence over path if both are provided.
    server_cert_pem = config.server_cert_pem
    server_key_pem = config.server_key_pem
    server_cert_path = config.server_cert_path
    server_key_path = config.server_key_path

    if server_cert_pem is not None or server_key_pem is not None:
        if not server_cert_pem or not server_key_pem:
            raise ValueError("Both server_cert_pem and server_key_pem are required")
    else:
        if server_cert_path is None or server_key_path is None:
            raise ValueError("Either server_cert_path/server_key_path or server_cert_pem/server_key_pem must be set")

    # Load server certificate and key
    load_server_cert_chain(
        context,
        server_cert_path,
        server_key_path,
        cert_pem=server_cert_pem,
        key_pem=server_key_pem,
        password=config.server_key_password,
    )

    # Configure client certificate verification (mTLS)
    if config.client_cert_verification != ssl.CERT_NONE:
        context.verify_mode = config.client_cert_verification

        ca_tmp = None
        try:
            if config.ca_cert_pem is not None:
                ca_tmp = tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    delete=False,
                    suffix=".pem",
                )
                ca_tmp.write(config.ca_cert_pem)
                ca_tmp.flush()
                ca_tmp.close()
                context.load_verify_locations(cafile=ca_tmp.name)
            elif config.ca_cert_path:
                context.load_verify_locations(cafile=str(config.ca_cert_path))
        finally:
            if ca_tmp is not None:
                try:
                    Path(ca_tmp.name).unlink(missing_ok=True)
                except Exception:  # pragma: no cover - best effort
                    pass

    # Set TLS version constraints
    min_version = _to_ssl_version(config.minimum_version)
    max_version = _to_ssl_version(config.maximum_version) if config.maximum_version else None
    if max_version is not None and max_version < min_version:
        raise ValueError("maximum_version cannot be lower than minimum_version")
    context.minimum_version = min_version
    if max_version is not None:
        context.maximum_version = max_version

    # Set cipher suite if specified
    if config.ciphers:
        context.set_ciphers(config.ciphers)

    return context


# =============================================================================
# Principal extraction (Phase 11)
# =============================================================================


def extract_principal_from_cert(
    cert_dict: dict | None,
    *,
    prefer_san: bool = True,
) -> PeerCertificate | None:
    """Extract principal information from a peer certificate.

    This function extracts:
    - Common Name (CN) from subject
    - Subject Alternative Names (SAN): DNS and URI entries
    - Certificate serial number
    - Validity period (not_before, not_after)
    - SHA-256 fingerprint

    Args:
        cert_dict: Certificate dictionary from SSLSocket.getpeercert().
        prefer_san: If True, prefer SAN entries over CN for principal.

    Returns:
        PeerCertificate with extracted information, or None if cert_dict is None.
    """
    if not cert_dict:
        return None

    # Extract common name from subject
    common_names = _extract_common_names(cert_dict.get("subject", ()))
    common_name = next(iter(common_names)) if common_names else None

    # Extract SAN entries
    san_entries = cert_dict.get("subjectAltName", ())
    san_dns = list(_extract_san_dns(san_entries))
    san_uri = _extract_san_uri(san_entries)

    # Extract serial number
    serial_number = cert_dict.get("serialNumber")

    # Extract validity period
    not_before = cert_dict.get("notBefore")
    not_after = cert_dict.get("notAfter")

    # Compute fingerprint (from raw binary if available, otherwise from dict)
    fingerprint = None
    if "peercert" in cert_dict:
        # Raw binary certificate available
        fingerprint = hashlib.sha256(cert_dict["peercert"]).hexdigest()
    else:
        # Fallback: compute from dict representation (less secure but usable for logging)
        cert_str = str(cert_dict)
        fingerprint = hashlib.sha256(cert_str.encode()).hexdigest()

    return PeerCertificate(
        subject={"raw": cert_dict.get("subject", ())},
        issuer={"raw": cert_dict.get("issuer", ())},
        common_name=common_name,
        san_dns=san_dns if san_dns else None,
        san_uri=san_uri if san_uri else None,
        serial_number=serial_number,
        not_before=not_before,
        not_after=not_after,
        fingerprint=fingerprint,
        raw=cert_dict,
    )


def get_principal_from_cert(
    cert_dict: dict | None,
    *,
    prefer_san: bool = True,
    prefer_uri: bool = False,
) -> str | None:
    """Get the principal identifier from a peer certificate.

    The principal is determined by:
    1. SAN URI entry (if prefer_uri=True and available)
    2. SAN DNS entry (if prefer_san=True and available)
    3. Common Name (CN) from subject

    Args:
        cert_dict: Certificate dictionary from SSLSocket.getpeercert().
        prefer_san: Prefer SAN entries over CN.
        prefer_uri: Prefer URI SAN over DNS SAN.

    Returns:
        Principal identifier string or None.
    """
    peer_cert = extract_principal_from_cert(cert_dict, prefer_san=prefer_san)
    if not peer_cert:
        return None

    # Priority 1: SAN URI (if enabled)
    if prefer_uri and peer_cert.san_uri:
        return peer_cert.san_uri[0]

    # Priority 2: SAN DNS (if enabled)
    if prefer_san and peer_cert.san_dns:
        return peer_cert.san_dns[0]

    # Priority 3: Common Name
    return peer_cert.common_name


# =============================================================================
# Certificate sanitization for audit (Phase 11)
# =============================================================================


def sanitize_cert_for_audit(
    cert: PeerCertificate | dict | None,
    *,
    include_issuer: bool = True,
    include_serial: bool = False,
    include_fingerprint: bool = True,
) -> dict:
    """Create a sanitized version of certificate info for audit logging.

    This function removes sensitive details while keeping useful information
    for security auditing and troubleshooting.

    Args:
        cert: PeerCertificate or raw cert dict.
        include_issuer: Include issuer information.
        include_serial: Include serial number (usually not needed).
        include_fingerprint: Include certificate fingerprint.

    Returns:
        Sanitized dictionary safe for logging.
    """
    if not cert:
        return {"present": False}

    # Convert dict to PeerCertificate if needed
    if isinstance(cert, dict):
        peer_cert = extract_principal_from_cert(cert)
        if not peer_cert:
            return {"present": True, "error": "failed_to_parse"}
    else:
        peer_cert = cert

    result: dict = {
        "present": True,
        "common_name": peer_cert.common_name,
    }

    if peer_cert.san_dns:
        result["san_dns"] = peer_cert.san_dns[:3]  # Limit to first 3
    if peer_cert.san_uri:
        result["san_uri"] = peer_cert.san_uri[:3]  # Limit to first 3

    if include_issuer and peer_cert.issuer:
        # Only include issuer common name, not full DN
        issuer_raw = peer_cert.issuer.get("raw", ())
        issuer_cn = _extract_common_names(issuer_raw)
        if issuer_cn:
            result["issuer_cn"] = next(iter(issuer_cn))

    if include_serial and peer_cert.serial_number:
        # Truncate serial number for privacy
        serial = str(peer_cert.serial_number)
        result["serial"] = serial[:8] + "..." if len(serial) > 8 else serial

    if include_fingerprint and peer_cert.fingerprint:
        # Show only first 16 chars of fingerprint (enough for identification)
        result["fingerprint"] = peer_cert.fingerprint[:16] + "..."

    # Validity period
    if peer_cert.not_before:
        result["valid_from"] = peer_cert.not_before
    if peer_cert.not_after:
        result["valid_until"] = peer_cert.not_after

    return result


def verify_mtls_connection(
    cert_dict: dict | None,
    auth_scheme: str | None = None,
    config: ServerTlsConfig | None = None,
) -> tuple[bool, str | None]:
    """Verify that the connection meets mTLS requirements.

    This ensures that when auth_scheme='mtls', the connection is actually
    using mutual TLS with a valid client certificate.

    Args:
        cert_dict: Certificate dictionary from SSLSocket.getpeercert().
        auth_scheme: Auth scheme from request metadata (e.g., "mtls").
        config: Server TLS configuration.

    Returns:
        Tuple of (is_valid, error_message).
    """
    # If auth_scheme is not mtls, no verification needed
    if auth_scheme != "mtls":
        return True, None

    # If mTLS is not configured/enabled, reject mtls auth scheme
    if config and not config.mtls_enabled:
        return False, "mTLS not enabled on server"

    # Check if certificate was presented
    if not cert_dict:
        return False, "Client certificate required for mtls auth scheme"

    # Additional verification: check if cert is valid
    peer_cert = extract_principal_from_cert(cert_dict)
    if not peer_cert:
        return False, "Failed to parse client certificate"

    return True, None
