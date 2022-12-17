import discord

import cogs5e.models.character
from cogs5e.templates.participant import Participant
from cogs5e.templates.participant import PlayerParticipant
from cogs5e.models.sheet.attack import AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skills
from cogs5e.models.sheet.resistance import Resistance, Resistances
from cogs5e.models.sheet.spellcasting import Spellbook
from cogs5e.models.sheet.statblock import DESERIALIZE_MAP
from utils.constants import RESIST_TYPES
from utils.functions import combine_maybe_mods, get_guild_member, search_and_select
from .effect import Effect
from .errors import ExplorationException, RequiresContext
from .types import ExplorerType
from .utils import create_explorer_id

participant_name = 'explorer'
participant_name_plural = 'explorers'
participant_name_capital = 'Explorer'
ongoing_event_name = 'exploration'
ongoing_event_name_capital = 'Exploration'
article = 'an'


class Explorer(Participant):
    DESERIALIZE_MAP = DESERIALIZE_MAP
    type = ExplorerType.GENERIC

    def __init__(
        self,
        # init metadata
        ctx,
        exploration,
        id: str,
        name: str,
        controller_id: str,
        private: bool,
        notes: str = None,
        effects: list = None,
        group_id: str = None,
        # statblock info
        stats: BaseStats = None,
        levels: Levels = None,
        attacks: AttackList = None,
        skills: Skills = None,
        saves: Saves = None,
        resistances: Resistances = None,
        spellbook: Spellbook = None,
        ac: int = None,
        max_hp: int = None,
        hp: int = None,
        temp_hp: int = 0,
        creature_type: str = None,
        **_,
    ):
        super().__init__(
            ctx=ctx,
            ongoing_event=exploration,
            id=id,
            name=name,
            controller_id=controller_id,
            private=private,
            notes=notes,
            effects=effects,
            group_id=group_id,
            stats=stats,
            levels=levels,
            attacks=attacks,
            skills=skills,
            saves=saves,
            resistances=resistances,
            spellbook=spellbook,
            ac=ac,
            max_hp=max_hp,
            hp=hp,
            temp_hp=temp_hp,
            creature_type=creature_type,
        )
        if effects is None:
            effects = []
        self.ctx = ctx
        self.exploration = exploration
        self.id = id

        self._controller = controller_id
        self._private = private
        self._notes = notes
        self._effects = effects
        self._group_id = group_id

        self._cache = {}

    pass


class PlayerExplorer(PlayerParticipant):
    DESERIALIZE_MAP = DESERIALIZE_MAP
    type = ExplorerType.PLAYER

    def __init__(
        self,
        # init metadata
        ctx,
        exploration,
        id: str,
        name: str,
        controller_id: str,
        private: bool,
        notes: str = None,
        effects: list = None,
        group_id: str = None,
        # statblock info
        attacks: AttackList = None,
        resistances: Resistances = None,
        ac: int = None,
        max_hp: int = None,
        # character specific
        character_id=None,
        character_owner=None,
        **_,
    ):
        super().__init__(
            ctx,
            exploration,
            id,
            name,
            controller_id,
            private,
            notes,
            effects,
            group_id,
            attacks=attacks,
            resistances=resistances,
            ac=ac,
            max_hp=max_hp,
        )
        self.character_id = character_id
        self.character_owner = character_owner

        self._character = None  # cache

    pass
