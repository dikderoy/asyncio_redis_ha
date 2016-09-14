from asyncio_redis import RedisProtocol
from asyncio_redis.protocol import CommandCreator, QueryCommandCreator, NativeType, MultiBulkReply

# list of all command methods
from asyncio_redis.replies import ListReply

_all_commands = []


class _command:
    """ Mark method as command (to be passed through CommandCreator for the
    creation of a protocol method) """
    creator = CommandCreator

    def __init__(self, method):
        self.method = method


class _query_command(_command):
    """
    Mark method as query command: This will pass through QueryCommandCreator.

    NOTE: be sure to choose the correct 'returns'-annotation. This will automatially
    determine the correct post processor function in :class:`PostProcessors`.
    """
    creator = QueryCommandCreator

    def __init__(self, method):
        super().__init__(method)


class _RedisProtocolMeta(type):
    """
    Metaclass for `RedisProtocol` which applies the _command decorator.
    """

    def __new__(cls, name, bases, attrs):
        for attr_name, value in dict(attrs).items():
            if isinstance(value, _command):
                creator = value.creator(value.method)
                for suffix, method in creator.get_methods():
                    attrs[attr_name + suffix] = method

                    # Register command.
                    _all_commands.append(attr_name + suffix)

        return type.__new__(cls, name, bases, attrs)


class ExtendedProtocol(RedisProtocol, metaclass=_RedisProtocolMeta):
    @_query_command
    def role(self, tr) -> MultiBulkReply:
        return self._query(tr, b'role')


class SentinelProtocol(ExtendedProtocol, metaclass=_RedisProtocolMeta):
    @_query_command
    def get_master_by_name(self, tr, name: NativeType) -> ListReply:
        return self._query(tr, b'sentinel', b'get-master-by-name', self.encode_from_native(name))

    @_query_command
    def slaves(self, tr, name: NativeType) -> ListReply:
        return self._query(tr, b'sentinel', b'slaves', self.encode_from_native(name))

    @_query_command
    def sentinels(self, tr, name: NativeType) -> ListReply:
        return self._query(tr, b'sentinel', b'sentinels', self.encode_from_native(name))
