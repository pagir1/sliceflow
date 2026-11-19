from sqlmodel import Session

from kitchen import orders_in_state


def customer_board(session: Session) -> dict:
    """What the customer TV shows: only order numbers, never names or food."""
    preparing = [o.id for o in orders_in_state(session, "SUBMITTED")]
    preparing += [o.id for o in orders_in_state(session, "IN_OVEN")]
    ready = [o.id for o in orders_in_state(session, "READY")]
    return {"preparing": sorted(preparing), "ready": sorted(ready)}