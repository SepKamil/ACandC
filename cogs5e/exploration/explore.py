import asyncio

import discord
import disnake.ext.commands
from typing import Any, List, Optional, TYPE_CHECKING
import cachetools
from cogs5e.models.errors import NoCharacter
from utils.functions import search_and_select
from .types import ExplorerType
from .explorer import Explorer, PlayerExplorer
from .group import ExplorerGroup
from .errors import *



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

    # sync deser/ser
    @classmethod
    def from_ctx_sync(cls, ctx):  # cached
        channel_id = str(ctx.channel.id)
        try:
            return cls._cache[channel_id]
        except KeyError:
            raw = ctx.bot.mdb.combats.delegate.find_one({"channel": channel_id})
            if raw is None:
                raise ExplorationNotFound
            # write to cache
            inst = cls.from_dict_sync(raw, ctx)
            cls._cache[channel_id] = inst
            return inst

    @classmethod
    def from_dict_sync(cls, raw, ctx):
        inst = cls(
            raw["channel"],
            raw["summary"],
            raw["dm"],
            raw["options"],
            ctx,
            [],
            raw["round"],
        )
        for e in raw["explorers"]:
            inst._explorers.append(deserialize_explorer_sync(e, ctx, inst))
        return inst

    def to_dict(self):
        return {
            "channel": self.channel,
            "summary": self.summary,
            "dm": self.dm,
            "options": self.options,
            "explorers": [c.to_dict() for c in self._explorers],
            "round": self.round_num,
        }

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

    def get_groups(self):
        """
        Returns a list of all ExplorerGroups in an exploration
        :return: A list of all ExplorerGroups
        """
        return [g for g in self._explorers if isinstance(g, ExplorerGroup)]

    def add_explorer(self, explorer):
        """
        Adds a explorer to exploration

        :type explorer: Explorer
        """
        self._explorers.append(explorer)

    def remove_explorer(self, explorer, ignore_remove_hook=False):
        """
        Removes an explorer from exploration, and fires the remove hook.

        :type explorer: Explorer
        :param bool ignore_remove_hook: Whether or not to ignore the remove hook.
        :rtype: Explorer
        """
        if not ignore_remove_hook:
            explorer.on_remove()
        if not explorer.group:
            self._explorers.remove(explorer)
        else:
            self.get_group(explorer.group).remove_explorer(explorer)
            self._check_empty_groups()
        return self

    def explorer_by_id(self, explorer_id):
        """Gets an explorer by their ID."""
        return self._explorer_id_map.get(explorer_id)

    def get_explorer(self, name, strict=None):
        """Gets an explorer by their name or ID.

        :param name: The name or id of the explorer.
        :param strict: Whether explorer name must be a full case insensitive match.
            If this is ``None`` (default), attempts a strict match with fallback to partial match.
            If this is ``False``, it returns the first partial match.
            If this is ``True``, it will only return a strict match.
        :return: The explorer or None.
        """
        if name in self._explorer_id_map:
            return self._explorer_id_map[name]

        explorer = None
        if strict is not False:
            explorer = next((c for c in self.get_explorers() if name.lower() == c.name.lower()), None)
        if not explorer and not strict:
            explorer = next((c for c in self.get_explorers() if name.lower() in c.name.lower()), None)
        return explorer

    def get_group(self, name, create=None, strict=None):
        """
        Gets an explorer group by its name or ID.

        :rtype: ExplorerGroup
        :param name: The name of the explorer group.
        :param create: The initiative to create a group at if a group is not found.
        :param strict: Whether explorer name must be a full case insensitive match.
            If this is ``None`` (default), attempts a strict match with fallback to partial match.
            If this is ``False``, it returns the first partial match.
            If this is ``True``, it will only return a strict match.
        :return: The explorer group.
        """
        if name in self._explorer_id_map and isinstance(self._explorer_id_map[name], ExplorerGroup):
            return self._explorer_id_map[name]

        grp = None
        if strict is not False:
            grp = next((g for g in self.get_groups() if g.name.lower() == name.lower()), None)
        if not grp and not strict:
            grp = next((g for g in self.get_groups() if name.lower() in g.name.lower()), None)

        if grp is None and create is not None:
            grp = ExplorerGroup.new(self, name, init=create, ctx=self.ctx)
            self.add_explorer(grp)

        return grp

    def _check_empty_groups(self):
        """Removes any empty groups in the exploration."""
        removed = False
        for c in self._explorers:
            if isinstance(c, ExplorerGroup) and len(c.get_explorers()) == 0:
                self.remove_explorer(c)
                removed = True

    async def select_explorer(self, name, choice_message=None, select_group=False):
        """
        Opens a prompt for a user to select the explorer they were searching for.

        :param choice_message: The message to pass to the selector.
        :param select_group: Whether to allow groups to be selected.
        :rtype: Explorer
        :param name: The name of the explorer to search for.
        :return: The selected Explorer, or None if the search failed.
        """
        return await search_and_select(
            self.ctx,
            self.get_explorers(select_group),
            name,
            lambda c: c.name,
            message=choice_message,
            selectkey=lambda c: f"{c.name} {c.hp_str()}",
        )

    def skip_rounds(self, num_rounds):
        messages = []

        self._round += num_rounds
        for exp in self.get_explorers():
            exp.on_turn(num_rounds)
            exp.on_turn_end(num_rounds)

        return messages

    async def end(self):
        """Ends exploration in a channel."""
        for c in self._explorers:
            c.on_remove()
        await self.ctx.bot.mdb.explorations.delete_one({"channel": self.channel})
        try:
            del Explore._cache[self.channel]
        except KeyError:
            pass

    def get_summary(self, private=False):
        """Returns the generated summary message (pinned) content."""
        explorers = self._explorers
        name = self.options.get("name") if self.options.get("name") else "Current initiative"

        out = f"```md\n{name} (round {self.round_num})\n"
        out += f"{'=' * (len(out) - 7)}\n"

        explorer_strs = []
        for e in explorers:
            explorer_str = ("# " + e.get_summary(private))
            explorer_strs.append(explorer_str)

        out += "{}```"
        if len(out.format("\n".join(explorer_strs))) > 2000:
            explorer_strs = []
            for e in explorers:
                explorer_str = ("# " + e.get_summary(private, no_notes=True))
                explorer_strs.append(explorer_str)
        return out.format("\n".join(explorer_strs))

    # db
    async def commit(self):
        """Commits the exploration to db."""
        if not self.ctx:
            raise RequiresContext
        for pc in self.get_explorers():
            if isinstance(pc, PlayerExplorer):
                await pc.character.commit(self.ctx)
        await self.ctx.bot.mdb.explorations.update_one(
            {"channel": self.channel}, {"$set": self.to_dict(), "$currentDate": {"lastchanged": True}}, upsert=True
        )

    async def final(self):
        """Commit, update the summary message, and fire any recorder events in parallel."""
        await asyncio.gather(self.commit(), self.update_summary())

    # misc
    @staticmethod
    async def ensure_unique_chan(ctx):
        if await ctx.bot.mdb.explorations.find_one({"channel": str(ctx.channel.id)}):
            raise ChannelInUse

    async def update_summary(self):
        """Edits the summary message with the latest summary."""
        await self.get_summary_msg().edit(content=self.get_summary())

    def get_channel(self):
        """Gets the Channel object of the exploration."""
        if self.ctx:
            return self.ctx.channel
        else:
            chan = self.ctx.bot.get_channel(int(self.channel))
            if chan:
                return chan
            else:
                raise ExplorationChannelNotFound()

    def get_summary_msg(self):
        """Gets the Message object of the exploration summary."""
        return discord.PartialMessage(channel=self.get_channel(), id=self.summary)

    def __str__(self):
        return f"Initiative in <#{self.channel}>"


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
    elif ctype == ExplorerType.GROUP:
        return await ExplorerGroup.from_dict(raw_explorer, ctx, exploration)
    else:
        raise ExplorationException(f"Unknown explorer type: {raw_explorer['type']}")


def deserialize_explorer_sync(raw_explorer, ctx, exploration):
    ctype = ExplorerType(raw_explorer["type"])
    if ctype == ExplorerType.GENERIC:
        return Explorer.from_dict(raw_explorer, ctx, exploration)
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
