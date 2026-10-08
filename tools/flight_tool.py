import os
import re
from typing import Optional

import requests
import certifi
import airportsdata
import pycountry

from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

API_KEY = os.getenv("AVIATIONSTACK_API_KEY")

DEFAULT_ORIGIN_IATA = os.getenv(
    "DEFAULT_ORIGIN_IATA",
    "IND"
)

BASE_URL = "http://api.aviationstack.com/v1/flights"


# ============================================================
# AIRPORT DATA
# ============================================================

AIRPORTS = airportsdata.load("IATA")


# ============================================================
# COUNTRY ALIASES
# ============================================================

COUNTRY_ALIASES = {
    "usa": "US",
    "us": "US",
    "america": "US",

    "uk": "GB",
    "britain": "GB",
    "england": "GB",

    "uae": "AE",
    "emirates": "AE",

    "ksa": "SA",
    "saudi": "SA",

    "bharat": "IN",
    "hindustan": "IN",

    "turkey": "TR",
    "turkiye": "TR",

    "holland": "NL",

    "south korea": "KR",
    "korea": "KR",

    "russia": "RU",
    "prc": "CN",

    "japan": "JP",
    "nippon": "JP",

    "germany": "DE",
    "deutschland": "DE",

    "france": "FR",
    "italy": "IT",
    "spain": "ES",

    "singapore": "SG",
    "malaysia": "MY",
    "thailand": "TH",
    "indonesia": "ID",

    "nepal": "NP",
    "bangladesh": "BD",
    "pakistan": "PK",
    "sri lanka": "LK",

    "qatar": "QA",
    "canada": "CA",
    "australia": "AU",
    "new zealand": "NZ",

    "brazil": "BR",
    "mexico": "MX",
    "south africa": "ZA",
}


# ============================================================
# COUNTRY -> MAIN AIRPORT
# ============================================================

COUNTRY_MAIN_AIRPORT = {
    "IN": "DEL",
    "US": "JFK",
    "GB": "LHR",
    "AE": "DXB",
    "SA": "RUH",
    "QA": "DOH",
    "SG": "SIN",
    "JP": "NRT",
    "CN": "PEK",
    "KR": "ICN",
    "TH": "BKK",
    "MY": "KUL",
    "ID": "CGK",
    "NP": "KTM",
    "BD": "DAC",
    "LK": "CMB",
    "PK": "LHE",
    "AU": "SYD",
    "NZ": "AKL",
    "CA": "YYZ",
    "FR": "CDG",
    "DE": "FRA",
    "IT": "FCO",
    "ES": "MAD",
    "NL": "AMS",
    "CH": "ZRH",
    "TR": "IST",
    "RU": "SVO",
    "BR": "GRU",
    "MX": "MEX",
    "ZA": "JNB",
}


# ============================================================
# CITY -> MAIN AIRPORT
# ============================================================

CITY_MAIN_AIRPORT = {

    # India
    "delhi": "DEL",
    "new delhi": "DEL",
    "mumbai": "BOM",
    "bombay": "BOM",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "hyderabad": "HYD",
    "chennai": "MAA",
    "madras": "MAA",
    "kolkata": "CCU",
    "calcutta": "CCU",
    "pune": "PNQ",
    "ahmedabad": "AMD",
    "goa": "GOI",
    "jaipur": "JAI",
    "lucknow": "LKO",
    "kochi": "COK",
    "cochin": "COK",
    "chandigarh": "IXC",
    "patna": "PAT",
    "varanasi": "VNS",

    # USA
    "new york": "JFK",
    "los angeles": "LAX",
    "san francisco": "SFO",
    "chicago": "ORD",
    "boston": "BOS",
    "washington": "DCA",
    "miami": "MIA",
    "seattle": "SEA",
    "dallas": "DFW",
    "houston": "IAH",
    "atlanta": "ATL",
    "las vegas": "LAS",

    # UK
    "london": "LHR",
    "manchester": "MAN",
    "birmingham": "BHX",
    "edinburgh": "EDI",
    "glasgow": "GLA",

    # UAE
    "dubai": "DXB",
    "abu dhabi": "AUH",
    "sharjah": "SHJ",

    # Asia
    "singapore": "SIN",
    "tokyo": "HND",
    "osaka": "KIX",
    "beijing": "PEK",
    "shanghai": "PVG",
    "hong kong": "HKG",
    "seoul": "ICN",
    "bangkok": "BKK",
    "kuala lumpur": "KUL",
    "jakarta": "CGK",
    "bali": "DPS",
    "kathmandu": "KTM",
    "dhaka": "DAC",
    "colombo": "CMB",

    # Europe
    "paris": "CDG",
    "frankfurt": "FRA",
    "berlin": "BER",
    "rome": "FCO",
    "milan": "MXP",
    "madrid": "MAD",
    "barcelona": "BCN",
    "amsterdam": "AMS",
    "zurich": "ZRH",
    "istanbul": "IST",
    "moscow": "SVO",

    # Australia / Canada
    "sydney": "SYD",
    "melbourne": "MEL",
    "brisbane": "BNE",
    "toronto": "YYZ",
    "vancouver": "YVR",

    # Middle East
    "doha": "DOH",
    "riyadh": "RUH",
    "jeddah": "JED",
    "muscat": "MCT",
    "kuwait city": "KWI",
}


