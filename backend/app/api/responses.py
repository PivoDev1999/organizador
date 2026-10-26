from collections.abc import Callable, Iterator, Mapping

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send


class ClosingStreamingResponse(StreamingResponse):
    """StreamingResponse that always runs `close` when it ends: finished, failed or client gone.

    A disconnect stops the iteration midway: the iterator is left unfinished (its own `finally` only runs
    when it is garbage collected) and, with ASGI 2.4, Starlette raises ClientDisconnect and skips the
    `background` task. Here the close is explicit, so the storage connection goes back to the pool.
    """

    def __init__(
        self,
        content: Iterator[bytes],
        *,
        close: Callable[[], None],
        media_type: str,
        headers: Mapping[str, str],
    ) -> None:
        super().__init__(content, media_type=media_type, headers=headers)
        self._close = close

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._close()
