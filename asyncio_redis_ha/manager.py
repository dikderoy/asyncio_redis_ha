from asyncio_redis_ha.connection import SentinelConnection
from asyncio_redis_ha.log import logger
from asyncio_redis_ha.protocol import ExtendedProtocol


class HighAvailabilityConfig:
    def __init__(self,
                 cluster_name: str,
                 sentinels: dict,
                 db=0,
                 password=None,
                 encoder=None,
                 loop=None,
                 protocol_class=ExtendedProtocol):
        self.protocol_class = protocol_class
        self.loop = loop
        self.encoder = encoder
        self.password = password
        self.db = db
        self.sentinels = sentinels
        self.cluster_name = cluster_name


class ConnectionManager:
    """
    :type sentinels: list[SentinelConnection]
    """

    def __init__(self, config: HighAvailabilityConfig):
        """

        :param config: HighAvailabilityConfig
        """
        self.config = config

        self.cluster_name = self.config.cluster_name
        self.sentinels = []
        self.master = None
        self.instances = []

    def discover(self):
        pass

    def _create_sentinel_connections(self):
        for x in self.config.sentinels:
            connection = yield from SentinelConnection.create(*x, **self.config.__dict__)
            self.sentinels.append(connection)

    def _discover_master(self):
        """
        :return: ExtendedProtocol
        """
        master = None

        for instance in self.sentinels:
            master = yield from instance.get_master_by_name(self.cluster_name)
            if master:
                break
        logger.info('master at %s', master)
