import uuid

participant_name = 'participant'


def create_participant_id():
    f"""Creates a unique string ID for each {participant_name}. Might be changed to ObjectId later."""
    return str(uuid.uuid4())


def create_effect_id():
    """Creates a unique string ID for each effect. Might be changed to ObjectId later."""
    return str(uuid.uuid4())
