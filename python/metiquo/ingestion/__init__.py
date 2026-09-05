"""Ingestion reproductible des sources officielles de Metiquo."""

from metiquo.ingestion.object_store import (
    FilesystemObjectStore,
    ObjectCollisionError,
    ObjectStore,
    StoredObject,
)
from metiquo.ingestion.transport import (
    DownloadReceipt,
    RetryPolicy,
    SourceMetadata,
    SourceRef,
    SourceTransport,
    TransportPolicy,
)

__all__ = [
    "DownloadReceipt",
    "FilesystemObjectStore",
    "ObjectCollisionError",
    "ObjectStore",
    "RetryPolicy",
    "SourceMetadata",
    "SourceRef",
    "SourceTransport",
    "StoredObject",
    "TransportPolicy",
]
