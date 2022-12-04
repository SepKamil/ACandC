from cogs5e.models.errors import AvraeException

__all__ = (
    "OEventException",
    "OEventNotFound",
    "RequiresContext",
    "ChannelInUse",
    "OEventChannelNotFound",
    "NoParticipants",
)
participant_name = 'participant'
participant_name_plural = 'participants'
ongoing_event_name = 'ongoing event'
ongoing_event_name_capital = 'Ongoing event'
article = 'an'


class OEventException(AvraeException):
    f"""A base exception for {ongoing_event_name}-related exceptions to stem from."""

    pass


class OEventNotFound(OEventException):
    f"""Raised when a channel is not in {ongoing_event_name}."""

    def __init__(self):
        super().__init__(f"This channel is not in {ongoing_event_name}.")


class RequiresContext(OEventException):
    f"""Raised when {article} {ongoing_event_name} is committed without context."""

    def __init__(self, msg=None):
        super().__init__(msg or f"{ongoing_event_name_capital} not contextualized.")


class ChannelInUse(OEventException):
    f"""Raised when {article} {ongoing_event_name} is started with an already active {ongoing_event_name}."""

    def __init__(self):
        super().__init__(f"Channel already in {ongoing_event_name}.")


class OEventChannelNotFound(OEventException):
    f"""Raised when {article} {ongoing_event_name}'s channel is not in the channel list."""

    def __init__(self):
        super().__init__(f"{ongoing_event_name_capital} channel does not exist.")


class NoParticipants(OEventException):
    f"""Raised when a {ongoing_event_name} tries to advance time with no {participant_name_plural}."""

    def __init__(self):
        super().__init__(f"There are no {participant_name_plural}.")
