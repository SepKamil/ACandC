import disnake.ext.commands
from typing import Any, List, Optional, TYPE_CHECKING
import cachetools

from .types import ExplorerType
from .explorer import Explorer, PlayerExplorer
from .group import ExplorerGroup
from .errors import *
from cogs5e.models.errors import NoCharacter


class Explore:
    # cache exploration for 10 seconds to avoid race conditions
    # this makes sure that multiple calls to Explore.from_ctx() in the same invocation or two simultaneous ones
    # retrieve/modify the same Explore state
    # caches based on channel id
    # probably won't encounter any scaling issues, since an exploration will be shard-specific
    _cache = cachetools.TTLCache(maxsize=50, ttl=10)

    def __init__(
        self,
        channel_id: str,
        message_id: int,
        dm_id: str,
        options: dict,
        ctx: disnake.ext.commands.Context,
        explorers: List[Explorer] = None,
        round_num: int = 0,
    ):
        self._channel = str(channel_id)  # readonly
        self._summary = int(message_id)  # readonly
        self._dm = str(dm_id)
        self._options = options  # readonly (?)
        self._explorers = explorers
        self._round = round_num
        self.ctx = ctx

    @classmethod
    def new(cls, channel_id, message_id, dm_id, options, ctx):
        return cls(channel_id, message_id, dm_id, options, ctx)

    @classmethod
    async def from_ctx(cls, ctx):  # cached
        channel_id = str(ctx.channel.id)
        return await cls.from_id(channel_id, ctx)

    @classmethod
    async def from_id(cls, channel_id, ctx):
        try:
            return cls._cache[channel_id]
        except KeyError:
            raw = await ctx.bot.mdb.explorations.find_one({"channel": channel_id})
            if raw is None:
                raise ExplorationNotFound()
            # write to cache
            inst = await cls.from_dict(raw, ctx)
            cls._cache[channel_id] = inst
            return inst

    @classmethod
    async def from_dict(cls, raw, ctx):
        inst = cls(
            raw["channel"],
            raw["summary"],
            raw["dm"],
            raw["options"],
            ctx,
            [],
            raw["round"],
        )
        for c in raw["explorers"]:
            inst._explorers.append(await deserialize_explorer(c, ctx, inst))
        return inst

    # members
    @property
    def channel(self):
        return self._channel

    @property
    def summary(self):
        return self._summary

    @summary.setter
    def summary(self, new_summary: int):
        self._summary = new_summary

    @property
    def dm(self):
        return self._dm

    @property
    def options(self):
        return self._options

    @options.setter
    def options(self, value):
        self._options = value

    @property
    def round_num(self):
        return self._round

    @round_num.setter
    def round_num(self, value):
        self._round = value

    @property
    def _explorer_id_map(self):
        return {c.id: c for c in self.get_explorers(groups=True)}

    # explorers
    @property
    def explorers(self):
        """
        A read-only copy of the explorer list.
        Note that this will not update if the underlying explorer list changes.
        Use this to access an explorer given its index.
        """
        return tuple(self._explorers)

    def get_explorers(self, groups=False):
        """
        Returns a list of all Explorers in an exploration, regardless of if they are in a group.
        Differs from ._explorers since that won't yield explorers in groups.

        :param groups: Whether to return ExplorerGroup objects in the list.
        :return: A list of all explorers (and optionally groups).
        """
        explorers = []
        for c in self._explorers:
            if not isinstance(c, ExplorerGroup):
                explorers.append(c)
            else:
                explorers.extend(c.get_explorers())
                if groups:
                    explorers.append(c)
        return explorers

    # misc
    @staticmethod
    async def ensure_unique_chan(ctx):
        if await ctx.bot.mdb.explorations.find_one({"channel": str(ctx.channel.id)}):
            raise ChannelInUse


async def deserialize_explorer(raw_explorer, ctx, exploration):
    ctype = ExplorerType(raw_explorer["type"])
    if ctype == ExplorerType.GENERIC:
        return Explorer.from_dict(raw_explorer, ctx, exploration)
    elif ctype == ExplorerType.PLAYER:
        try:
            return await PlayerExplorer.from_dict(raw_explorer, ctx, exploration)
        except NoCharacter:
            # if the character was deleted, make a best effort to restore what we know
            # note: PlayerExplorer.from_dict mutates raw_explorer so we don't have to call the normal from_dict
            # operations here (this is hacky)
            return Explorer(ctx, exploration, **raw_explorer)
    else:
        raise ExplorationException(f"Unknown explorer type: {raw_explorer['type']}")


def deserialize_explorer_sync(raw_explorer, ctx, exploration):
    ctype = ExplorerType(raw_explorer["type"])
    if ctype == ExplorerType.GENERIC:
        return Explore.from_dict(raw_explorer, ctx, exploration)
    elif ctype == ExplorerType.PLAYER:
        try:
            return PlayerExplorer.from_dict_sync(raw_explorer, ctx, exploration)
        except NoCharacter:
            # if the character was deleted, make a best effort to restore what we know
            # note: PlayerExplorer.from_dict mutates raw_explorer so we don't have to call the normal from_dict
            # operations here (this is hacky)
            return Explorer(ctx, exploration, **raw_explorer)
    elif ctype == ExplorerType.GROUP:
        return ExplorerGroup.from_dict_sync(raw_explorer, ctx, exploration)
    else:
        raise ExplorationException(f"Unknown explorer type: {raw_explorer['type']}")
