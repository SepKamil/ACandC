import asyncio

from typing import List, Optional

import cachetools
import discord
import disnake.ext.commands
from d20 import roll

from cogs5e.models.errors import NoCharacter
from utils.functions import search_and_select
from .participant import Participant, PlayerParticipant
from .errors import *
from .group import ParticipantGroup
from .types import ParticipantType

COMBAT_TTL = 60 * 60 * 24 * 7  # 1 week TTL
participant_name = 'participant'
participant_name_plural = 'participants'
participant_name_capital = 'Participant'
ongoing_event_name = 'ongoing event'
ongoing_event_name_capital = 'Ongoing event'
article = 'an'


# ==== code ====
class OngoingEvent:
    # cache ongoing_events for 10 seconds to avoid race conditions
    # this makes sure that multiple calls to OngoingEvent.from_ctx() in the same invocation or two simultaneous ones
    # retrieve/modify the same OngoingEvent state
    # caches based on channel id
    # probably won't encounter any scaling issues, since a ongoing_event will be shard-specific
    _cache = cachetools.TTLCache(maxsize=50, ttl=10)

    def __init__(
        self,
        channel_id: str,
        message_id: int,
        dm_id: str,
        options: dict,
        ctx: disnake.ext.commands.Context,
        participants: List[Participant] = None,
        round_num: int = 0,
        current_index: Optional[int] = None,
        metadata: dict = None,
    ):
        if participants is None:
            participants = []
        if metadata is None:
            metadata = {}
        self._channel = str(channel_id)  # readonly
        self._summary = int(message_id)  # readonly
        self._dm = str(dm_id)
        self._options = options  # readonly (?)
        self._participants = participants
        self._round = round_num
        self._current_index = current_index
        self.ctx = ctx
        self._metadata = metadata

    @classmethod
    def new(cls, channel_id, message_id, dm_id, options, ctx):
        return cls(channel_id, message_id, dm_id, options, ctx)

    # async deser
    @classmethod
    async def from_ctx(cls, ctx):  # cached
        channel_id = str(ctx.channel.id)
        return await cls.from_id(channel_id, ctx)

    @classmethod
    async def from_id(cls, channel_id, ctx):
        try:
            return cls._cache[channel_id]
        except KeyError:
            raw = await ctx.bot.mdb.ongoing_events.find_one({"channel": channel_id})
            if raw is None:
                raise OEventNotFound()
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
            raw["current"],
            raw.get("metadata"),
        )
        for c in raw["participants"]:
            inst._participants.append(await deserialize_participant(c, ctx, inst))
        return inst

    # sync deser/ser
    @classmethod
    def from_ctx_sync(cls, ctx):  # cached
        channel_id = str(ctx.channel.id)
        try:
            return cls._cache[channel_id]
        except KeyError:
            raw = ctx.bot.mdb.ongoing_events.delegate.find_one({"channel": channel_id})
            if raw is None:
                raise OEventNotFound
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
            raw["current"],
            raw.get("metadata"),
        )
        for c in raw["participants"]:
            inst._participants.append(deserialize_participant_sync(c, ctx, inst))
        return inst

    def to_dict(self):
        return {
            "channel": self.channel,
            "summary": self.summary,
            "dm": self.dm,
            "options": self.options,
            "participants": [c.to_dict() for c in self._participants],
            "round": self.round_num,
            "current": self._current_index,
            "metadata": self._metadata,
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

    @property  # private write
    def turn_num(self):
        return self._turn

    @property  # private write
    def index(self):
        return self._current_index

    @property
    def _participant_id_map(self):
        return {c.id: c for c in self.get_participants(groups=True)}

    # participants
    @property
    def participants(self):
        f"""
        A read-only copy of the {participant_name} list.
        Note that this will not update if the underlying {participant_name} list changes.
        Use this to access {article} {participant_name} given its index.
        """
        return tuple(self._participants)

    @property
    def current_participant(self):
        f"""
        The {participant_name} whose turn it currently is.

        :rtype: Participant
        """
        if self.index is None:
            return None
        return self._participants[self.index]

    @property
    def next_participant(self):
        f"""The {participant_name} whose turn it will be when advance_turn() is called."""
        if len(self._participants) == 0:
            return None
        if self.index is None:
            index = 0
        elif self.index + 1 >= len(self._participants):
            index = 0
        else:
            index = self.index + 1
        return self._participants[index]

    def get_participants(self, groups=False):
        f"""
        Returns a list of all {participant_name_capital} in {article} {ongoing_event_name}, regardless of if they are in a group.
        Differs from ._{participant_name} since that won't yield {participant_name_plural} in groups.

        :param groups: Whether to return {participant_name_capital}Group objects in the list.
        :return: A list of all {participant_name_plural} (and optionally groups).
        """
        participants = []
        for c in self._participants:
            if not isinstance(c, ParticipantGroup):
                participants.append(c)
            else:
                participants.extend(c.get_participants())
                if groups:
                    participants.append(c)
        return participants

    def get_groups(self):
        f"""
        Returns a list of all {participant_name_capital}Groups in {article} {ongoing_event_name}
        :return: A list of all {participant_name_capital}Groups
        """
        return [g for g in self._participants if isinstance(g, ParticipantGroup)]

    def add_participant(self, participant):
        f"""
        Adds a participant to {ongoing_event_name}, and sorts the {participant_name} list by init.

        :type {participant_name}: {participant_name_capital}
        """
        self._participants.append(participant)
        self.sort_participants()

    def remove_participant(self, participant, ignore_remove_hook=False):
        f"""
        Removes a participant from {ongoing_event_name}, sorts the {participant_name} list by init (updates index), and fires the remove hook.

        :type {participant_name}: {participant_name_capital}
        :param bool ignore_remove_hook: Whether or not to ignore the remove hook.
        :rtype: {participant_name_capital}
        """
        if not ignore_remove_hook:
            participant.on_remove()
        if not participant.group:
            self._participants.remove(participant)
            self.sort_participants()
        else:
            self.get_group(participant.group).remove_participant(participant)
            self._check_empty_groups()
        return self

    # def sort_participants(self):
    #     f"""
    #     Sorts the participant list by place in init and updates {participant_name_plural}' indices.
    #     """
    #     if not self._participants:
    #         self._current_index = None
    #         self._turn = 0
    #         return
    #
    #     current = None
    #     if self._current_index is not None:
    #         current = next((c for c in self._participants if c.index == self._current_index), None)
    #
    #     self._participants = sorted(self._participants, key=lambda k: (k.init, int(k.init_skill)), reverse=True)
    #     for n, c in enumerate(self._participants):
    #         c.index = n
    #
    #     if current is not None:
    #         self._current_index = current.index
    #         self._turn = current.init
    #     else:
    #         self._current_index = None

    def participant_by_id(self, participant_id):
        """Gets a participant by their ID."""
        return self._participant_id_map.get(participant_id)

    def get_participant(self, name, strict=None):
        f"""Gets a participant by their name or ID.

        :param name: The name or id of the {participant_name}.
        :param strict: Whether {participant_name} name must be a full case insensitive match.
            If this is ``None`` (default), attempts a strict match with fallback to partial match.
            If this is ``False``, it returns the first partial match.
            If this is ``True``, it will only return a strict match.
        :return: The {participant_name} or None.
        """
        if name in self._participant_id_map:
            return self._participant_id_map[name]

        participant = None
        if strict is not False:
            participant = next((c for c in self.get_participants() if name.lower() == c.name.lower()), None)
        if not participant and not strict:
            participant = next((c for c in self.get_participants() if name.lower() in c.name.lower()), None)
        return participant

    def get_group(self, name, create=None, strict=None):
        f"""
        Gets a {participant_name} group by its name or ID.

        :rtype: {participant_name_capital}Group
        :param name: The name of the {participant_name} group.
        :param create: The initiative to create a group at if a group is not found.
        :param strict: Whether {participant_name} name must be a full case insensitive match.
            If this is ``None`` (default), attempts a strict match with fallback to partial match.
            If this is ``False``, it returns the first partial match.
            If this is ``True``, it will only return a strict match.
        :return: The participant group.
        """
        if name in self._participant_id_map and isinstance(self._participant_id_map[name], ParticipantGroup):
            return self._participant_id_map[name]

        grp = None
        if strict is not False:
            grp = next((g for g in self.get_groups() if g.name.lower() == name.lower()), None)
        if not grp and not strict:
            grp = next((g for g in self.get_groups() if name.lower() in g.name.lower()), None)

        if grp is None and create is not None:
            grp = ParticipantGroup.new(self, name, init=create, ctx=self.ctx)
            self.add_participant(grp)

        return grp

    def _check_empty_groups(self):
        f"""Removes any empty groups in the {ongoing_event_name}."""
        # removed = False
        for c in self._participants:
            if isinstance(c, ParticipantGroup) and len(c.get_participants()) == 0:
                 self.remove_participant(c)
        #         removed = True
        # if removed:
        #     self.sort_participants()

    # def reroll_dynamic(self):
    #     f"""
    #     Rerolls all {participant_name} initiatives. Returns a string representing the new init order.
    #     """
    #     rolls = {}
    #     for c in self._participants:
    #         init_roll = roll(c.init_skill.d20())
    #         c.init = init_roll.total
    #         rolls[c] = init_roll
    #     self.sort_participants()
    #
    #     # reset current turn
    #     self.end_round()
    #
    #     order = []
    #     for participant, init_roll in sorted(
    #         rolls.items(), key=lambda r: (r[1].total, int(r[0].init_skill)), reverse=True
    #     ):
    #         order.append(f"{init_roll.result}: {participant.name}")
    #
    #     order = "\n".join(order)
    #
    #     return order

    # def end_round(self):
    #     f"""
    #     Moves initiative to just before the next round (no active {participant_name} or group).
    #     """
    #     self._turn = 0
    #     self._current_index = None

    async def select_participant(self, name, choice_message=None, select_group=False):
        f"""
        Opens a prompt for a user to select the {participant_name} they were searching for.

        :param choice_message: The message to pass to the selector.
        :param select_group: Whether to allow groups to be selected.
        :rtype: {participant_name_capital}
        :param name: The name of the {participant_name} to search for.
        :return: The selected {participant_name_capital}, or None if the search failed.
        """
        return await search_and_select(
            self.ctx,
            self.get_participants(select_group),
            name,
            lambda c: c.name,
            message=choice_message,
            selectkey=lambda c: f"{c.name} {c.hp_str()}",
        )

    def advance_turn(self):
        """Advances the turn. If any caveats should be noted, returns them in messages."""
        if len(self._participants) == 0:
            raise NoParticipants

        messages = []

        # if self.current_participant:
        #     self.current_participant.on_turn_end()

        changed_round = False
        if self.index is None:  # new round, no dynamic reroll
            self._current_index = 0
            self._round += 1
        elif self.index + 1 >= len(self._participants):  # new round
            # if self.options.get("dynamic"):
            #     messages.append(f"New initiatives:\n{self.reroll_dynamic()}")
            # self._current_index = 0
            self._round += 1
            changed_round = True
        # else:
        #     self._current_index += 1

        # self._turn = self.current_participant.init
        # self.current_participant.on_turn()
        return changed_round, messages

    # def rewind_turn(self):
    #     if len(self._participants) == 0:
    #         raise NoParticipants
    #
    #     # if self.current_participant:
    #     #     self.current_participant.on_turn_end()
    #
    #     if self.index is None:  # start of ongoing_event
    #         self._current_index = len(self._participants) - 1
    #     elif self.index == 0:  # new round
    #         self._current_index = len(self._participants) - 1
    #         self._round -= 1
    #     else:
    #         self._current_index -= 1
    #
    #     self._turn = self.current_participant.init

    # def goto_turn(self, init_num, is_participant=False):
    #     if len(self._participants) == 0:
    #         raise NoParticipants
    #
    #     if self.current_participant:
    #         self.current_participant.on_turn_end()
    #
    #     if is_participant:
    #         if init_num.group:
    #             init_num = self.get_group(init_num.group)
    #         self._current_index = init_num.index
    #     else:
    #         target = next((c for c in self._participants if c.init <= init_num), None)
    #         if target:
    #             self._current_index = target.index
    #         else:
    #             self._current_index = 0
    #
    #     self._turn = self.current_participant.init

    def skip_rounds(self, num_rounds):
        messages = []

        self._round += num_rounds
        for com in self.get_participants():
            com.on_turn(num_rounds)
            com.on_turn_end(num_rounds)
        if self.options.get("dynamic"):
            messages.append(f"New initiatives:\n{self.reroll_dynamic()}")

        return messages

    async def end(self):
        f"""Ends {ongoing_event_name} in a channel."""
        for c in self._participants:
            c.on_remove()
        await self.ctx.bot.mdb.ongoing_events.delete_one({"channel": self.channel})
        try:
            del OngoingEvent._cache[self.channel]
        except KeyError:
            pass

    # stringification
    # def get_turn_str(self):
    #     f"""Gets the string representing the current turn, and all {participant_name_plural} on it."""
    #     participant = self.current_participant
    #
    #     if participant is None:
    #         return None
    #
    #     if isinstance(participant, ParticipantGroup):
    #         participants = participant.get_participants()
    #         participant_statuses = "\n".join([co.get_status() for co in participants])
    #         mentions = ", ".join({co.controller_mention() for co in participants})
    #         out = (
    #             f"**Initiative {self.turn_num} (round {self.round_num})**: {participant.name} ({mentions})\n"
    #             f"```md\n{participant_statuses}```"
    #         )
    #
    #     else:
    #         out = (
    #             f"**Initiative {self.turn_num} (round {self.round_num})**: {participant.name} "
    #             f"({participant.controller_mention()})\n```md\n{participant.get_status()}```"
    #         )
    #
    #     if self.options.get("turnnotif"):
    #         nextTurn = self.next_participant
    #         out += f"**Next up**: {nextTurn.name} ({nextTurn.controller_mention()})\n"
    #     return out
    #
    # def get_turn_str_mentions(self):
    #     """Gets the :class:`discord.AllowedMentions` for the users mentioned in the current turn str."""
    #     if self.current_participant is None:
    #         return discord.AllowedMentions.none()
    #     if isinstance(self.current_participant, ParticipantGroup):
    #         # noinspection PyUnresolvedReferences
    #         user_ids = {discord.Object(id=int(comb.controller)) for comb in self.current_participant.get_participants()}
    #     else:
    #         user_ids = {discord.Object(id=int(self.current_participant.controller))}
    #
    #     if self.options.get("turnnotif") and self.next_participant is not None:
    #         user_ids.add(discord.Object(id=int(self.next_participant.controller)))
    #     return discord.AllowedMentions(users=list(user_ids))

    def get_summary(self, private=False):
        """Returns the generated summary message (pinned) content."""
        participants = self._participants
        name = self.options.get("name") if self.options.get("name") else "Current initiative"

        out = f"```md\n{name}: {self.turn_num} (round {self.round_num})\n"
        out += f"{'=' * (len(out) - 7)}\n"

        participant_strs = []
        for c in participants:
            participant_str = c.get_summary(private)
            participant_strs.append(participant_str)

        out += "{}```"
        if len(out.format("\n".join(participant_strs))) > 2000:
            participant_strs = []
            for c in participants:
                participant_str = c.get_summary(private, no_notes=True)
                participant_strs.append(participant_str)
        return out.format("\n".join(participant_strs))

    # db
    async def commit(self):
        f"""Commits the {ongoing_event_name} to db."""
        if not self.ctx:
            raise RequiresContext
        for pc in self.get_participants():
            if isinstance(pc, PlayerParticipant):
                await pc.character.commit(self.ctx)
        await self.ctx.bot.mdb.ongoing_events.update_one(
            {"channel": self.channel}, {"$set": self.to_dict(), "$currentDate": {"lastchanged": True}}, upsert=True
        )

    async def final(self):
        """Commit, update the summary message in parallel."""
        await asyncio.gather(self.commit(), self.update_summary())

    # misc
    @staticmethod
    async def ensure_unique_chan(ctx):
        if await ctx.bot.mdb.ongoing_events.find_one({"channel": str(ctx.channel.id)}):
            raise ChannelInUse

    async def update_summary(self):
        """Edits the summary message with the latest summary."""
        await self.get_summary_msg().edit(content=self.get_summary())

    def get_channel(self):
        f"""Gets the Channel object of the {ongoing_event_name}."""
        if self.ctx:
            return self.ctx.channel
        else:
            chan = self.ctx.bot.get_channel(int(self.channel))
            if chan:
                return chan
            else:
                raise OEventChannelNotFound()

    def get_summary_msg(self):
        f"""Gets the Message object of the {ongoing_event_name} summary."""
        return discord.PartialMessage(channel=self.get_channel(), id=self.summary)

    def __str__(self):
        return f"Initiative in <#{self.channel}>"


async def deserialize_participant(raw_participant, ctx, ongoing_event):
    ctype = ParticipantType(raw_participant["type"])
    if ctype == ParticipantType.GENERIC:
        return Participant.from_dict(raw_participant, ctx, ongoing_event)
    elif ctype == ParticipantType.PLAYER:
        try:
            return await PlayerParticipant.from_dict(raw_participant, ctx, ongoing_event)
        except NoCharacter:
            # if the character was deleted, make a best effort to restore what we know
            # note: PlayerParticipant.from_dict mutates raw_participant so we don't have to call the normal from_dict
            # operations here (this is hacky)
            return Participant(ctx, ongoing_event, **raw_participant)
    elif ctype == ParticipantType.GROUP:
        return await ParticipantGroup.from_dict(raw_participant, ctx, ongoing_event)
    else:
        raise OEventException(f"Unknown {participant_name} type: {raw_participant['type']}")


def deserialize_participant_sync(raw_participant, ctx, ongoing_event):
    ctype = ParticipantType(raw_participant["type"])
    if ctype == ParticipantType.GENERIC:
        return Participant.from_dict(raw_participant, ctx, ongoing_event)
    elif ctype == ParticipantType.PLAYER:
        try:
            return PlayerParticipant.from_dict_sync(raw_participant, ctx, ongoing_event)
        except NoCharacter:
            # if the character was deleted, make a best effort to restore what we know
            # note: PlayerParticipant.from_dict mutates raw_participant so we don't have to call the normal from_dict
            # operations here (this is hacky)
            return Participant(ctx, ongoing_event, **raw_participant)
    elif ctype == ParticipantType.GROUP:
        return ParticipantGroup.from_dict_sync(raw_participant, ctx, ongoing_event)
    else:
        raise OEventException(f"Unknown {participant_name} type: {raw_participant['type']}")
