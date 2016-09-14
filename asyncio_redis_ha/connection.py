from asyncio_redis.connection import Connection

from .sentinel_protocol import _all_commands, SentinelProtocol


class SentinelConnection(Connection):
    @classmethod
    def create(cls, host='localhost', port=6379, *, encoder=None, loop=None, protocol_class=SentinelProtocol, **kwargs):
        return super().create(host, port, encoder=encoder, auto_reconnect=False,
                              loop=loop, protocol_class=protocol_class)

    def __getattr__(self, name):
        # Only proxy commands.
        if name not in _all_commands:
            raise AttributeError

        return getattr(self.protocol, name)
