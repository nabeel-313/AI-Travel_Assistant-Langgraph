"""Custom tools with circuit breaker and retry logic for production use."""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar

import aiohttp
from langchain.tools import StructuredTool

from src.exceptions import ExceptionError
from src.langgraph_core.schemas.all_schems import WeatherResponse, WindInfo
from src.loggers import Logger
from src.utils.Utilities import get_api_key

logger = Logger(__name__).get_logger()

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"         # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5          # Failures before opening circuit
    success_threshold: int = 2           # Successes in half-open to close
    timeout: float = 60.0               # Seconds before trying half-open
    half_open_max_calls: int = 3         # Max calls in half-open state


class CircuitBreaker:
    """Thread-safe circuit breaker implementation."""

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state (check timeout for half-open transition)."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time and \
               time.time() - self._last_failure_time >= self.config.timeout:
                return CircuitState.HALF_OPEN
        return self._state

    async def can_execute(self) -> bool:
        """Check if request can be executed."""
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.CLOSED:
                return True

            if current_state == CircuitState.OPEN:
                return False

            # HALF_OPEN: allow limited calls
            if self._half_open_calls < self.config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    async def record_success(self) -> None:
        """Record successful execution."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._reset()
            else:
                self._failure_count = 0

    async def record_failure(self) -> None:
        """Record failed execution."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._half_open_calls = 0
                self._success_count = 0
            elif self._failure_count >= self.config.failure_threshold:
                self._state = CircuitState.OPEN

    def _reset(self) -> None:
        """Reset circuit to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = None


class CircuitBreakerOpenError(Exception):
    """Raised when a circuit breaker is open and a call is rejected."""
    pass


@dataclass
class RetryConfig:
    """Configuration for retry logic."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    exponential_base: float = 2.0
    retry_on_timeout: bool = True


async def with_retry(
    func: Callable[..., T],
    config: RetryConfig = None,
    *args,
    **kwargs
) -> T:
    """Execute async function with retry logic and exponential backoff."""
    config = config or RetryConfig()
    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            result = await asyncio.wait_for(func(*args, **kwargs), timeout=30.0)
            return result
        except asyncio.TimeoutError as e:
            last_exception = e
            if not config.retry_on_timeout:
                raise
            logger.warning(
                "Timeout on attempt %d/%d for %s",
                attempt + 1, config.max_attempts, func.__name__
            )
        except (aiohttp.ClientError, ConnectionError) as e:
            last_exception = e
            logger.warning(
                "Request failed on attempt %d/%d: %s",
                attempt + 1, config.max_attempts, str(e)
            )
        except Exception as e:
            last_exception = e
            logger.error("Unexpected error in %s: %s", func.__name__, str(e))
            raise

        # Exponential backoff (skip on last attempt)
        if attempt < config.max_attempts - 1:
            delay = min(
                config.base_delay * (config.exponential_base ** attempt),
                config.max_delay
            )
            # Add jitter
            delay *= (0.5 + asyncio.get_event_loop().time() % 0.5)
            await asyncio.sleep(delay)

    raise last_exception


# Circuit breakers for each external service
_weather_circuit = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3, timeout=30))
_flight_circuit = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5, timeout=60))
_hotel_circuit = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5, timeout=60))


async def weather_information(city_name: str) -> WeatherResponse:
    """Generates a weather report for a given city with circuit breaker and retry."""
    if not await _weather_circuit.can_execute():
        logger.warning("Weather API circuit open, returning cached/default response")
        return {"city": city_name, "temp": None, "unit": "Celsius", "wind": {"speed": None, "direction": None}}

    base_url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city_name,
        "appid": get_api_key("OPENWEATHERMAP_API_KEY"),
        "units": "metric",
    }

    async def _fetch():
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                if response.status != 200:
                    text = await response.text()
                    raise ValueError(f"Error fetching weather: {text}")

                data = await response.json()
                return WeatherResponse(
                    city=data["name"],
                    temp=data["main"]["temp"],
                    unit="Celsius",
                    wind=WindInfo(speed=data["wind"]["speed"], direction=data["wind"]["deg"]),
                )

    try:
        result = await with_retry(_fetch, RetryConfig(max_attempts=3, base_delay=0.5))
        await _weather_circuit.record_success()
        return result.dict() if hasattr(result, 'dict') else result
    except Exception as e:
        await _weather_circuit.record_failure()
        logger.error(f"Error in weather_information: {e}")
        # Return graceful degradation response
        return {"city": city_name, "temp": None, "unit": "Celsius", "wind": {"speed": None, "direction": None}}


