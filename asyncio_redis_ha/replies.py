import asyncio

from asyncio_redis.protocol import MultiBulkReply
from asyncio_redis.replies import ListReply, DictReply


class NestedListReply(ListReply):
    @asyncio.coroutine
    def aslist(self):
        """ Return the result as a Python ``list[list]``. """

        @asyncio.coroutine
        def _resolve_nested(multibulk: MultiBulkReply):
            result = []
            l1 = yield from ListReply(multibulk).aslist()
            """:type l1 list"""
            for x in l1:
                if isinstance(x, MultiBulkReply):
                    l2 = yield from _resolve_nested(x)
                    result.append(l2)
                else:
                    result.append(x)
            return result

        """:type data : list"""
        final = yield from _resolve_nested(self._result)
        return final


class NestedDictReply(ListReply):
    @asyncio.coroutine
    def aslist(self):
        """ Return the result as a Python ``list[dict]``. """
        final = []
        data = yield from super().aslist()
        """:type data : list"""
        for x in data:
            if isinstance(x, MultiBulkReply):
                x = DictReply(x)
                nested = yield from x.asdict()
                final.append(nested)
            else:
                final.append(x)
        return final
