"""Cooperative I/O checkpoints scoped to the executing job's thread/context."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar


class OperationCancelled(Exception):
    """Stop at the next boundary without committing a partial operation."""


_CHECKPOINT: ContextVar[Callable[[], None] | None] = ContextVar(
    "operation_checkpoint", default=None
)


def checkpoint() -> None:
    callback = _CHECKPOINT.get()
    if callback is not None:
        callback()


@contextmanager
def cancellation_scope(callback: Callable[[], None]) -> Iterator[None]:
    token = _CHECKPOINT.set(callback)
    try:
        yield
    finally:
        _CHECKPOINT.reset(token)
