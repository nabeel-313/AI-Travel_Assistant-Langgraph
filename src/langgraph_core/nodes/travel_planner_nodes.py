import json
from datetime import datetime
from uuid import uuid4
import asyncio

from langchain_core.messages import AIMessage, HumanMessage

from src.langgraph_core.state.travel_planner_states import TravelPlannerState
from src.langgraph_core.tools.custom_tools import (
    search_flights,
    search_hotels,
    weather_tool,
)
from src.langgraph_core.tools.tools import get_tools
from src.loggers import Logger
from src.utils.Utilities import TravelInfo
from src.cache.redis_client import redis_client

logger = Logger(__name__).get_logger()


class TravelPlannerNode:
    def __init__(self, llm):
        self.llm = llm
        self.weather_tool_name = weather_tool.name
        self.search_tool_name = get_tools()[0].name

    async def router(self, state: TravelPlannerState) -> dict:
        logger.info("Router node is called")
        if not state.get("messages"):
            return {"route": "chat", "messages": [AIMessage(content="Hello! I'm your travel assistant. How can I help you today?")], "last_user_message": ""}

        available_flights = state.get("available_flights", {})
        if available_flights and not state.get("flights_processed", False):
            logger.info("Bypassing router - processing flight selection")
            return {"route": "flight_selection_node", "messages": state["messages"], "last_user_message": state.get("last_user_message", "")}

        available_hotels = state.get("available_hotels", {})
        if available_hotels and not state.get("hotels_processed", False):
            logger.info("Bypassing router - processing hotel selection")
            return {"route": "hotel_selection_node", "messages": state["messages"], "last_user_message": state.get("last_user_message", "")}

        if state.get("awaiting_field"):
            logger.info("Bypassing router - continuing travel info collection")
            return {"route": "collect_missing_travel_info_node", "messages": state["messages"], "last_user_message": state.get("last_user_message", "")}

        if state.get("awaiting_airport_clarification"):
            logger.info("Bypassing router - processing airport clarification")
            return {"route": "flight_search_node", "messages": state["messages"], "last_user_message": state.get("last_user_message", "")}  # Go back to flight node to process the response

        # If waiting for destination city clarification
        if state.get("awaiting_destination_city"):
            logger.info("Bypassing router - processing destination city clarification")
            return {"route": "flight_search_node", "messages": state["messages"], "last_user_message": state.get("last_user_message", "")}  # Go back to flight node to process the response

        # Check if we're waiting for travel confirmation
        if state.get("awaiting_confirmation"):
            logger.info("Processing travel confirmation")
            return {"route": "process_travel_confirmation", "messages": state["messages"], "last_user_message": state.get("last_user_message", "")}

        if state.get("destination") and (state.get("accommodation_guests") is None):
            logger.info("Bypassing router - collecting hotel preferences")
            return {"route": "collect_hotel_info_node", "messages": state["messages"], "last_user_message": state.get("last_user_message", "")}

        last_msg = state["messages"][-1]
        if not isinstance(last_msg, HumanMessage):
            return {"route": state.get("route", "chat"), "messages": state["messages"], "last_user_message": state.get("last_user_message", "")}

        user_input = last_msg.content
        state["last_user_message"] = user_input

        # Enhanced routing logic
        user_input_lower = user_input.lower()
        if any(word in user_input_lower for word in ["travel", "visit", "trip", "vacation", "holiday", "go to"]):
            route = "travel"
        elif any(word in user_input_lower for word in ["weather", "temperature", "forecast"]):
            route = "weather"
        elif any(word in user_input_lower for word in ["search", "find", "look for"]):
            route = "search"
        else:
            route = "chat"

        messages = state["messages"]

        # Tool call injection
        if route == "weather":
            city_prompt = f"Extract city from: '{user_input}' give only city name"
            city_response = await self.llm.ainvoke([HumanMessage(content=city_prompt)])
            city = city_response.content.strip()
            ai_msg = AIMessage(
                content="Let me check the weather for you...",
                tool_calls=[{"id": str(uuid4()), "name": self.weather_tool_name, "args": {"city_name": city}}],
            )
            messages = messages + [ai_msg]
        elif route == "search":
            query_prompt = f"Extract search query from: '{user_input}'"
            query_response = await self.llm.ainvoke([HumanMessage(content=query_prompt)])
            query = query_response.content.strip() or user_input
            ai_msg = AIMessage(
                content=f"Searching for {query}...",
                tool_calls=[{"id": str(uuid4()), "name": self.search_tool_name, "args": {"query": query}}],
            )
            messages = messages + [ai_msg]

        logger.info(f"Router classified intent as: {route}")
        return {"route": route, "messages": messages, "last_user_message": user_input}

    async def chat_node(self, state: TravelPlannerState):
        logger.info("Chat_node is called")
        if not state["messages"]:
            return {"messages": [AIMessage(content="Hello! How can I help you?")]}

        last_msg = state["messages"][-1]
        if not isinstance(last_msg, HumanMessage):
            return {"messages": state["messages"]}

        response = await self.llm.ainvoke([last_msg])
        return {"messages": state["messages"] + [response]}

    async def travel_node(self, state: TravelPlannerState):
        logger.info("Travel node is called")
        extractor = TravelInfo()
        logger.info("Extracting the info from user msg ...")

        # Extract from the LAST human message
        user_input = state["last_user_message"]
        info = extractor.extract_trip_info(user_input)

        # Update state with extracted info
        state.update({"destination": info.get("destination"), "start_date": info.get("start_date"), "end_date": info.get("end_date"), "duration": info.get("duration"), "source": info.get("source")})

        # Build confirmation message
        parts = ["Got it! Planning trip"]
        if state["destination"]:
            parts.append(f"to {state['destination']}")
        if state["duration"]:
            parts.append(f"for {state['duration']} days")
        if state["start_date"] and state["end_date"]:
            parts.append(f"from {state['start_date']} to {state['end_date']}")

        msg_text = " ".join(parts) + "."

        # Determine missing fields
        missing_fields = []
        if not state.get("source"):
            missing_fields.append("source")
        if not state.get("start_date"):
            missing_fields.append("start_date")
        if not state.get("end_date"):
            missing_fields.append("end_date")

        # Add ONLY the confirmation message now
        state["messages"].append(AIMessage(content=msg_text))
        logger.info(f"Travel node: Added message: {msg_text}")

        if missing_fields:
            state["missing_fields"] = missing_fields
            state["awaiting_field"] = missing_fields[0]
            # DON'T ask the question here - let collect_missing_travel_info_node handle it
            state["route"] = "collect_missing_travel_info_node"
        else:
            state["route"] = "flight_search_node"

        logger.info(f"Travel node: route set to collect_missing_travel_info_node, missing_fields: {missing_fields}")
        return {"messages": state["messages"], "destination": state.get("destination"), "source": state.get("source"), "start_date": state.get("start_date"), "end_date": state.get("end_date"), "duration": state.get("duration"), "route": state["route"], "awaiting_field": state.get("awaiting_field"), "missing_fields": state.get("missing_fields")}

    async def collect_missing_travel_info(self, state: TravelPlannerState):
        logger.info("Collect missing travel info node is called")

        current_field = state.get("awaiting_field")
        last_msg = state["messages"][-1] if state["messages"] else None

        # Check if we have a human response to process
        has_human_response = last_msg and isinstance(last_msg, HumanMessage)

        if has_human_response:
            # Process the user's response
            user_input = last_msg.content

            # Store the user's response
            if current_field == "source":
                state["source"] = user_input
                logger.info(f"User provided source: {user_input}")
            elif current_field == "start_date":
                state["start_date"] = user_input
                logger.info(f"User provided start_date: {user_input}")
            elif current_field == "end_date":
                state["end_date"] = user_input
                logger.info(f"User provided end_date: {user_input}")

            # Update missing fields
            missing_fields = state.get("missing_fields", [])
            if current_field in missing_fields:
                missing_fields.remove(current_field)
            state["missing_fields"] = missing_fields

            # Check if we have more fields to collect
            if missing_fields:
                state["awaiting_field"] = missing_fields[0]
                next_field = missing_fields[0]

                # Ask the next question
                if next_field == "source":
                    question = "What is your departure city?"
                elif next_field == "start_date":
                    question = "When would you like to start your trip? (e.g., 2024-12-25)"
                elif next_field == "end_date":
                    question = "When does your trip end? (e.g., 2024-12-31)"

                state["messages"].append(AIMessage(content=question))
                state["route"] = "END"  # End graph after asking question
                logger.info(f"Asked next question: {question}")
            else:
                # All fields collected - show summary and proceed to flights
                state["awaiting_field"] = None

                # Calculate duration
                duration = self._calculate_duration(state.get("start_date"), state.get("end_date"))
                state["duration"] = duration

                # Build summary message
                summary_parts = ["Perfect! Here's your trip summary:"]
                summary_parts.append(f"• Destination: {state.get('destination')}")
                summary_parts.append(f"• Departure from: {state.get('source')}")
                summary_parts.append(f"• Travel dates: {state.get('start_date')} to {state.get('end_date')}")
                summary_parts.append(f"• Duration: {duration} days")

                summary_msg = "\n".join(summary_parts)
                state["messages"].append(AIMessage(content=summary_msg))
                logger.info(f"Displayed trip summary: {summary_msg}")

                # Add searching message
                state["messages"].append(AIMessage(content="Should I proceed with searching for flights and hotels? (yes/no)"))
                state["route"] = "END"
                state["awaiting_confirmation"] = True  # ← Track that we're waiting for confirmation
                logger.info("Displayed trip summary, waiting for user confirmation")

        else:
            # No human response - check if we need to ask first question
            last_ai_msg = None
            for msg in reversed(state["messages"]):
                if isinstance(msg, AIMessage):
                    last_ai_msg = msg
                    break

            # If we haven't asked the first question yet, ask it
            if current_field and (not last_ai_msg or "departure city" not in last_ai_msg.content):
                if current_field == "source":
                    question = "What is your departure city?"
                elif current_field == "start_date":
                    question = "When would you like to start your trip? (e.g., 2024-12-25)"
                elif current_field == "end_date":
                    question = "When does your trip end? (e.g., 2024-12-31)"

                state["messages"].append(AIMessage(content=question))
                state["route"] = "END"  # End graph after asking question
                logger.info(f"Asked missing info question: {question}")
            else:
                # We already asked a question - end execution and wait for user
                state["route"] = "END"  # End the graph execution
                logger.info("Waiting for user response - ending graph")

        return {"messages": state["messages"], "source": state.get("source"), "start_date": state.get("start_date"), "end_date": state.get("end_date"), "duration": state.get("duration"), "route": state["route"], "awaiting_field": state.get("awaiting_field"), "missing_fields": state.get("missing_fields"), "awaiting_confirmation": state.get("awaiting_confirmation")}

    def _calculate_duration(self, start_date: str, end_date: str) -> int:
        """Calculate duration between two dates in days."""
        try:
            if not start_date or not end_date:
                return 0

            # Parse dates (assuming format YYYY-MM-DD)
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")

            # Calculate difference in days
            duration = (end - start).days
            return max(0, duration)  # Ensure non-negative
        except Exception as e:
            logger.error(f"Error calculating duration:{e}")
            return 0

    async def process_travel_confirmation(self, state: TravelPlannerState):
        logger.info("Process travel confirmation node is called")

        last_msg = state["messages"][-1] if state["messages"] else None

        if isinstance(last_msg, HumanMessage):
            user_input = last_msg.content.lower()

            if user_input in ["yes", "y", "ok", "proceed", "continue", "sure"]:
                # User confirmed - proceed to flights
                # User confirmed - show travel summary first
                summary_parts = ["** Travel Confirmed! Here's your trip:**"]
                summary_parts.append(f"• **Destination:** {state.get('destination')}")
                summary_parts.append(f"• **Departure from:** {state.get('source')}")
                summary_parts.append(f"• **Travel dates:** {state.get('start_date')} to {state.get('end_date')}")
                summary_parts.append(f"• **Duration:** {state.get('duration')} days")
                summary_parts.append("")
                summary_parts.append("Now searching for flights...")

                summary_msg = "\n".join(summary_parts)
                state["messages"].append(AIMessage(content=summary_msg))

                # Then proceed to flight search
                state["awaiting_confirmation"] = False
                state["route"] = "flight_search_node"
                logger.info("User confirmed travel, proceeding to flight search")

            else:
                # User declined or said something else
                state["awaiting_confirmation"] = False
                state["route"] = "chat_node"
                state["messages"].append(AIMessage(content="Okay, let me know if you'd like to make any changes to your trip details."))

        return state

    async def flight_search_node(self, state: TravelPlannerState):
        logger.info("Flight search node is called")

        source = state.get("source")
        destination = state.get("destination")
        start_date = state.get("start_date")
        end_date = state.get("end_date")
        # Validate we have all required information
        if not all([source, destination, start_date, end_date]):
            missing_fields = []
            if not source:
                missing_fields.append("source")
            if not start_date:
                missing_fields.append("start_date")
            if not end_date:
                missing_fields.append("end_date")

            state["missing_fields"] = missing_fields
            state["awaiting_field"] = missing_fields[0]
            state["route"] = "collect_missing_travel_info_node"
            state["messages"].append(AIMessage(content="I'm missing some information to search for flights."))
            return state

        # Step 1: Check if we're processing a destination city response
        if state.get("awaiting_destination_city"):
            last_msg = state["messages"][-1] if state["messages"] else None
            if isinstance(last_msg, HumanMessage):
                user_input = last_msg.content.strip()

                # If user provides a specific city, use it
                if user_input.lower() not in ["yes", "y", "ok", "use it"]:
                    # User specified a different city (like "Muscat")
                    destination = user_input
                    state["destination"] = destination
                    logger.info(f"User specified city: {destination}")
                else:
                    # User accepted the suggestion
                    destination = state.get("suggested_city", destination)
                    state["destination"] = destination
                    logger.info(f"User accepted suggested city: {destination}")

                state["awaiting_destination_city"] = False
                # Clear the processed flag to re-check the new destination
                state["destination_city_processed"] = False
            else:
                # Still waiting for response, end graph
                state["route"] = "END"
                return state

        # Step 2: Check if destination is a country name (only if not already processed)
        if not state.get("awaiting_destination_city") and not state.get("destination_city_processed"):
            destination_check_prompt = f"""
            Is "{destination}" a country name or city name?
            Respond with ONLY one word: "country" or "city"
            """

            try:
                dest_resp = await self.llm.ainvoke([HumanMessage(content=destination_check_prompt)])
                dest_type = dest_resp.content.strip().lower()

                if "country" in dest_type:
                    # It's a country, ask for city
                    city_suggestion_prompt = f"""
                    What is the main city or capital of {destination} for flight searches?
                    Respond with ONLY the city name.
                    """
                    city_resp = await self.llm.ainvoke([HumanMessage(content=city_suggestion_prompt)])
                    suggested_city = city_resp.content.strip()

                    state["messages"].append(AIMessage(content=f"I see you mentioned {destination} which is a country. For flight search, I need a specific city. Should I use {suggested_city} or would you like to specify a different city in {destination}?"))
                    state["awaiting_destination_city"] = True
                    state["original_destination"] = destination
                    state["suggested_city"] = suggested_city
                    state["route"] = "END"
                    return state

            except Exception as e:
                logger.error(f"Error analyzing destination: {e}")
                # Continue with original destination, mark as processed
                state["destination_city_processed"] = True

        # Step 3: Convert to IATA codes
        IATA_prompt = f"""
        Convert these locations to IATA airport codes. If no direct IATA code exists, provide the nearest major airport city.
        Source: "{source}"
        Destination: "{destination}"

        Respond with strict JSON format:
        {{
            "source_iata": "CODE_OR_NEAREST_CITY",
            "destination_iata": "CODE_OR_NEAREST_CITY",
            "source_type": "city|airport|nearest_city",
            "destination_type": "city|airport|nearest_city",
            "notes": "any_issues_found"
        }}
        """

        try:
            resp = await self.llm.ainvoke([HumanMessage(content=IATA_prompt)])
            raw_text = resp.content.strip()
            iata_data = json.loads(raw_text)

            source_iata = iata_data.get("source_iata")
            destination_iata = iata_data.get("destination_iata")

            logger.info(f"IATA Conversion - Source: {source}→{source_iata}, Destination: {destination}→{destination_iata}")

        except Exception as e:
            logger.error(f"Error converting to IATA codes: {e}")
            # Use city names as fallback
            source_iata = source
            destination_iata = destination

        # Step 4: Final fallback - use city names if IATA failed
        if not source_iata:
            source_iata = source
        if not destination_iata:
            destination_iata = destination

        # Step 5: Search for flights
        try:
            logger.info(f"Searching flights from {source_iata} to {destination_iata}")
            flight_key = f"{source.lower()}-{destination.lower()}-{start_date}-{end_date}"
            # print("::::", flight_key)
            flight_expire = 10800
            cached_flight = await redis_client.get(flight_key)
            # print("???", cached_flight)
            if cached_flight:
                logger.info(f"cache found for {flight_key}")
                flights_dict = json.loads(cached_flight)
            else:
                logger.info(f" no cache found for {flight_key}")
                flights_data = await search_flights(
                    source_iata, destination_iata, start_date, end_date, state.get("flight_type", "cheapest"))

                flights_list = flights_data.get("flights", [])

                # Store flights in dictionary format with sequence numbers as keys
                flights_dict = {}
                for i, flight in enumerate(flights_list, 1):
                    flights_dict[str(i)] = flight

                cached_flight = await redis_client.set_json(flight_key, flights_dict, flight_expire)
                logger.info(f"flight details cached: {flight_key}")

            state["available_flights"] = flights_dict  # Store as dict with sequence numbers
            state["flights_processed"] = False  # Flag to track if flights have been processed

            if flights_dict:
                # Build flight selection message
                flights_msg = f"** Found {len(flights_dict)} flights from {source} to {destination}:**\n\n"

                for flight_no, flight in flights_dict.items():
                    airline = flight.get("airline", "Unknown Airline")
                    price = flight.get("price", "Price not available")
                    departure_time = flight.get("departure_time", "Time not available")
                    arrival_time = flight.get("arrival_time", "Time not available")

                    flights_msg += f"**{flight_no}. {airline}**\n"
                    flights_msg += f"    Price: {price}\n"
                    flights_msg += f"    Departure: {departure_time}\n"
                    flights_msg += f"    Arrival: {arrival_time}\n"

                    # Add duration if available
                    duration = flight.get("duration")
                    if duration and duration != "Duration not available":
                        flights_msg += f"   ⏱ Duration: {duration}\n"

                    flights_msg += "\n"

                flights_msg += "**Please select a flight by entering the number (1, 2, 3, etc.):**"

                state["messages"].append(AIMessage(content=flights_msg))
                logger.info(f"Displayed {len(flights_dict)} flight options to user")

                # Set route to flight selection node
                state["route"] = "flight_selection_node"

            else:
                # No flights found
                no_flights_msg = f"No flights found from {source} to {destination} for your travel dates.\n\n"
                no_flights_msg += "Let me try searching for hotels instead."

                state["messages"].append(AIMessage(content=no_flights_msg))
                state["route"] = "hotel_search_node"
                logger.info("No flights found, proceeding to hotel search")

        except Exception as e:
            logger.error(f"Error searching flights: {e}")
            error_msg = f"I encountered an error while searching for flights from {source} to {destination}.\n\n"
            error_msg += "Let me try searching for hotels instead."

            state["messages"].append(AIMessage(content=error_msg))
            state["route"] = "hotel_search_node"

        return state

    async def flight_selection_node(self, state: TravelPlannerState):
        logger.info("Flight selection node is called")

        last_msg = state["messages"][-1] if state["messages"] else None

        if isinstance(last_msg, HumanMessage):
            user_input = last_msg.content.strip()
            available_flights = state.get("available_flights", {})

            # Check if user selected a valid flight number
            if user_input in available_flights:
                selected_flight = available_flights[user_input]
                state["selected_flight"] = selected_flight
                state["selected_flight_number"] = user_input
                state["flights_processed"] = True

                # CRITICAL: Clear accommodation_guests to prevent carry-over
                state["accommodation_guests"] = None

                # Build confirmation message
                airline = selected_flight.get("airline", "Unknown Airline")
                price = selected_flight.get("price", "Price not available")

                confirmation_msg = f"**Flight {user_input} selected!**\n\n"
                confirmation_msg += f"**{airline}** - {price}\n\n"
                confirmation_msg += "Now proceeding to hotel search..."

                state["messages"].append(AIMessage(content=confirmation_msg))
                state["route"] = "hotel_search_node"
                logger.info(f"User selected flight {user_input}: {airline}")

            else:
                # Invalid selection
                error_msg = f"Invalid selection: '{user_input}'. Please enter a valid flight number (1, 2, 3, etc.) from the list above."
                state["messages"].append(AIMessage(content=error_msg))
                state["route"] = "flight_selection_node"
                logger.info(f"User entered invalid flight selection: {user_input}")

        else:
            # No user response yet, wait
            state["route"] = "END"

        return state

    async def hotel_search_node(self, state: TravelPlannerState):
        logger.info("Hotel search node is called")

        destination = state.get("destination")
        start_date = state.get("start_date")
        end_date = state.get("end_date")

        if not destination:
            state["messages"].append(AIMessage(content="I need to know your destination to search for hotels."))
            state["route"] = "END"
            return state

        # Check if we need to collect hotel preferences
        if state.get("accommodation_guests") is None:
            state["messages"].append(AIMessage(content="How many guests will be staying?"))
            state["route"] = "collect_hotel_info_node"
            return state

        try:
            hotel_key = f"{destination.lower()}-{start_date}-{end_date}"
            hotel_expire = 10800
            cached_hotel = await redis_client.get(hotel_key)
            if cached_hotel:
                logger.info(f"cache found for {hotel_key}")
                hotels_dict = json.loads(cached_hotel)
            else:
                logger.info(f" no cache found for {hotel_key}")
                hotel_results = await search_hotels(
                    city=destination, check_in=start_date, check_out=end_date, guests=state["accommodation_guests"])
                hotel_options = hotel_results.get("hotels", [])
                # print(len(hotel_options))
                # Store hotels in dictionary format with sequence numbers as keys
                hotels_dict = {}
                for i, hotel in enumerate(hotel_options, 1):
                    hotels_dict[str(i)] = hotel
                await redis_client.set_json(hotel_key, hotels_dict, hotel_expire)
                logger.info(f"hotel details cached: {hotel_key}")

            state["available_hotels"] = hotels_dict  # Store as dict with sequence numbers
            state["hotels_processed"] = False  # Flag to track if hotels have been processed

            if hotels_dict:
                # Build hotel selection message
                hotels_msg = f"** Found {len(hotels_dict)} hotels in {destination}:**\n\n"

                for hotel_no, hotel in hotels_dict.items():
                    name = hotel.get("name", "Unknown Hotel")
                    price = hotel.get("price", "Price not available")
                    rating = hotel.get("rating", "Rating not available")
                    location = hotel.get("location", "Location not available")

                    hotels_msg += f"**{hotel_no}. {name}**\n"
                    hotels_msg += f"   Price: {price} per night\n"
                    if rating and rating != "Rating not available":
                        hotels_msg += f"   Rating: {rating}/5\n"
                    if location and location != "Location not available":
                        hotels_msg += f"   Location: {location}\n"

                    # Add amenities if available
                    amenities = hotel.get("amenities")
                    if amenities:
                        hotels_msg += f"    Amenities: {', '.join(amenities[:3])}\n"

                    hotels_msg += "\n"

                hotels_msg += "**Please select a hotel by entering the number (1, 2, 3, etc.):**"

                state["messages"].append(AIMessage(content=hotels_msg))
                logger.info(f"Displayed {len(hotels_dict)} hotel options to user")

                # Set route to hotel selection node
                state["route"] = "hotel_selection_node"

            else:
                # No hotels found
                no_hotels_msg = f" No hotels found in {destination} for your criteria.\n\n"
                no_hotels_msg += "You can try adjusting your search preferences."

                state["messages"].append(AIMessage(content=no_hotels_msg))
                state["route"] = "END"
                logger.info("No hotels found, ending search")

        except Exception as e:
            logger.error(f"Error searching hotels: {e}")
            error_msg = f" I encountered an error while searching for hotels in {destination}.\n\n"
            error_msg += "Please try again later or adjust your search criteria."

            state["messages"].append(AIMessage(content=error_msg))
            state["route"] = "END"

        return state

    async def hotel_selection_node(self, state: TravelPlannerState):
        logger.info("Hotel selection node is called")

        last_msg = state["messages"][-1] if state["messages"] else None

        if isinstance(last_msg, HumanMessage):
            user_input = last_msg.content.strip()
            available_hotels = state.get("available_hotels", {})

            # Check if user selected a valid hotel number
            if user_input in available_hotels:
                selected_hotel = available_hotels[user_input]
                state["selected_hotel"] = selected_hotel
                state["selected_hotel_number"] = user_input
                state["hotels_processed"] = True

                # Build confirmation message
                name = selected_hotel.get("name", "Unknown Hotel")
                price = selected_hotel.get("price", "Price not available")
                rating = selected_hotel.get("rating", "")

                confirmation_msg = f" **Hotel {user_input} selected!**\n\n"
                confirmation_msg += f"**{name}**\n"
                confirmation_msg += f" Price: {price} per night\n"
                if rating:
                    confirmation_msg += f" Rating: {rating}/5\n"

                confirmation_msg += f"\n **Your trip to {state.get('destination')} is all set!**\n\n"
                confirmation_msg += "**Trip Summary:**\n"
                confirmation_msg += f"•  Flight: {state.get('selected_flight', {}).get('airline', 'Selected flight')}\n"
                confirmation_msg += f"•  Hotel: {name}\n"
                confirmation_msg += f"•  Dates: {state.get('start_date')} to {state.get('end_date')}\n"
                confirmation_msg += f"•  Guests: {state.get('accommodation_guests')}\n"
                confirmation_msg += f"•  Area: {state.get('accommodation_area_type')}\n\n"
                confirmation_msg += " **Your travel planning is complete! Have a wonderful trip!**"

                state["messages"].append(AIMessage(content=confirmation_msg))
                state["route"] = "generate_itinerary_node"
                logger.info(f"User selected hotel {user_input}, routing to itinerary generation")

            else:
                # Invalid selection
                error_msg = f" Invalid selection: '{user_input}'. Please enter a valid hotel number (1, 2, 3, etc.) from the list above."
                state["messages"].append(AIMessage(content=error_msg))
                state["route"] = "hotel_selection_node"
                logger.info(f"User entered invalid hotel selection: {user_input}")

        else:
            # No user response yet, wait
            state["route"] = "END"

        return state

    async def collect_hotel_info_node(self, state: TravelPlannerState):
        """Collect missing hotel information"""
        logger.info("Collect hotel info node is called")

        # DEBUG: Check if we're carrying over flight selection
        selected_flight_num = state.get("selected_flight_number")
        current_guests = state.get("accommodation_guests")

        # If accommodation_guests equals the selected flight number, it's a carry-over error
        if selected_flight_num and current_guests and str(current_guests) == selected_flight_num:
            logger.info(f"Detected carry-over: guests={current_guests}, flight={selected_flight_num}")
            state["accommodation_guests"] = None  # Clear the invalid value

        last_msg = state["messages"][-1] if state["messages"] else None

        if isinstance(last_msg, HumanMessage):
            user_input = last_msg.content.strip()

            if state.get("accommodation_guests") is None:
                try:
                    state["accommodation_guests"] = int(user_input)
                    state["route"] = "hotel_search_node"
                    state["messages"].append(AIMessage(content="Great! Now searching for hotels..."))
                    logger.info(f"User provided guests: {user_input}, routing to hotel_search_node")
                    return state
                except ValueError:
                    state["messages"].append(AIMessage(content="Please enter a valid number for guests (e.g., 2)."))
                    state["route"] = "collect_hotel_info_node"
                    return state

        else:
            # No response yet - ask for guests
            if state.get("accommodation_guests") is None:
                state["messages"].append(AIMessage(content="How many guests will be staying?"))
                state["route"] = "END"
            else:
                # Shouldn't get here if guests already set
                state["route"] = "hotel_search_node"

        return state

    async def generate_itinerary_node(self, state: TravelPlannerState):
        """Generate travel itinerary based on selected hotel and flight"""
        logger.info("Generate itinerary node is called")

        destination = state.get("destination")
        start_date = state.get("start_date")
        end_date = state.get("end_date")
        duration = state.get("duration")
        selected_hotel = state.get("selected_hotel")

        if not all([destination, start_date, end_date, duration, selected_hotel]):
            missing = []
            if not destination:
                missing.append("destination")
            if not start_date:
                missing.append("start_date")
            if not end_date:
                missing.append("end_date")
            if not duration:
                missing.append("duration")
            if not selected_hotel:
                missing.append("selected_hotel")

            logger.error(f"Missing required fields for itinerary: {missing}")
            state["messages"].append(AIMessage(content="I need complete trip details to generate your itinerary. Let's start over."))
            state["route"] = "END"
            return state

        try:
            # Generate itinerary using LLM
            itinerary_prompt = f"""
            Create a detailed {duration}-day travel itinerary for {destination}.

            Travel Details:
            - Destination: {destination}
            - Dates: {start_date} to {end_date} ({duration} days)
            - Hotel: {selected_hotel.get('name', 'Selected hotel')}

            Please provide a comprehensive daily itinerary including:
            1. Morning activities
            2. Afternoon activities
            3. Evening activities
            4. Dining recommendations
            5. Transportation tips
            6. Cultural highlights

            Make it practical and enjoyable for a {duration}-day trip.
            Format it clearly with daily sections.
            """

            itinerary_response = await self.llm.ainvoke([HumanMessage(content=itinerary_prompt)])
            itinerary_content = itinerary_response.content

            # Format the final message with trip summary + itinerary
            final_message = f"""🎉 **Your Travel Planning is Complete!**

    ** Trip Summary:**
    • Destination: {destination}
    • Dates: {start_date} to {end_date} ({duration} days)
    • Hotel: {selected_hotel.get('name', 'Selected hotel')}
    • Guests: {state.get('accommodation_guests', 1)}

    ** Selected Hotel:**
    • Name: {selected_hotel.get('name', 'N/A')}
    • Price: {selected_hotel.get('price', 'N/A')}
    • Rating: {selected_hotel.get('rating', 'N/A')}

    ** Your {duration}-Day Itinerary for {destination}:**

    {itinerary_content}

    ** Pro Tip:** Save this itinerary and have a wonderful trip! """

            state["messages"].append(AIMessage(content=final_message))
            state["itinerary_generated"] = True
            state["route"] = "END"
            logger.info(f"Successfully generated {duration}-day itinerary for {destination}")

        except Exception as e:
            logger.error(f"Error generating itinerary: {e}")
            state["messages"].append(AIMessage(content=f" Your booking is confirmed! I encountered an issue generating the detailed itinerary, but your hotel and flight are booked.\n\n" f"**Trip Summary:**\n" f"• Destination: {destination}\n" f"• Dates: {start_date} to {end_date}\n" f"• Hotel: {selected_hotel.get('name', 'Selected hotel')}\n\n" f"Have a wonderful trip! 🎉"))
            state["route"] = "END"

        return state
