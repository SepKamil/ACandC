import enum


class BaseParticipant:
    __slots__ = ()


class ParticipantType(enum.Enum):
    GENERIC = "common"
    PLAYER = "player"
    GROUP = "group"
