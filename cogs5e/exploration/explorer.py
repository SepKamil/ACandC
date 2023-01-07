from cogs5e.templates.participant import Participant
from cogs5e.templates.participant import PlayerParticipant
from cogs5e.models.sheet.attack import AttackList
from cogs5e.models.sheet.base import BaseStats, Levels, Saves, Skills
from cogs5e.models.sheet.resistance import Resistances
from cogs5e.models.sheet.spellcasting import Spellbook
from cogs5e.models.sheet.statblock import DESERIALIZE_MAP
from .types import ExplorerType

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
            init: int = 0,
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
        self.exploration = exploration
        self.id = id

        self._controller = controller_id
        self._private = private
        self._notes = notes
        self._effects = effects
        self._group_id = group_id

        self._cache = {}

    def on_turn(self, num_rounds=1):
        """
        A method called at the start of the round
        :param num_rounds: The number of rounds that just passed.
        :return: A string containing messages from effects
        """
        message_list = []
        s_name = self.name + "'s "
        for e in self.get_effects().copy():
            message_list.append(s_name + e.on_turn(num_rounds))
        for m in message_list:
            if m == s_name:
                message_list.remove(m)
        if len(message_list) > 0:
            final_str = "\n".join(message_list)
        else:
            final_str = ""
        return final_str


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
            init: int,
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
            init,
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

    def on_turn(self, num_rounds=1):
        """
        A method called at the start of the round
        :param num_rounds: The number of rounds that just passed.
        :return: A string containing messages from effects
        """
        message_list = []
        s_name = self.name + "'s "
        for e in self.get_effects().copy():
            message_list.append(s_name + e.on_turn(num_rounds))
        for m in message_list:
            if m == s_name:
                message_list.remove(m)
        if len(message_list) > 0:
            final_str = "\n".join(message_list)
        else:
            final_str = ""
        return final_str

    def hp_str(self, private=True):
        out = ""
        return out

