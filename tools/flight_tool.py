import os 
import re
import certifi
import airportsdata
import pycountry

from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

API_KEY = os.getenv("AVIATIONSTACK_API_KEY")

DEFAULT_ORIGIN_IATA = os.getenv("DEFAULT_ORIGIN_IATA", "IND")

BASE_URL = "http://api.aviationstack.com/v1/flights"

AIRPORTS = airportsdata.load("IATA")

COUNTRY_ALIASES = {
    "usa": "United States",
    "us": "United States",
    "america": "United States",

    "uk": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",

    "uae": "United Arab Emirates",
    "emirates": "United Arab Emirates",

    "ksa": "Saudi Arabia",
    "saudi": "Saudi Arabia",

    "bharat": "India",
    "hindustan": "India",

    "turkey": "Türkiye",
    "turkiye": "Türkiye",

    "holland": "Netherlands",

    "south korea": "South Korea",
    "korea": "South Korea",

    "russia": "Russia",
    "prc": "China",

    "japan": "Japan",
    "nippon": "Japan",

    "germany": "Germany",
    "deutschland": "Germany",

    "france": "France",
    "italy": "Italy",
    "spain": "Spain",

    "singapore": "Singapore",
    "malaysia": "Malaysia",
    "thailand": "Thailand",
    "indonesia": "Indonesia",

    "nepal": "Nepal",
    "bangladesh": "Bangladesh",
    "pakistan": "Pakistan",
    "sri lanka": "Sri Lanka",

    "qatar": "Qatar",
    "canada": "Canada",
    "australia": "Australia",
    "new zealand": "New Zealand",

    "brazil": "Brazil",
    "mexico": "Mexico",
    "south africa": "South Africa",
}


COUNTRY_MAIN_AIRPORT = {
    "india": "DEL",              # Indira Gandhi International Airport
    "united states": "JFK",      # John F. Kennedy International Airport
    "united kingdom": "LHR",     # London Heathrow
    "uae": "DXB",                # Dubai International
    "saudi arabia": "RUH",       # King Khalid International
    "qatar": "DOH",              # Hamad International
    "singapore": "SIN",          # Changi
    "japan": "NRT",              # Narita
    "china": "PEK",              # Beijing Capital
    "south korea": "ICN",        # Incheon
    "thailand": "BKK",           # Suvarnabhumi
    "malaysia": "KUL",            # Kuala Lumpur International
    "indonesia": "CGK",           # Soekarno-Hatta
    "nepal": "KTM",               # Tribhuvan International
    "bangladesh": "DAC",          # Hazrat Shahjalal International
    "sri lanka": "CMB",           # Bandaranaike International
    "pakistan": "LHE",            # Lahore
    "australia": "SYD",           # Sydney
    "new zealand": "AKL",         # Auckland
    "canada": "YYZ",               # Toronto Pearson
    "france": "CDG",               # Paris Charles de Gaulle
    "germany": "FRA",              # Frankfurt
    "italy": "FCO",                # Rome Fiumicino
    "spain": "MAD",                # Madrid
    "netherlands": "AMS",          # Amsterdam Schiphol
    "switzerland": "ZRH",          # Zurich
    "turkey": "IST",               # Istanbul
    "russia": "SVO",               # Sheremetyevo
    "brazil": "GRU",               # São Paulo Guarulhos
    "mexico": "MEX",               # Mexico City
    "south africa": "JNB",         # Johannesburg
}

CITY_MAIN_AIRPORT = {
    # India
    "delhi": "DEL",
    "mumbai": "BOM",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "hyderabad": "HYD",
    "chennai": "MAA",
    "kolkata": "CCU",
    "pune": "PNQ",
    "ahmedabad": "AMD",
    "goa": "GOI",
    "jaipur": "JAI",
    "lucknow": "LKO",
    "kochi": "COK",
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

def clean_text(text: str)-> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    stop_words = [
        "flight", "flights", "ticket", "tickets", "trip", "travel",
        "plan", "complete", "days","day", "including", "hotel", "hotels",
        "sightseeing","under", "budget", "info", "information"
    ]

    words = [w for w in text.split() if w not in stop_words]
    return " ".join(words).strip()

def country_name_to_code(text: str):
    text = clean_text(text)

    if text in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[text]

    try:
        country = pycountry.countries.lookup(text)
        return country.alpha_2
    except LookupError:
        pass

    #detect country name inside longer text
    for country in pycountry.countries:
        country_name = country.name.lower()
        if country_name in text:
            return country.alpha_2

    for alias, code in COUNTRY_ALIASES.items():
        if alias in text:
            return code

    return None            

def airport_country_matches(airport: dict, country_code: str)-> bool:
    airport_country = str(airport.get("country", "")).upper().split

    if airport_country == country_code:
        return True

    try:
        country = pycountry.countries.get(alpha_2=country_code)
        if country and airport_country.lower() == country.name.lower():
            return True
    except Exception:
        pass
    return False

if __name__ == "__main__":
    query = input("Enter your search query: ")
    results = country_name_to_code(query)
    print(results)    