# ============================================================
# CABIN ALIASES
# ============================================================

CABIN_ALIASES = {
    "economy": "economy",
    "eco": "economy",
    "economy class": "economy",

    "premium economy": "premium_economy",

    "business": "business",
    "business class": "business",
    "biz": "business",

    "first": "first",
    "first class": "first",
}


# ============================================================
# TIME RANGES
# ============================================================

TIME_RANGES = {
    "early morning": ("04:00", "08:00"),
    "morning": ("06:00", "12:00"),
    "afternoon": ("12:00", "17:00"),
    "evening": ("17:00", "21:00"),
    "night": ("21:00", "23:59"),
    "late night": ("23:00", "23:59"),
}


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text: str) -> str:

    text = text.lower().strip()

    text = re.sub(
        r"[^a-z0-9\s]",
        "",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    stop_words = [
        "flight",
        "flights",
        "ticket",
        "tickets",
        "trip",
        "travel",
        "plan",
        "complete",
        "days",
        "day",
        "including",
        "hotel",
        "hotels",
        "sightseeing",
        "under",
        "budget",
        "info",
        "information",
        "from",
        "to",
    ]

    words = [
        word
        for word in text.split()
        if word not in stop_words
    ]

    return " ".join(words).strip()


# ============================================================
# COUNTRY RESOLUTION
# ============================================================

def country_name_to_code(text: str) -> Optional[str]:

    text = clean_text(text)

    # Direct alias
    if text in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[text]

    # pycountry lookup
    try:

        country = pycountry.countries.lookup(text)

        return country.alpha_2

    except LookupError:
        pass

    # Search inside longer text
    for country in pycountry.countries:

        country_name = country.name.lower()

        if country_name in text:

            return country.alpha_2

    # Search aliases inside longer text
    for alias, code in COUNTRY_ALIASES.items():

        if alias in text:

            return code

    return None


# ============================================================
# AIRPORT COUNTRY MATCH
# ============================================================

def airport_country_matches(
    airport: dict,
    country_code: str
) -> bool:

    airport_country = str(
        airport.get("country", "")
    ).upper().strip()

    country_code = country_code.upper()

    # Some airport datasets already contain ISO code
    if airport_country == country_code:
        return True

    try:

        country = pycountry.countries.get(
            alpha_2=country_code
        )

        if country:

            if (
                airport_country.lower()
                == country.name.lower()
            ):
                return True

    except Exception:
        pass

    return False


# ============================================================
# RESOLVE LOCATION TO IATA
# ============================================================

def resolve_location(location: str) -> Optional[str]:

    location = clean_text(location)

    # --------------------------------------------------------
    # 1. Direct IATA code
    # --------------------------------------------------------

    if len(location) == 3:

        code = location.upper()

        if code in AIRPORTS:

            return code

    # --------------------------------------------------------
    # 2. City mapping
    # --------------------------------------------------------

    if location in CITY_MAIN_AIRPORT:

        return CITY_MAIN_AIRPORT[location]

    # --------------------------------------------------------
    # 3. Country mapping
    # --------------------------------------------------------

    country_code = country_name_to_code(location)

    if country_code:

        if country_code in COUNTRY_MAIN_AIRPORT:

            return COUNTRY_MAIN_AIRPORT[country_code]

    # --------------------------------------------------------
    # 4. Search airport dataset
    # --------------------------------------------------------

    for iata, airport in AIRPORTS.items():

        name = str(
            airport.get("name", "")
        ).lower()

        city = str(
            airport.get("city", "")
        ).lower()

        country = str(
            airport.get("country", "")
        ).lower()

        if (
            location == city
            or location == name
            or location in city
            or location in name
            or location in country
        ):

            return iata

    return None


# ============================================================
# BUILD TIME RANGE
# ============================================================

def get_time_range(
    preference: Optional[str]
):

    if not preference:
        return None

    preference = preference.lower().strip()

    return TIME_RANGES.get(preference)


# ============================================================
# SEARCH FLIGHTS
# ============================================================

def search_flights(
    origin: str,
    destination: str,
    departure_date: Optional[str] = None,
    airline: Optional[str] = None,
    flight_status: Optional[str] = None,
    limit: int = 20,
):

    if not API_KEY:

        raise ValueError(
            "AVIATIONSTACK_API_KEY is missing."
        )

    params = {
        "access_key": API_KEY,
        "dep_iata": origin,
        "arr_iata": destination,
        "limit": limit,
    }

    # Optional filters
    if departure_date:
        params["flight_date"] = departure_date

    if airline:
        params["airline_name"] = airline

    if flight_status:
        params["flight_status"] = flight_status

    try:

        response = requests.get(
            BASE_URL,
            params=params,
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

    except requests.RequestException as e:

        raise RuntimeError(
            f"Flight API request failed: {e}"
        )

    # Aviationstack API errors
    if "error" in data:

        error = data["error"]

        raise RuntimeError(
            error.get(
                "info",
                "Unknown Aviationstack API error"
            )
        )

    return data.get("data", [])


# ============================================================
# FORMAT FLIGHT RESULTS
# ============================================================

def format_flight(flight: dict) -> dict:

    airline = flight.get(
        "airline",
        {}
    )

    flight_info = flight.get(
        "flight",
        {}
    )

    departure = flight.get(
        "departure",
        {}
    )

    arrival = flight.get(
        "arrival",
        {}
    )

    return {

        "airline": airline.get("name"),

        "flight_number": flight_info.get(
            "iata"
        ),

        "flight_date": flight.get(
            "flight_date"
        ),

        "status": flight.get(
            "flight_status"
        ),

        "origin": departure.get(
            "iata"
        ),

        "origin_airport": departure.get(
            "airport"
        ),

        "departure_time": departure.get(
            "scheduled"
        ),

        "destination": arrival.get(
            "iata"
        ),

        "destination_airport": arrival.get(
            "airport"
        ),

        "arrival_time": arrival.get(
            "scheduled"
        ),
    }


# ============================================================
# HIGH LEVEL FLIGHT SEARCH
# ============================================================

def find_flights(
    origin: str,
    destination: str,
    departure_date: Optional[str] = None,
    departure_time: Optional[str] = None,
    airline: Optional[str] = None,
    limit: int = 20,
):

    # Resolve origin
    origin_iata = resolve_location(origin)

    if not origin_iata:

        raise ValueError(
            f"Could not resolve origin: {origin}"
        )

    # Resolve destination
    destination_iata = resolve_location(destination)

    if not destination_iata:

        raise ValueError(
            f"Could not resolve destination: {destination}"
        )

    # Search API
    flights = search_flights(
        origin=origin_iata,
        destination=destination_iata,
        departure_date=departure_date,
        airline=airline,
        limit=limit,
    )

    # Format
    results = [
        format_flight(flight)
        for flight in flights
    ]

    # --------------------------------------------------------
    # Optional departure time filtering
    # --------------------------------------------------------

    time_range = get_time_range(
        departure_time
    )

    if time_range:

        start_time, end_time = time_range

        filtered = []

        for flight in results:

            scheduled = flight.get(
                "departure_time"
            )

            if not scheduled:
                continue

            # Example:
            # 2026-10-15T08:30:00+00:00
            match = re.search(
                r"T(\d{2}:\d{2})",
                scheduled
            )

            if not match:
                continue

            flight_time = match.group(1)

            if start_time <= flight_time <= end_time:

                filtered.append(flight)

        results = filtered

    return results


# ============================================================
# PRINT RESULTS
# ============================================================

def print_flights(flights: list):

    if not flights:

        print("\nNo flights found.")

        return

    print(
        f"\nFound {len(flights)} flight(s):\n"
    )

    for index, flight in enumerate(
        flights,
        start=1
    ):

        print(
            f"{index}. "
            f"{flight.get('airline')} "
            f"{flight.get('flight_number')}"
        )

        print(
            f"   "
            f"{flight.get('origin')} → "
            f"{flight.get('destination')}"
        )

        print(
            f"   Departure: "
            f"{flight.get('departure_time')}"
        )

        print(
            f"   Arrival: "
            f"{flight.get('arrival_time')}"
        )

        print(
            f"   Status: "
            f"{flight.get('status')}"
        )

        print()


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("Flight Search Tool")
    print("------------------")

    origin = input(
        "Origin: "
    )

    destination = input(
        "Destination: "
    )

    departure_date = input(
        "Departure date (YYYY-MM-DD, optional): "
    ).strip()

    departure_time = input(
        "Time preference "
        "(morning/afternoon/evening/night, optional): "
    ).strip()

    if not departure_date:

        departure_date = None

    if not departure_time:

        departure_time = None

    try:

        flights = find_flights(

            origin=origin,

            destination=destination,

            departure_date=departure_date,

            departure_time=departure_time,

            limit=20,
        )

        print_flights(flights)

    except Exception as e:

        print(
            f"\nError: {e}"
        )