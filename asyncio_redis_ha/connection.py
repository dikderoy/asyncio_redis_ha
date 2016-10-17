import asyncio
import logging

from asyncio_redis.connection import Connection

from asyncio_redis_ha.protocol import ExtendedProtocol
from .log import logger
from .protocol import _all_commands, SentinelProtocol

# In Python 3.4.4, `async` was renamed to `ensure_future`.
try:
    ensure_future = asyncio.ensure_future
except AttributeError:
    ensure_future = asyncio.async


class RedisConnection(Connection):
    def __init__(self):
        super().__init__()
        self._reconnect_count = 0

    @classmethod
    @asyncio.coroutine
    def create(cls, host='localhost', port=6379, *, password=None, db=0,
               encoder=None, loop=None, protocol_class=ExtendedProtocol, **kw):
        connection = yield from super().create(host, port, password=password, db=db,
                                               encoder=encoder, auto_reconnect=False,
                                               loop=loop, protocol_class=protocol_class)
        return connection

    @classmethod
    @asyncio.coroutine
    def configurable_create(cls, host='localhost', port=6379, *, password=None, db=0,
                            encoder=None, loop=None, protocol_class=ExtendedProtocol,
                            auto_reconnect=True, reconnect_cb=None, ensure_connection_established=True):
        """
        :param host: Address, either host or unix domain socket path
        :type host: str
        :param port: TCP port. If port is 0 then host assumed to be unix socket path
        :type port: int
        :param password: Redis database password
        :type password: bytes
        :param db: Redis database
        :type db: int
        :param encoder: Encoder to use for encoding to or decoding from redis bytes to a native type.
        :type encoder: :class:`~asyncio_redis.encoders.BaseEncoder` instance.
        :param loop: (optional) asyncio event loop.

        :param protocol_class: (optional) redis protocol implementation
        :type protocol_class: ~asyncio_redis_ha.ExtendedProtocol

        :param auto_reconnect: Enable auto reconnect
        :type auto_reconnect: bool
        :param reconnect_cb: (optional) coroutine callback, returning bool whatever connection should reconnect,
            with following signature: `cb(~Connection connection)->bool`,
            acts as backoff strategy (you may alter connection properties during the call),
            auto_reconnect should be True in order to use this feature
        :type reconnect_cb: ~callable
        :param ensure_connection_established:  whatever to wait for connection
         to be established before returning connection instance
        :type ensure_connection_established: bool
        """
        # todo: test this method

        assert port >= 0, "Unexpected port value: %r" % (port,)
        connection = cls()

        connection.host = host
        connection.port = port
        connection._loop = loop or asyncio.get_event_loop()
        connection._retry_interval = .5
        connection._closed = False
        connection._closing = False

        connection._auto_reconnect = reconnect_cb is not None

        @asyncio.coroutine
        def reconnect_hook():
            if reconnect_cb:
                should_reconnect = yield from reconnect_cb(connection)
            else:
                should_reconnect = True
            if should_reconnect:
                yield from connection._reconnect()
            else:
                connection.close()

        # Create protocol instance

        def connection_lost():
            if not connection._closing and connection._auto_reconnect:
                # schedule reconnect hook execution
                ensure_future(reconnect_hook(), loop=connection._loop)

        # Create protocol instance
        connection.protocol = protocol_class(password=password, db=db, encoder=encoder,
                                             connection_lost_callback=connection_lost, loop=connection._loop)

        # Connect
        if ensure_connection_established:
            yield from connection._reconnect()
        else:
            ensure_future(connection._reconnect(), loop=connection._loop)

        return connection

    def _inc_reconnect_count(self):
        """increment reconnect count"""
        self._reconnect_count += 1

    def _reset_reconnect_count(self):
        """reset reconnect count to 0"""
        self._reconnect_count = 0

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
                self._reset_reconnect_count()
                return
            except OSError:
                if not self._auto_reconnect or self._reconnect_count == 0:
                    raise ConnectionError
                # Sleep and try again
                self._increase_retry_interval()
                self._inc_reconnect_count()
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

    @classmethod
    def configurable_create(cls, host='localhost', port=26379, *,
                            encoder=None, loop=None, protocol_class=SentinelProtocol,
                            auto_reconnect=True, reconnect_cb=None, ensure_connection_established=True, **kw):
        return super().configurable_create(host, port, encoder=encoder, loop=loop,
                                           protocol_class=protocol_class,
                                           auto_reconnect=auto_reconnect, reconnect_cb=reconnect_cb)

    def __getattr__(self, name):
        # Only proxy commands.
        if name not in _all_commands:
            raise AttributeError

        return getattr(self.protocol, name)
