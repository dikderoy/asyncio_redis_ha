import asyncio

from asyncio_redis import RedisProtocol
from asyncio_redis.cursors import Cursor, SetCursor, DictCursor, ZCursor
from asyncio_redis.protocol import CommandCreator, NativeType, \
    _RedisProtocolMeta as _CoreRedisProtocolMeta, PostProcessors, MultiBulkReply, ListOf, Transaction, Subscription, \
    Script, NoneType, ZScoreBoundary, _ScanPart
from asyncio_redis.replies import ListReply, BlockingPopReply, ConfigPairReply, DictReply, InfoReply, ClientListReply, \
    SetReply, StatusReply, ZRangeReply, EvalScriptReply

from asyncio_redis_ha.replies import NestedDictReply, NestedListReply

_all_commands = []


class SentinelPostProcessors(PostProcessors):
    @classmethod
    def get_default(cls, return_type):
        try:
            return super().get_default(return_type)
        except KeyError:
            return {
                NestedListReply: cls.multibulk_as_nested_list,
                NestedDictReply: cls.multibulk_as_nested_dict,
            }[return_type]

    # === Post processor handlers below. ===

    @asyncio.coroutine
    def multibulk_as_nested_list(protocol, result):
        assert isinstance(result, MultiBulkReply)
        return NestedListReply(result)

    @asyncio.coroutine
    def multibulk_as_nested_dict(protocol, result):
        assert isinstance(result, MultiBulkReply)
        return NestedDictReply(result)


class ExtendedCommandCreator(CommandCreator):
    def _get_docstring(self, suffix, return_type):
        # Append the real signature as the first line in the docstring.
        # (This will make the sphinx docs show the real signature instead of
        # (*a, **kw) of the wrapper.)
        # (But don't put the anotations inside the copied signature, that's rather
        # ugly in the docs.)
        from inspect import formatargspec
        signature = formatargspec(*self.specs[:6])

        # Use function annotations to generate param documentation.

        def get_name(type_):
            """ Turn type annotation into doc string. """
            try:
                return {
                    BlockingPopReply: ":class:`BlockingPopReply <asyncio_redis.replies.BlockingPopReply>`",
                    ConfigPairReply: ":class:`ConfigPairReply <asyncio_redis.replies.ConfigPairReply>`",
                    DictReply: ":class:`DictReply <asyncio_redis.replies.DictReply>`",
                    InfoReply: ":class:`InfoReply <asyncio_redis.replies.InfoReply>`",
                    ClientListReply: ":class:`InfoReply <asyncio_redis.replies.ClientListReply>`",
                    ListReply: ":class:`ListReply <asyncio_redis.replies.ListReply>`",
                    MultiBulkReply: ":class:`MultiBulkReply <asyncio_redis.replies.MultiBulkReply>`",
                    NativeType: "Native Python type, as defined by " +
                                ":attr:`~asyncio_redis.encoders.BaseEncoder.native_type`",
                    NoneType: "None",
                    SetReply: ":class:`SetReply <asyncio_redis.replies.SetReply>`",
                    StatusReply: ":class:`StatusReply <asyncio_redis.replies.StatusReply>`",
                    ZRangeReply: ":class:`ZRangeReply <asyncio_redis.replies.ZRangeReply>`",
                    ZScoreBoundary: ":class:`ZScoreBoundary <asyncio_redis.replies.ZScoreBoundary>`",
                    EvalScriptReply: ":class:`EvalScriptReply <asyncio_redis.replies.EvalScriptReply>`",
                    Cursor: ":class:`Cursor <asyncio_redis.cursors.Cursor>`",
                    SetCursor: ":class:`SetCursor <asyncio_redis.cursors.SetCursor>`",
                    DictCursor: ":class:`DictCursor <asyncio_redis.cursors.DictCursor>`",
                    ZCursor: ":class:`ZCursor <asyncio_redis.cursors.ZCursor>`",
                    _ScanPart: ":class:`_ScanPart",
                    int: 'int',
                    bool: 'bool',
                    float: 'float',
                    str: 'str',
                    bytes: 'bytes',

                    list: 'list',
                    set: 'set',
                    dict: 'dict',

                    # XXX: Because of circular references, we cannot use the real types here.
                    Transaction: ":class:`asyncio_redis.Transaction`",
                    Subscription: ":class:`asyncio_redis.Subscription`",
                    Script: ":class:`~asyncio_redis.Script`",

                    NestedDictReply: ":class:`NestedDictReply <asyncio_redis_ha.replies.NestedDictReply>`",
                    NestedListReply: ":class:`NestedListReply <asyncio_redis_ha.replies.NestedListReply>`",
                }[type_]
            except KeyError:
                if isinstance(type_, ListOf):
                    return "List or iterable of %s" % get_name(type_.type)

                elif isinstance(type_, tuple):
                    return ' or '.join(get_name(t) for t in type_)
                else:
                    raise Exception('Unknown annotation %r' % type_)
                    # return "``%s``" % type_.__name__

        def get_param(k, v):
            return ':param %s: %s\n' % (k, get_name(v))

        params_str = [get_param(k, v) for k, v in self.params.items()]
        returns = ':returns: (Future of) %s\n' % get_name(return_type) if return_type else ''

        return '%s%s\n%s\n\n%s%s' % (
            self.method.__name__ + suffix, signature,
            self.method.__doc__,
            ''.join(params_str),
            returns
        )


class ExtendedQueryCommandCreator(ExtendedCommandCreator):
    def get_methods(self):
        # (Some commands, e.g. those that return a ListReply can generate
        # multiple protocol methods.  One that does return the ListReply, but
        # also one with the 'aslist' suffix that returns a Python list.)
        all_post_processors = SentinelPostProcessors.get_all(self.return_type)
        result = []

        for suffix, return_type, post_processor in all_post_processors:
            result.append((suffix, self._get_wrapped_method(post_processor, suffix, return_type)))

        return result


class _command:
    """ Mark method as command (to be passed through CommandCreator for the
    creation of a protocol method) """
    creator = ExtendedCommandCreator

    def __init__(self, method):
        self.method = method


class _query_command(_command):
    """
    Mark method as query command: This will pass through ExtendedQueryCommandCreator.

    NOTE: be sure to choose the correct 'returns'-annotation. This will automatially
    determine the correct post processor function in :class:`PostProcessors`.
    """
    creator = ExtendedQueryCommandCreator

    def __init__(self, method):
        super().__init__(method)


class _RedisProtocolMeta(_CoreRedisProtocolMeta):
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
    def role(self, tr) -> NestedListReply:
        return self._query(tr, b'role')


class SentinelProtocol(ExtendedProtocol, metaclass=_RedisProtocolMeta):
    @_query_command
    def get_master_addr_by_name(self, tr, name: NativeType) -> ListReply:
        """sentinel get master command, return host port pair of current master"""
        return self._query(tr, b'sentinel', b'get-master-addr-by-name', self.encode_from_native(name))

    @_query_command
    def slaves(self, tr, name: NativeType) -> NestedDictReply:
        return self._query(tr, b'sentinel', b'slaves', self.encode_from_native(name))

    @_query_command
    def sentinels(self, tr, name: NativeType) -> NestedDictReply:
        return self._query(tr, b'sentinel', b'sentinels', self.encode_from_native(name))
