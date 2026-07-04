from datetime import date
from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import Dict, List, Optional, TypedDict


class TravelPlannerState(TypedDict):
    """Travel planner state with user input + extracted details."""

    messages: Annotated[List[BaseMessage], add_messages]
    last_user_message: str

    # --- Extracted user travel details ---
    destination: Optional[str]
    source: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    duration: Optional[int]
    flights: Optional[List]
    flight_type: Optional[str]
    accommodation_guests: Optional[int]
    accommodation_area_type: Optional[str]
    hotel_options: Optional[List]

    # --- Control flow / orchestration ---
    route: Optional[str]
    awaiting_field: Optional[str]
    missing_fields: Optional[List[str]]
    awaiting_confirmation: Optional[bool]

    # --- Flight node specific states ---
    awaiting_destination_city: Optional[bool]  # When destination is a country
    awaiting_airport_clarification: Optional[bool]  # When IATA conversion fails
    original_destination: Optional[str]  # Store original destination for context
    suggested_city: Optional[str]
    # --- Flight specific states ---
    available_flights: Optional[Dict]  # Flights stored as dict {1: flight1, 2: flight2, ...}
    selected_flight: Optional[Dict]  # User's selected flight
    selected_flight_number: Optional[str]  # Selected flight number
    flights_processed: Optional[bool]  # Whether flights have been processed

    # --- Hotel/Accommodation details ---
    accommodation_guests: Optional[int]
    accommodation_area_type: Optional[str]
    accommodation_budget: Optional[str]
    accommodation_type: Optional[str]
    available_hotels: Optional[Dict]  # Hotels stored as dict {1: hotel1, 2: hotel2, ...}
    selected_hotel: Optional[Dict]
    selected_hotel_number: Optional[str]
    hotels_processed: Optional[bool]  # Whether hotel search is done
