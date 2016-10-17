import asyncio
from functools import wraps

from asyncio_redis import Script, NoAvailableConnectionsInPoolError, NotConnectedError

from asyncio_redis_ha.connection import SentinelConnection, RedisConnection
from asyncio_redis_ha.log import logger
from asyncio_redis_ha.protocol import ExtendedProtocol

# In Python 3.4.4, `async` was renamed to `ensure_future`.
try:
    ensure_future = asyncio.ensure_future
except AttributeError:
    ensure_future = asyncio.async


class HighAvailabilityConfig:
    def __init__(self,
                 cluster_name: str,
                 sentinels: list,
                 db=0,
                 password=None,
                 encoder=None,
                 protocol_class=ExtendedProtocol):
        self.protocol_class = protocol_class
        self.encoder = encoder
        self.password = password
        self.db = db
        self.sentinels = sentinels
        self.cluster_name = cluster_name


class ConnectionManager:
    """
    Sentinel guarded connection manager, also manages connection Pool (always)

    :type _sentinels: list[SentinelConnection]
    :type _connections: list[RedisConnection]
    """

    def __init__(self, config: HighAvailabilityConfig, poolsize=1, loop=None):
        """

        :param config: HighAvailabilityConfig
        """
        self._poolsize = poolsize
        self._sentinels = []
        self._connections = []
        self._loop = loop or asyncio.get_event_loop()
        self.config = config
        self.cluster_name = self.config.cluster_name
        self._discover_lock = asyncio.Lock()

    @classmethod
    @asyncio.coroutine
    def create(cls,
               cluster_name: str,
               sentinels: list,
               db=0,
               password=None,
               encoder=None,
               protocol_class=ExtendedProtocol,
               poolsize=1,
               loop=None):
        """
        creates new instance of ConnectionManager, and initializes it

        :type cluster_name: str
        :param cluster_name: redis cluster name
        :type sentinels: list[tuple]
        :param sentinels: list of known sentinel instances as tuples ``(host, port)``
        :param password: Redis database password
        :type password: bytes
        :param db: Redis database
        :type db: int
        :param encoder: Encoder to use for encoding to or decoding from redis bytes to a native type.
        :type encoder: :class:`~asyncio_redis.encoders.BaseEncoder` instance.
        :param loop: (optional) asyncio event loop.
        :type protocol_class: :class:`~asyncio_redis_ha.ExtendedProtocol`
        :param protocol_class: (optional) redis protocol implementation:param protocol_class:
        :type poolsize: int
        :param poolsize: The number of parallel connections.
        :return: ConnectionManager
        """
        config = HighAvailabilityConfig(
            cluster_name=cluster_name,
            sentinels=sentinels,
            db=db,
            password=password,
            encoder=encoder,
            protocol_class=protocol_class,
        )

        self = cls(config, poolsize=poolsize, loop=loop)
        # run initial discovery
        yield from self._discover_master()
        # now we are ready
        return self

    @asyncio.coroutine
    def _recreate_sentinel_connections(self):
        """creates connections for configured sentinels, closes previously opened connections if any"""
        self._close_sentinel_connections()

        for conf in self.config.sentinels:
            try:
                logger.info('connecting sentinel (%s, %s)', *conf)
                connection = yield from SentinelConnection.configurable_create(
                    *conf, loop=self._loop, auto_reconnect=True, ensure_connection_established=False
                )
                """:type connection SentinelConnection"""
                self._sentinels.append(connection)
            except ConnectionError:
                pass
        yield from asyncio.sleep(.1)  # make sure above coroutines run

    def _close_sentinel_connections(self):
        logger.info('closing sentinel connections')

        for s in self._sentinels:
            s.close()

        self._sentinels = []

    @asyncio.coroutine
    def _add_pool_instance(self, host='localhost', port=6379, protocol_class=ExtendedProtocol):
        """
        Create a new connection pool instance.

        :param host: Address, either host or unix domain socket path
        :type host: str
        :param port: TCP port. If port is 0 then host assumed to be unix socket path
        :type port: int
        :param poolsize: The number of parallel connections.
        :type poolsize: int
        :type protocol_class: :class:`~asyncio_redis.RedisProtocol`
        :param protocol_class: (optional) redis protocol implementation
        """

        @asyncio.coroutine
        def report_connection_lost(connection: RedisConnection):
            """reconnect strategy, 3 attempts, then - rediscover"""
            if connection._reconnect_count <= 3:
                return True
            else:
                logger.info('connection seems lost - schedule rediscover')
                # ensure_future(self._discover_master(), self._loop)
                try:
                    yield from self._discover_master()
                except NotConnectedError:
                    pass
                return False

        logger.info('connecting redis-master (%s, %s)', host, port)
        connection = yield from RedisConnection.configurable_create(
            host=host,
            port=port,
            password=self.config.password,
            db=self.config.db,
            auto_reconnect=True,
            loop=self._loop,
            protocol_class=protocol_class,
            reconnect_cb=report_connection_lost
        )
        """:type connection RedisConnection"""
        self._connections.append(connection)
        return connection

    @asyncio.coroutine
    def _discover_master(self):
        """
        performs a discover sequence, only one runs at a time (lock used)
        """

        lock = self._discover_lock
        was_locked = lock.locked()

        yield from lock.acquire()
        logger.debug('acquired discovery lock')

        if was_locked or self.connections_connected == self.poolsize:
            logger.debug('skipping discovery as it was just performed')
            lock.release()
            return

        logger.debug('start discovery')

        config_pair = None
        self._close_master_pool()

        if self.sentinels_connected < 1:
            yield from self._recreate_sentinel_connections()

        for sentinel in [c for c in self._sentinels if c.protocol.is_connected]:
            try:
                # try retrieve master address from sentinels
                """:type config_pair list"""
                config_pair = yield from (yield from sentinel.get_master_addr_by_name(self.cluster_name)).aslist()
                break
            except ConnectionError:
                pass
            except Exception as e:
                lock.release()
                raise e

        if not config_pair or not isinstance(config_pair, list):
            lock.release()
            raise NotConnectedError('Failed to discover redis-master')

        if len(config_pair) >= 2:
            try:
                connection = yield from self._add_pool_instance(config_pair[0], int(config_pair[1]))
                reply = yield from (yield from connection.role()).aslist()
                role = reply[0]
                if role == 'master':
                    # initialize rest of the pool
                    for x in range(self.poolsize - 1):
                        yield from self._add_pool_instance(config_pair[0], int(config_pair[1]))
                else:
                    self._close_master_pool()
            except ConnectionError:
                pass
            except Exception as e:
                lock.release()
                raise e

        if self.connections_connected < 1:
            lock.release()
            raise NotConnectedError
        logger.info('master at %s', config_pair)
        lock.release()

    def _discover_sentinels(self):
        # todo: add sentinel discovery
        pass

    def _discover_slaves(self):
        # todo: add slave discovery and promotion algorithms
        pass

    def _close_master_pool(self):
        """
        Close all the connections in the pool.
        """
        logger.info('closing redis-master connections')
        for c in self._connections:
            c.close()

        self._connections = []

    def close(self):
        self._close_master_pool()
        self._close_sentinel_connections()

    def __repr__(self):
        return 'ConnectionManager(cluster=%r, poolsize=%r)' % (self.config.cluster_name, self._poolsize)

    @property
    def poolsize(self):
        """ Number of parallel connections in the pool."""
        return self._poolsize

    @property
    def connections_in_use(self):
        """
        Return how many protocols are in use.
        """
        return sum([1 for c in self._connections if c.protocol.in_use])

    @property
    def connections_connected(self):
        """
        The amount of open TCP connections.
        """
        return sum([1 for c in self._connections if c.protocol.is_connected])

    @property
    def sentinels_connected(self):
        """
        The amount of open TCP connections.
        """
        return sum([1 for c in self._sentinels if c.protocol.is_connected])

    def _get_free_connection(self):
        """
        Return the next protocol instance that's not in use.
        (A protocol in pubsub mode or doing a blocking request is considered busy,
        and can't be used for anything else.)
        """
        self._shuffle_connections()

        for c in self._connections:
            if c.protocol.is_connected and not c.protocol.in_use:
                return c

    def _shuffle_connections(self):
        """
        'shuffle' protocols. Make sure that we devide the load equally among the protocols.
        """
        self._connections = self._connections[1:] + self._connections[:1]

    def __getattr__(self, name):
        """
        Proxy to a protocol. (This will choose a protocol instance that's not
        busy in a blocking request or transaction.)
        """

        @asyncio.coroutine
        def guard(*args, **kwargs):
            """wrapper ensuring that where are active connections to master, and performing rediscover if needed"""
            if self.connections_connected == 0:
                yield from self._discover_master()
            connection = self._get_free_connection()

            if connection:
                result = yield from getattr(connection, name)(*args, **kwargs)
                return result
            else:
                raise NoAvailableConnectionsInPoolError(
                    'No available connections in the pool: size=%s, in_use=%s, connected=%s' % (
                        self.poolsize, self.connections_in_use, self.connections_connected))

        return guard

    # Proxy the register_script method, so that the returned object will
    # execute on any available connection in the pool.
    @asyncio.coroutine
    @wraps(ExtendedProtocol.register_script)
    def register_script(self, script: str) -> Script:
        # Call register_script from the Protocol.
        script = yield from self.__getattr__('register_script')(script)
        assert isinstance(script, Script)

        # Return a new script instead that runs it on any connection of the pool.
        return Script(script.sha, script.code, lambda: self.evalsha)
