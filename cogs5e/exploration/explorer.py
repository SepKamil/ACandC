import discord

import cogs5e.models.character
from cogs5e.models.errors import NoCharacter
from cogs5e.models.sheet.attack import AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skill, Skills
from cogs5e.models.sheet.resistance import Resistance, Resistances
from cogs5e.models.sheet.spellcasting import Spellbook
from cogs5e.models.sheet.statblock import DESERIALIZE_MAP, StatBlock
from gamedata.monster import MonsterCastableSpellbook
from utils.constants import RESIST_TYPES
from utils.functions import combine_maybe_mods, get_guild_member, search_and_select
from .effect import Effect
from .errors import ExplorationException, RequiresContext
from .types import BaseExplorer, ExplorerType
from .utils import create_explorer_id


class Explorer(BaseExplorer, StatBlock):
    DESERIALIZE_MAP = DESERIALIZE_MAP  # allow making class-specific deser maps
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
        init: int,
        index: int = None,
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
            name=name,
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
        self._init = init

        self._private = private
        self._index = index
        self._notes = notes
        self._effects = effects
        self._group_id = group_id

        self._cache = {}

    @classmethod
    def new(
        cls,
        name: str,
        controller_id: str,
        ctx,
        exploration,
    ):
        skills = Skills.default()

        levels = Levels({"Monster": 0})
        id = create_explorer_id()
        return cls(
            ctx,
            exploration,
            id,
            name,
            controller_id,
            levels=levels,
            skills=skills
        )

    @classmethod
    def from_dict(cls, raw, ctx, exploration):
        for key, klass in cls.DESERIALIZE_MAP.items():
            if key in raw:
                raw[key] = klass.from_dict(raw[key])
        del raw["type"]
        effects = raw.pop("effects")
        inst = cls(ctx, exploration, **raw)
        inst._effects = [Effect.from_dict(e, exploration, inst) for e in effects]
        return inst


class PlayerExplorer(Explorer):
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
        init: int,
        index: int = None,
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
        # note that the player explorer doesn't initialize the statblock
        # because we want the explorer statblock attrs to reference the character attrs
        super().__init__(
            ctx,
            exploration,
            id,
            name,
            controller_id,
            private,
            init,
            index,
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

    @classmethod
    async def from_character(cls, character, ctx, exploration, controller_id, init, private):
        id = create_explorer_id()
        inst = cls(
            ctx,
            exploration,
            id,
            character.name,
            controller_id,
            private,
            init,
            # statblock copies
            resistances=character.resistances.copy(),
            # character specific
            character_id=character.upstream,
            character_owner=character.owner,
        )
        inst._character = character
        return inst

    # ==== serialization ====
    @classmethod
    async def from_dict(cls, raw, ctx, exploration):
        inst = super().from_dict(raw, ctx, exploration)
        inst.character_id = raw["character_id"]
        inst.character_owner = raw["character_owner"]
        inst._character = await cogs5e.models.character.Character.from_bot_and_ids(
            ctx.bot, inst.character_owner, inst.character_id
        )
        return inst

    @classmethod
    def from_dict_sync(cls, raw, ctx, exploration):
        inst = super().from_dict(raw, ctx, exploration)
        inst.character_id = raw["character_id"]
        inst.character_owner = raw["character_owner"]
        inst._character = cogs5e.models.character.Character.from_bot_and_ids_sync(
            ctx.bot, inst.character_owner, inst.character_id
        )
        return inst

    def to_dict(self):
        ignored_attributes = ("stats", "levels", "skills", "saves", "spellbook", "hp", "temp_hp")
        raw = super().to_dict()
        for attr in ignored_attributes:
            del raw[attr]
        raw.update({"character_id": self.character_id, "character_owner": self.character_owner})
        return raw

    # ==== helpers ====
    async def update_character_ref(self, ctx, inst=None):
        """
        Updates the character reference in self._character to ensure that it references the cached Character instance
        if one is cached (since Exploration cache TTL > Character cache TTL), preventing instance divergence.

        If ``inst`` is passed, sets the character to reference the given instance, otherwise retrieves it via the normal
        Character init flow (from cache or db). ``inst`` should be a Character instance with the same character ID and
        owner as ``self._character``.
        """
        if inst is not None:
            self._character = inst
            return

        # retrieve from character constructor
        self._character = await cogs5e.models.character.Character.from_bot_and_ids(
            ctx.bot, self.character_owner, self.character_id
        )

    # ==== members ====
    @property
    def character(self):
        return self._character

    @property
    def init_skill(self):
        return self.character.skills.initiative

    @property
    def stats(self):
        return self.character.stats

    @property
    def levels(self):
        return self.character.levels

    @property
    def skills(self):
        return self.character.skills

    @property
    def saves(self):
        return self.character.saves

    @property
    def ac(self):
        _ac = self._ac or self.character.ac
        _ac = combine_maybe_mods(self.active_effects("ac"), base=_ac)
        return _ac

    @ac.setter
    def ac(self, new_ac):
        """
        :param int|None new_ac: The new AC
        """
        self._ac = new_ac

    @property
    def spellbook(self):
        return self.character.spellbook

    @property
    def max_hp(self):
        _maxhp = self._max_hp or self.character.max_hp
        _maxhp = combine_maybe_mods(self.active_effects("maxhp"), base=_maxhp)
        return _maxhp

    @max_hp.setter
    def max_hp(self, new_max_hp):
        self._max_hp = new_max_hp

    @property
    def hp(self):
        return self.character.hp

    @hp.setter
    def hp(self, new_hp):
        self.character.hp = new_hp

    def set_hp(self, new_hp):
        return self.character.set_hp(new_hp)

    def reset_hp(self):
        return self.character.reset_hp()

    @property
    def temp_hp(self):
        return self.character.temp_hp

    @temp_hp.setter
    def temp_hp(self, new_hp):
        self.character.temp_hp = new_hp

    @property
    def attacks(self):
        return super().attacks + self.character.attacks

    def get_scope_locals(self):
        return {**self.character.get_scope_locals(), **super().get_scope_locals()}

    def get_color(self):
        return self.character.get_color()
