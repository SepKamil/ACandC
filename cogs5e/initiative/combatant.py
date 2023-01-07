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
from .errors import CombatException, RequiresContext
from .types import BaseCombatant, CombatantType
from .utils import create_combatant_id
from ..templates.participant import Participant, PlayerParticipant


class Combatant(Participant):
    DESERIALIZE_MAP = DESERIALIZE_MAP  # allow making class-specific deser maps
    type = CombatantType.GENERIC

    def __init__(
        self,
        # init metadata
        ctx,
        combat,
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
            ctx=ctx,
            ongoing_event=combat,
            id=id,
            name=name,
            controller_id=controller_id,
            private=private,
            init=init,
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
        self.combat = combat
        self.id = id

        self._controller = controller_id
        self._init = init
        self._private = private
        self._index = index  # combat write only; position in combat
        self._notes = notes
        self._effects = effects
        self._group_id = group_id

        self._cache = {}

    @classmethod
    def new(
        cls,
        name: str,
        controller_id: str,
        init: int,
        init_skill: Skill,
        max_hp: int,
        ac: int,
        private: bool,
        resists: Resistances,
        ctx,
        combat,
    ):
        skills = Skills.default()
        skills.update({"initiative": init_skill})
        levels = Levels({"Monster": 0})
        id = create_combatant_id()
        return cls(
            ctx,
            combat,
            id,
            name,
            controller_id,
            private,
            init,
            levels=levels,
            resistances=resists,
            skills=skills,
            max_hp=max_hp,
            ac=ac,
        )

    pass


class MonsterCombatant(Combatant):
    DESERIALIZE_MAP = {**DESERIALIZE_MAP, "spellbook": MonsterCastableSpellbook}
    type = CombatantType.MONSTER

    def __init__(
        self,
        # init metadata
        ctx,
        combat,
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
        # monster specific
        monster_name=None,
        monster_id=None,
        creature_type=None,
        **_,
    ):
        super(MonsterCombatant, self).__init__(
            ctx,
            combat,
            id,
            name,
            controller_id,
            private,
            init,
            index,
            notes,
            effects,
            group_id,
            stats,
            levels,
            attacks,
            skills,
            saves,
            resistances,
            spellbook,
            ac,
            max_hp,
            hp,
            temp_hp,
            creature_type=creature_type,
        )
        self._monster_name = monster_name
        self._monster_id = monster_id

    @classmethod
    def from_monster(cls, monster, ctx, combat, name, controller_id, init, private, hp=None, ac=None):
        monster_name = monster.name
        creature_type = monster.creature_type
        hp = int(monster.hp) if not hp else int(hp)
        ac = int(monster.ac) if not ac else int(ac)
        id = create_combatant_id()

        # copy spellbook
        spellbook = None
        if monster.spellbook is not None:
            spellbook = MonsterCastableSpellbook.copy(monster.spellbook)

        # copy resistances (#1134)
        resistances = monster.resistances.copy()

        return cls(
            ctx,
            combat,
            id,
            name,
            controller_id,
            private,
            init,
            # statblock info
            stats=monster.stats,
            levels=monster.levels,
            attacks=monster.attacks,
            skills=monster.skills,
            saves=monster.saves,
            resistances=resistances,
            spellbook=spellbook,
            ac=ac,
            max_hp=hp,
            # monster specific
            monster_name=monster_name,
            monster_id=monster.entity_id,
            creature_type=creature_type,
        )

    # ser/deser
    @classmethod
    def from_dict(cls, raw, ctx, combat):
        inst = super().from_dict(raw, ctx, combat)
        inst._monster_name = raw["monster_name"]
        inst._monster_id = raw.get("monster_id")
        return inst

    def to_dict(self):
        raw = super().to_dict()
        raw.update({"monster_name": self._monster_name, "monster_id": self._monster_id})
        return raw

    # members
    @property
    def monster_name(self):
        return self._monster_name

    @property
    def monster_id(self):
        return self._monster_id


class PlayerCombatant(PlayerParticipant):
    type = CombatantType.PLAYER

    def __init__(
        self,
        # init metadata
        ctx,
        combat,
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
        # note that the player combatant doesn't initialize the statblock
        # because we want the combatant statblock attrs to reference the character attrs
        super().__init__(
            ctx,
            combat,
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

    pass
