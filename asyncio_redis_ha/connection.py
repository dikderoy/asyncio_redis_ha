import asyncio

from asyncio_redis.connection import Connection

from .protocol import _all_commands, SentinelProtocol


class SentinelConnection(Connection):
    @classmethod
    @asyncio.coroutine
    def create(cls, host='localhost', port=6379, *, encoder=None, loop=None, protocol_class=SentinelProtocol, **kwargs):
        connection = yield from super().create(host, port, encoder=encoder, auto_reconnect=False,
                                               loop=loop, protocol_class=protocol_class)
        return connection

    def __getattr__(self, name):
        # Only proxy commands.
        if name not in _all_commands:
            raise AttributeError

        return getattr(self.protocol, name)
