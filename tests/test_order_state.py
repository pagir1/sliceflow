import pytest
from core.order_state import State, Event, Role, next_state, TransitionError, FINAL_STATES


def test_happy_path_from_draft_to_completed():
    s = State.DRAFT
    s = next_state(s, Event.SEND_TO_KITCHEN, Role.CASHIER, item_count=2)
    assert s == State.SUBMITTED
    s = next_state(s, Event.START_COOKING, Role.KITCHEN)
    assert s == State.IN_OVEN
    s = next_state(s, Event.MARK_READY, Role.KITCHEN)
    assert s == State.READY
    s = next_state(s, Event.HAND_OVER, Role.CASHIER, is_paid=True)
    assert s == State.COMPLETED


def test_cashier_can_cancel_a_draft():
    assert next_state(State.DRAFT, Event.CANCEL, Role.CASHIER) == State.CANCELLED


def test_cannot_send_empty_order():
    with pytest.raises(TransitionError):
        next_state(State.DRAFT, Event.SEND_TO_KITCHEN, Role.CASHIER, item_count=0)


def test_cannot_hand_over_unpaid_order():
    # INV-5: an order is Completed only if it is paid
    with pytest.raises(TransitionError):
        next_state(State.READY, Event.HAND_OVER, Role.CASHIER, is_paid=False)


def test_only_manager_can_void():
    assert next_state(State.SUBMITTED, Event.VOID, Role.MANAGER) == State.CANCELLED
    with pytest.raises(TransitionError):
        next_state(State.SUBMITTED, Event.VOID, Role.CASHIER)


def test_manager_can_void_in_oven_and_ready():
    # CR-02
    assert next_state(State.IN_OVEN, Event.VOID, Role.MANAGER) == State.CANCELLED
    assert next_state(State.READY, Event.VOID, Role.MANAGER) == State.CANCELLED
    with pytest.raises(TransitionError):
        next_state(State.READY, Event.VOID, Role.KITCHEN)


def test_cannot_skip_steps():
    with pytest.raises(TransitionError):
        next_state(State.DRAFT, Event.MARK_READY, Role.KITCHEN)


@pytest.mark.parametrize("final_state", list(FINAL_STATES))
@pytest.mark.parametrize("event", list(Event))
@pytest.mark.parametrize("role", list(Role))
def test_final_states_never_change(final_state, event, role):
    # INV-6: Completed and Cancelled are final
    with pytest.raises(TransitionError):
        next_state(final_state, event, role, item_count=5, is_paid=True)