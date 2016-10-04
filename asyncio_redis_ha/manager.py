import asyncio
from functools import wraps

from asyncio_redis import Script, NoAvailableConnectionsInPoolError
from asyncio_redis.replies import ListReply

from asyncio_redis_ha.connection import SentinelConnection, RedisConnection
from asyncio_redis_ha.log import logger
from asyncio_redis_ha.protocol import ExtendedProtocol


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

    @asyncio.coroutine
    def _create_sentinel_connections(self):
        for x in self.config.sentinels:
            try:
                connection = yield from SentinelConnection.create(*x, auto_reconnect=True, loop=self._loop)
                """:type connection SentinelConnection"""
                self._sentinels.append(connection)
            except ConnectionError:
                pass

    def _close_sentinel_connections(self):
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
        connection = yield from RedisConnection.create(
            host=host,
            port=port,
            password=self.config.password,
            db=self.config.db,
            auto_reconnect=False,
            loop=self._loop,
            protocol_class=protocol_class
        )
        """:type connection RedisConnection"""
        self._connections.append(connection)
        return connection

    @asyncio.coroutine
    def discover(self):
        yield from self._create_sentinel_connections()
        yield from self._discover_master()

    @asyncio.coroutine
    def _discover_master(self):
        """
        :return: ExtendedProtocol
        """
        config_pair = None
        self._close_master_pool()

        if self.sentinels_connected < 1:
            yield from self._create_sentinel_connections()

        for sentinel in [c for c in self._sentinels if c.protocol.is_connected]:
            try:
                # try retrieve master address from sentinels
                config_pair = yield from sentinel.get_master_addr_by_name(self.cluster_name)
            except ConnectionError:
                continue

            if isinstance(config_pair, ListReply):
                config_pair = yield from config_pair.aslist()
                """:type config_pair list"""
                if len(config_pair) >= 2:
                    try:
                        connection = yield from self._add_pool_instance(config_pair[0], int(config_pair[1]))
                        reply = yield from connection.role()
                        """:type reply ListReply"""
                        reply = yield from reply.aslist()
                        role = reply[0]
                        if role == 'master':
                            for x in range(self.poolsize - 1):
                                yield from self._add_pool_instance(config_pair[0], int(config_pair[1]))
                            break
                    except ConnectionError:
                        pass

        if self.connections_connected < 1:
            raise NoAvailableConnectionsInPoolError
        logger.info('master at %s', config_pair)

    def _discover_sentinels(self):
        pass

    def _discover_slaves(self):
        pass

    def _close_master_pool(self):
        """
        Close all the connections in the pool.
        """
        for c in self._connections:
            c.close()

        self._connections = []

    def close(self):
        self._close_master_pool()
        self._close_sentinel_connections()

    def __repr__(self):
        return 'GuardedPool(cluster=%r, poolsize=%r)' % (self.config.cluster_name, self._poolsize)

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
