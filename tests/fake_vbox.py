"""In-process fake Vitrea vBox controller for exercising VBoxConnection.

Implements the host-protocol basics from spec rev 2.108: accepts a TCP
client, answers the P:VITREA authentication/keep-alive with S:PSW:OK, and
records every command received. Misbehavior (silence, dropped connections,
fragmented or malformed frames) is scripted by the tests.
"""

import asyncio
import contextlib
import time

AUTH = b"P:VITREA\r\n"
AUTH_ACK = b"S:PSW:OK\r\n"
COMMAND_ACK = b"OK\r\n"
VERSION_QUERY = b"G:V:S\r\n"


class FakeVBox:
    """Minimal scriptable vBox server.

    With single_connection=True it mirrors the real device, which accepts
    only ONE host socket at a time: a second connection attempt while one
    is active gets closed immediately and counted in `rejected`.
    """

    def __init__(
        self,
        respond_to_auth: bool = True,
        single_connection: bool = False,
        version_reply: bytes | None = b"V:950\r\n",
    ) -> None:
        self.respond_to_auth = respond_to_auth
        self.single_connection = single_connection
        self.version_reply = version_reply
        self.auth_reply = AUTH_ACK
        self.ack_commands = False  # answer every H: command with OK per spec
        self.status_reply_to_get = False  # answer H:*:G:* with a status frame
        # Binary parameter-API replies keyed by command number (C#):
        # when a VTH> frame with that C# arrives, the mapped bytes are sent.
        self.param_replies: dict[int, bytes] = {}
        self.reject_connections = False  # simulate a stale session holding the slot
        # Real-firmware quirks observed live (9.50): unsolicited status
        # frames can arrive before the auth ack, and the FIRST P:VITREA on
        # a fresh socket is not always acknowledged.
        self.unsolicited_on_connect = b""
        self.skip_first_auth_ack = False
        self.host = "127.0.0.1"
        self.port: int | None = None
        self.server: asyncio.Server | None = None
        self.connections = 0
        self.active_connections = 0
        self.max_concurrent = 0
        self.rejected = 0
        self.commands: list[bytes] = []
        self.command_times: list[tuple[bytes, float]] = []
        self.client_writer: asyncio.StreamWriter | None = None
        self.client_writers: list[asyncio.StreamWriter] = []
        self.client_connected = asyncio.Event()
        self.auth_received = asyncio.Event()

    async def start(self) -> tuple[str, int]:
        """Start listening; reuses the previous port after a restart."""
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port or 0
        )
        self.port = self.server.sockets[0].getsockname()[1]
        return self.host, self.port

    async def stop_listening(self) -> None:
        # Note: no wait_closed() here. On Python 3.12+ it waits for all
        # client handlers to finish, which deadlocks while a client is still
        # connected; close() already releases the listening socket.
        if self.server:
            self.server.close()
            self.server = None

    async def drop_client(self) -> None:
        """Close all client connections (simulates a vBox-side drop)."""
        writers, self.client_writers = self.client_writers, []
        self.client_writer = None
        for writer in writers:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def stop(self) -> None:
        await self.stop_listening()
        await self.drop_client()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if self.reject_connections or (
            self.single_connection and self.active_connections >= 1
        ):
            self.rejected += 1
            writer.close()
            with contextlib.suppress(ConnectionError, OSError):
                await writer.wait_closed()
            return
        self.connections += 1
        self.active_connections += 1
        self.max_concurrent = max(self.max_concurrent, self.active_connections)
        self.client_writer = writer
        self.client_writers.append(writer)
        self.client_connected.set()
        auth_count = 0
        try:
            if self.unsolicited_on_connect:
                writer.write(self.unsolicited_on_connect)
                await writer.drain()
            while True:
                prefix = await reader.readexactly(2)
                if prefix == b"VT":
                    # Binary parameter-API frame: VTH> C# len(2, Hi-Lo) payload.
                    header = await reader.readexactly(5)
                    length = int.from_bytes(header[3:5], "big")
                    payload = await reader.readexactly(length)
                    command = prefix + header + payload
                    self.commands.append(command)
                    self.command_times.append((command, time.monotonic()))
                    reply = self.param_replies.get(header[2])
                    if reply:
                        writer.write(reply)
                        await writer.drain()
                    continue
                command = prefix + await reader.readuntil(b"\r\n")
                self.commands.append(command)
                self.command_times.append((command, time.monotonic()))
                if command == AUTH:
                    auth_count += 1
                    self.auth_received.set()
                    skip = self.skip_first_auth_ack and auth_count == 1
                    if self.respond_to_auth and not skip:
                        writer.write(self.auth_reply)
                        await writer.drain()
                elif command == VERSION_QUERY and self.version_reply:
                    writer.write(self.version_reply)
                    await writer.drain()
                elif command.startswith(b"H:") and b":G" in command and (
                    self.status_reply_to_get
                ):
                    # Per spec, a single-key status request is answered with
                    # the status frame itself — no OK.
                    writer.write(b"S:N001:1:O\r\n")
                    await writer.drain()
                elif command.startswith(b"H:") and self.ack_commands:
                    writer.write(COMMAND_ACK)
                    await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            self.active_connections -= 1

    async def send(self, data: bytes) -> None:
        assert self.client_writer is not None, "no client connected"
        self.client_writer.write(data)
        await self.client_writer.drain()

    async def send_fragmented(
        self, data: bytes, chunk_size: int = 1, delay: float = 0.02
    ) -> None:
        """Send data split into chunks with pauses, forcing TCP fragmentation."""
        for start in range(0, len(data), chunk_size):
            await self.send(data[start : start + chunk_size])
            await asyncio.sleep(delay)
