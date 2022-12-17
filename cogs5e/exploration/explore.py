import asyncio
import logging
import math
import discord
import d20

import disnake.ext.commands
from typing import List
import cachetools
from cogs5e.templates.ongoing_event import OngoingEvent
from cogs5e.models.errors import NoCharacter
from utils.functions import search_and_select
from .encounter import Encounter
from .types import ExplorerType
from .explorer import Explorer, PlayerExplorer
from .group import ExplorerGroup
from .errors import *
from utils.dice import VerboseMDStringifier
log = logging.getLogger(__name__)


class Explore(OngoingEvent):
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
        enctimer: int = 0,
        encthreshold: int = 0,
        chance: int = 100
    ):
        super().__init__(
            channel_id=channel_id,
            message_id=message_id,
            dm_id=dm_id,
            options=options,
            ctx=ctx,
            participants=explorers,
            round_num=round_num,
        )
        if explorers is None:
            explorers = []
        self._channel = str(channel_id)  # readonly
        self._summary = int(message_id)  # readonly
        self._dm = str(dm_id)
        self._options = options  # readonly (?)
        self._explorers = explorers
        self._round = round_num
        self.ctx = ctx
        self._enctimer = enctimer
        self._encthreshold = encthreshold
        self._chance = chance

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
            raw["enctimer"],
            raw["encthreshold"],
            raw["chance"],
        )
        for e in raw["explorers"]:
            inst._explorers.append(await deserialize_explorer(e, ctx, inst))
        return inst

    # sync deser/ser
    @classmethod
    def from_ctx_sync(cls, ctx):  # cached
        channel_id = str(ctx.channel.id)
        try:
            return cls._cache[channel_id]
        except KeyError:
            raw = ctx.bot.mdb.explorations.delegate.find_one({"channel": channel_id})
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
            raw["enctimer"],
            raw["encthreshold"],
            raw["chance"],
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
            "enctimer": self.enctimer,
            "encthreshold": self.encthreshold,
            "chance": self._chance
        }

    # members

    @property
    def enctimer(self):
        return self._enctimer

    @enctimer.setter
    def enctimer(self, value):
        self._enctimer = value

    @property
    def encthreshold(self):
        return self._encthreshold

    @encthreshold.setter
    def encthreshold(self, value):
        self._encthreshold = value

    @property
    def chance(self):
        return self._chance

    @chance.setter
    def chance(self, value):
        self._chance = value

    def set_chance(self, percent):
        if percent > 100:
            self.chance = 100
        elif percent < 1:
            self.chance = 1
        else:
            self.chance = percent

    def set_enc_timer(self, number):
        self.encthreshold = number
        self.enctimer = number

    async def skip_rounds(self, ctx, num_rounds):
        messages = []
        try:
            enc = await ctx.get_encounter()
        except NoEncounter:
            enc = None
        if self._enctimer != 0 and enc is not None:
            div = num_rounds // self._enctimer
            mod = num_rounds % self._enctimer
            log.warning(mod)
            log.warning(self._enctimer)
            if div == 0:
                self._enctimer -= num_rounds
            else:
                self._enctimer = self._encthreshold - mod
                encounter_list = enc.roll_encounters(div, self.chance)
                encounter_strs = ["Random encounters rolled:\n"]
                for enc in encounter_list:
                    if enc[1] is None:
                        encounter_strs.append(f"{enc[2]}) {enc[0]}")
                    else:
                        encounter_strs.append(f"{enc[2]}) {enc[1]} {enc[0]}")
                encounter_strs = "\n".join(encounter_strs)
                messages.append(encounter_strs)
        self._round += num_rounds
        for exp in self.get_participants():
            exp.on_round(num_rounds)
            exp.on_round_end(num_rounds)

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
        name = self.options.get("name") if self.options.get("name") else "Exploration"
        duration = self.duration_str(self.round_num)

        out = f"```md\n{name} ({duration})\n"
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

    async def final(self):
        """Commit, update the summary message, and fire any recorder events in parallel."""
        await asyncio.gather(self.commit(), self.update_summary())

    @staticmethod
    def duration_str(round_num):
        # build string
        remaining = round_num
        if math.isinf(remaining):
            return ""
        elif remaining > 5_256_000:  # years
            divisor, unit = 5256000, "year"
        elif remaining > 438_000:  # months
            divisor, unit = 438000, "month"
        elif remaining > 100_800:  # weeks
            divisor, unit = 100800, "week"
        elif remaining > 14_400:  # days
            divisor, unit = 14400, "day"
        elif remaining > 600:  # hours
            divisor, unit = 600, "hour"
        elif remaining > 10:  # minutes
            divisor, unit = 10, "minute"
        else:  # rounds
            divisor, unit = 1, "second"

        rounded = round(remaining / divisor, 1) if divisor > 1 else remaining * 6
        return f"[{rounded} {unit}s]"


async def deserialize_encounter(raw_encounter):
    return Encounter.from_dict(raw_encounter)
