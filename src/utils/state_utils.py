"""Helpers for serializing LangGraph travel-planner state to Redis."""

from typing import Any, Dict, List

# Workflow fields persisted across HTTP requests (messages are rebuilt each turn).
PERSISTED_STATE_KEYS: List[str] = [
    "route",
    "last_user_message",
    "destination",
    "source",
    "start_date",
    "end_date",
    "duration",
    "flight_type",
    "missing_fields",
    "awaiting_field",
    "awaiting_confirmation",
    "prompt_sent_for_field",
    "awaiting_destination_city",
    "awaiting_airport_clarification",
    "destination_city_processed",
    "original_destination",
    "suggested_city",
    "available_flights",
    "selected_flight",
    "selected_flight_number",
    "flights_processed",
    "accommodation_guests",
    "accommodation_area_type",
    "accommodation_budget",
    "accommodation_type",
    "available_hotels",
    "selected_hotel",
    "selected_hotel_number",
    "hotels_processed",
    "itinerary_generated",
]


def extract_persisted_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return only JSON-serializable workflow fields from graph state."""
    return {key: state[key] for key in PERSISTED_STATE_KEYS if key in state and state[key] is not None}


def merge_persisted_state(persisted: Dict[str, Any], user_message: str) -> Dict[str, Any]:
    """Build runtime state for a new graph turn from persisted Redis data."""
    from langchain_core.messages import HumanMessage

    runtime_state = {key: persisted[key] for key in PERSISTED_STATE_KEYS if key in persisted}
    runtime_state["messages"] = [HumanMessage(content=user_message)]
    return runtime_state
