from __future__ import annotations

"""mTLS helpers for configuring SSL contexts and verifying peer certificates."""

import enum
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

__all__ = [
    "TlsVersion",
    "TlsConfig",
    "TlsVerifier",
    "load_client_cert_chain",
    "create_ssl_context",
]


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
            try:
                ssl.match_hostname(cert, hostname)
            except ssl.CertificateError:
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


def load_client_cert_chain(
    context: ssl.SSLContext,
    cert_path: Path,
    key_path: Path,
    *,
    password: str | None = None,
) -> None:
    """Load a client certificate chain into the SSL context."""

    if cert_path is None or key_path is None:
        raise ValueError("cert_path and key_path are required for client certificates")
    context.load_cert_chain(
        certfile=str(cert_path),
        keyfile=str(key_path),
        password=password,
    )


def create_ssl_context(config: TlsConfig) -> ssl.SSLContext:
    """Create a client SSLContext based on the provided configuration."""

    cafile = str(config.ca_cert_path) if config.ca_cert_path else None
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=cafile)
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

    if config.client_cert_path or config.client_key_path:
        if not config.client_cert_path or not config.client_key_path:
            raise ValueError("Both client_cert_path and client_key_path are required")
        load_client_cert_chain(
            context,
            config.client_cert_path,
            config.client_key_path,
            password=config.client_key_password,
        )

    return context


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
