from .participant import Participant
from .types import ParticipantType
from .utils import create_participant_id


class ParticipantGroup(Participant):
    type = ParticipantType.GROUP

    def __init__(self, ctx, ongoing_event, id, participants, name, init, index=None, **_):
        super().__init__(
            ctx, ongoing_event, id, name=name, controller_id=str(ctx.author.id), private=False, init=init, index=index
        )
        self._participants = participants

    # noinspection PyMethodOverriding
    @classmethod
    def new(cls, ongoing_event, name, init, ctx=None):
        id = create_participant_id()
        return cls(ctx, ongoing_event, id, [], name, init)

    @classmethod
    async def from_dict(cls, raw, ctx, ongoing_event):
        # this import is here because Explore imports ParticipantGroup - it's a 1-time cost on first call but
        # practically free afterwards
        from .ongoing_event import deserialize_participant

        participants = []
        for c in raw.pop("participants"):
            participant = await deserialize_participant(c, ctx, ongoing_event)
            participants.append(participant)

        return cls(ctx, ongoing_event, participants=participants, **raw)

    @classmethod
    def from_dict_sync(cls, raw, ctx, ongoing_event):
        from .ongoing_event import deserialize_participant_sync

        participants = []
        for c in raw.pop("participants"):
            participant = deserialize_participant_sync(c, ctx, ongoing_event)
            participants.append(participant)

        return cls(ctx, ongoing_event, participants=participants, **raw)

    def to_dict(self):
        return {
            "name": self._name,
            "init": self._init,
            "participants": [c.to_dict() for c in self.get_participants()],
            "index": self._index,
            "type": "group",
            "id": self.id,
        }

    # members
    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name):
        self._name = new_name

    def get_name(self):
        return self.name

    @property
    def init(self):
        return self._init

    @init.setter
    def init(self, new_init):
        self._init = new_init

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, new_index):
        self._index = new_index

    @property
    def controller(self):
        return str(self.ctx.author.id)  # workaround

    def get_participants(self):
        return self._participants

    def add_participant(self, participant):
        self._participants.append(participant)
        participant.group = self.id
        participant.init = self.init

    def remove_participant(self, participant):
        self._participants.remove(participant)
        participant.group = None

    def get_summary(self, private=False, no_notes=False):
        """
        Gets a short summary of an participant's status.
        :return: A string describing the participant.
        """
        if len(self._participants) > 7 and not private:
            status = f"{self.init:>2}: {self.name} ({len(self.get_participants())} participants)"
        else:
            status = f"{self.init:>2}: {self.name}"
            for c in self.get_participants():
                status += f'\n     - {": ".join(c.get_summary(private, no_notes).split(": ")[1:])}'
        return status

    def get_status(self, private=False):
        """
        Gets the start-of-turn status of an participant.
        :param private: Whether to return the full revealed stats or not.
        :return: A string describing the participant.
        """
        return "\n".join(c.get_status(private) for c in self.get_participants())

    def on_turn(self, num_turns=1):
        for c in self.get_participants():
            c.on_turn(num_turns)

    def on_turn_end(self, num_turns=1):
        for c in self.get_participants():
            c.on_turn_end(num_turns)

    def on_remove(self):
        for c in self.get_participants():
            c.on_remove()

    def controller_mention(self):
        return ", ".join({c.controller_mention() for c in self.get_participants()})

    def __str__(self):
        return f"{self.name} ({len(self.get_participants())} participants)"

    def __contains__(self, item):
        return item in self._participants

    def __len__(self):
        return len(self._participants)