weather_tool = StructuredTool.from_function(
    func=weather_information,
    coroutine=weather_information,
    name="weather_infotmation",
    description="Fetches current weather info for a given city",
    return_direct=True,
)


async def search_flights(source: str, destination: str, start_date: str, end_date: str, flight_type: str = "cheapest") -> Dict[str, Any]:
    """
    Search flights using SerpAPI with circuit breaker and retry.
    """
    if not await _flight_circuit.can_execute():
        logger.warning("Flight API circuit open, returning empty results")
        return {"flights": [], "error": "Service temporarily unavailable"}

    api_key = get_api_key("SERPAPI_API_KEY")
    params = {
        "engine": "google_flights",
        "departure_id": source,
        "arrival_id": destination,
        "outbound_date": start_date,
        "return_date": end_date,
        "currency": "INR",
        "api_key": api_key,
    }

    async def _search():
        async with aiohttp.ClientSession() as session:
            async with session.get("https://serpapi.com/search", params=params) as response:
                response.raise_for_status()
                return await response.json()

    try:
        logger.info("Searching flights from %s to %s", source, destination)
        results = await with_retry(_search, RetryConfig(max_attempts=3, base_delay=1.0))
        await _flight_circuit.record_success()

        # Decide which list of flights to use
        if flight_type == "cheapest":
            flights = results.get("cheapest_flights", []) or results.get("best_flights", [])
        else:
            flights = results.get("best_flights", []) or results.get("other_flights", [])

        flight_options = []
        for flight in flights:
            segment = flight.get("flights", [{}])[0]

            dep_airport = segment.get("departure_airport", {})
            arr_airport = segment.get("arrival_airport", {})

            flight_options.append({
                "airline": segment.get("airline", flight.get("airline", "")),
                "price": flight.get("price", "N/A"),
                "departure_airport": (dep_airport.get("id") or dep_airport.get("name", "")),
                "departure_time": (dep_airport.get("time") or dep_airport.get("datetime", "")),
                "arrival_airport": (arr_airport.get("id") or arr_airport.get("name", "")),
                "arrival_time": (arr_airport.get("time") or arr_airport.get("datetime", "")),
                "duration": (segment.get("duration", flight.get("duration", ""))),
            })

        return {"flights": flight_options}

    except Exception as e:
        await _flight_circuit.record_failure()
        logger.error(f"Error fetching flights: {e}")
        return {"flights": [], "error": str(e)}


async def search_hotels(city: str, check_in: str, check_out: str, guests: int, hotel_type: str = "cheapest") -> Dict[str, Any]:
    """
    Search hotels using SerpAPI with circuit breaker and retry.
    """
    if not await _hotel_circuit.can_execute():
        logger.warning("Hotel API circuit open, returning empty results")
        return {"hotels": [], "error": "Service temporarily unavailable"}

    api_key = get_api_key("SERPAPI_API_KEY")
    params = {
        "engine": "google_hotels",
        "q": f"{city}",
        "check_in_date": check_in,
        "check_out_date": check_out,
        "adults": guests,
        "currency": "INR",
        "api_key": api_key,
    }

    async def _search():
        async with aiohttp.ClientSession() as session:
            async with session.get("https://serpapi.com/search", params=params) as response:
                response.raise_for_status()
                return await response.json()

    try:
        data = await with_retry(_search, RetryConfig(max_attempts=3, base_delay=1.0))
        await _hotel_circuit.record_success()

        # Extract properties list
        properties_list = data.get("properties", [])

        if hotel_type == "cheapest":
            properties_list.sort(key=lambda x: x.get("rate_per_night", {}).get("extracted_lowest", float("inf")))

        hotels = []
        for prop in properties_list:
            rate_info = prop.get("rate_per_night", {})
            total_rate = prop.get("total_rate", {})

            hotels.append({
                "name": prop.get("name"),
                "address": prop.get("gps_coordinates", {}),
                "price": rate_info.get("lowest", "N/A"),
                "rating": prop.get("overall_rating"),
                "reviews": prop.get("reviews"),
                "url": prop.get("link", ""),
                "type": prop.get("type"),
                "hotel_class": prop.get("hotel_class"),
                "total_rate": total_rate.get("lowest", "N/A")
            })

        return {"hotels": hotels}

    except Exception as e:
        await _hotel_circuit.record_failure()
        custom_err = ExceptionError(e)
        logger.error("Error fetching hotels: %s", custom_err)
        return {"hotels": [], "error": str(e)}
