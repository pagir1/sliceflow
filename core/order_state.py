from enum import Enum


class State(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_OVEN = "IN_OVEN"
    READY = "READY"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Event(str, Enum):
    SEND_TO_KITCHEN = "SEND_TO_KITCHEN"
    CANCEL = "CANCEL"
    START_COOKING = "START_COOKING"
    VOID = "VOID"
    MARK_READY = "MARK_READY"
    HAND_OVER = "HAND_OVER"


class Role(str, Enum):
    CASHIER = "CASHIER"
    KITCHEN = "KITCHEN"
    MANAGER = "MANAGER"


# The rule book: (current state, event) -> (next state, who is allowed)
TRANSITIONS = {
    (State.DRAFT, Event.SEND_TO_KITCHEN): (State.SUBMITTED, {Role.CASHIER}),
    (State.DRAFT, Event.CANCEL): (State.CANCELLED, {Role.CASHIER}),
    (State.SUBMITTED, Event.START_COOKING): (State.IN_OVEN, {Role.KITCHEN}),
    (State.SUBMITTED, Event.VOID): (State.CANCELLED, {Role.MANAGER}),
    (State.IN_OVEN, Event.MARK_READY): (State.READY, {Role.KITCHEN}),
    (State.IN_OVEN, Event.VOID): (State.CANCELLED, {Role.MANAGER}),     # CR-02
    (State.READY, Event.HAND_OVER): (State.COMPLETED, {Role.CASHIER}),
    (State.READY, Event.VOID): (State.CANCELLED, {Role.MANAGER}),
}

FINAL_STATES = {State.COMPLETED, State.CANCELLED}


class TransitionError(Exception):
    pass


def next_state(state: State, event: Event, role: Role,
               item_count: int = 0, is_paid: bool = False) -> State:
    key = (state, event)
    if key not in TRANSITIONS:
        raise TransitionError(f"Cannot do {event.value} when order is {state.value}")

    new_state, allowed_roles = TRANSITIONS[key]
    if role not in allowed_roles:
        raise TransitionError(f"{role.value} is not allowed to do {event.value}")

    # Guards (extra conditions)
    if event == Event.SEND_TO_KITCHEN and item_count < 1:
        raise TransitionError("Cannot send an empty order to the kitchen")
    if event == Event.HAND_OVER and not is_paid:
        raise TransitionError("Order must be paid before it is handed over")

    return new_state