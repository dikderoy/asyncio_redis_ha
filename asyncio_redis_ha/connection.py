import asyncio
import logging

from asyncio_redis.connection import Connection

from asyncio_redis_ha.protocol import ExtendedProtocol
from .log import logger
from .protocol import _all_commands, SentinelProtocol


class RedisConnection(Connection):
    def __init__(self, auto_reconnect=False, reconnect_cb=None):
        super().__init__()
        self.auto_reconnect = auto_reconnect,
        self._reconnect_cb = reconnect_cb

    @classmethod
    @asyncio.coroutine
    def create(cls, host='localhost', port=6379, *, encoder=None, loop=None, protocol_class=ExtendedProtocol, **kw):
        connection = yield from super().create(host, port, encoder=encoder, auto_reconnect=False,
                                               loop=loop, protocol_class=protocol_class)
        return connection

    @asyncio.coroutine
    def _reconnect(self):
        """
        Set up Redis connection.
        """
        while True:
            try:
                logger.log(logging.INFO, 'Connecting to redis')
                if self.port:
                    yield from self._loop.create_connection(lambda: self.protocol, self.host, self.port)
                else:
                    yield from self._loop.create_unix_connection(lambda: self.protocol, self.host)
                self._reset_retry_interval()
                return
            except OSError:
                if not self.auto_reconnect:
                    raise ConnectionError
                # Sleep and try again
                self._increase_retry_interval()
                interval = self._get_retry_interval()
                logger.log(logging.INFO, 'Connecting to redis failed. Retrying in %i seconds' % interval)
                yield from asyncio.sleep(interval, loop=self._loop)

    def __getattr__(self, name):
        try:
            return super().__getattr__(name)
        except AttributeError:
            # Only proxy commands.
            if name not in _all_commands:
                raise AttributeError
        return getattr(self.protocol, name)


class SentinelConnection(RedisConnection):
    @classmethod
    @asyncio.coroutine
    def create(cls, host='localhost', port=26379, *, encoder=None, loop=None, protocol_class=SentinelProtocol, **kw):
        connection = yield from super().create(host, port, encoder=encoder, auto_reconnect=False,
                                               loop=loop, protocol_class=protocol_class)
        return connection

    def __getattr__(self, name):
        # Only proxy commands.
        if name not in _all_commands:
            raise AttributeError

        return getattr(self.protocol, name)
