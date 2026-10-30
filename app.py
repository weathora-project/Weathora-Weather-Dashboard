
import os
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson.objectid import ObjectId

load_dotenv(
    dotenv_path=os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        ".env"
    ),
    override=True
)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-secret-key")

# API and database settings
WEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()

print("API Key loaded:", bool(WEATHER_API_KEY))
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGO_DB_NAME", "weathora")

# MongoDB connection
mongo_client = None
db = None
searches_collection = None

try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    mongo_client.admin.command("ping")
    db = mongo_client[DB_NAME]
    searches_collection = db["search_history"]
    print("MongoDB connected successfully!")
except PyMongoError as error:
    print("MongoDB connection failed:", error)


def get_guest_id():
    """Give each browser session its own search history."""
    if "guest_id" not in session:
        session["guest_id"] = str(uuid.uuid4())
    return session["guest_id"]


def get_weather(city):
    """Fetch current weather and a 5-day forecast from OpenWeather."""
    if not WEATHER_API_KEY:
        return None, "OpenWeather API key is missing. Please set it in your .env file."

    current_url = "https://api.openweathermap.org/data/2.5/weather"
    forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {
        "q": city,
        "appid": WEATHER_API_KEY,
        "units": "metric"
    }

    try:
        current_response = requests.get(
            current_url, params=params, timeout=10
        )

        if current_response.status_code == 404:
            return None, "City not found. Please check the city name."

        current_response.raise_for_status()
        current_data = current_response.json()

        forecast_response = requests.get(
            forecast_url, params=params, timeout=10
        )
        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()

        weather = {
            "city": current_data["name"],
            "country": current_data["sys"].get("country", ""),
            "temperature": round(current_data["main"]["temp"]),
            "feels_like": round(current_data["main"]["feels_like"]),
            "humidity": current_data["main"]["humidity"],
            "pressure": current_data["main"]["pressure"],
            "wind_speed": current_data["wind"]["speed"],
            "description": current_data["weather"][0]["description"].title(),
            "icon": current_data["weather"][0]["icon"],
            "visibility": round(current_data.get("visibility", 0) / 1000, 1),
            "sunrise": datetime.fromtimestamp(
                current_data["sys"]["sunrise"]
            ).strftime("%I:%M %p"),
            "sunset": datetime.fromtimestamp(
                current_data["sys"]["sunset"]
            ).strftime("%I:%M %p"),
            "forecast": []
        }

        # OpenWeather returns forecasts in 3-hour intervals.
        # Select one forecast per day, around noon.
        daily = {}
        for item in forecast_data.get("list", []):
            forecast_time = datetime.fromtimestamp(item["dt"])
            day_key = forecast_time.strftime("%Y-%m-%d")

            if day_key not in daily or abs(forecast_time.hour - 12) < abs(
                datetime.fromtimestamp(daily[day_key]["dt"]).hour - 12
            ):
                daily[day_key] = item

        for day_key, item in list(daily.items())[:5]:
            forecast_date = datetime.strptime(day_key, "%Y-%m-%d")
            weather["forecast"].append({
                "day": forecast_date.strftime("%a"),
                "date": forecast_date.strftime("%d %b"),
                "temperature": round(item["main"]["temp"]),
                "description": item["weather"][0]["description"].title(),
                "icon": item["weather"][0]["icon"]
            })

        return weather, None

    except requests.Timeout:
        return None, "Weather service timed out. Please try again."
    except requests.RequestException as error:
         app.logger.exception("Weather API request failed")
         return None, f"Weather API error: {error}"
    except (KeyError, ValueError, TypeError):
        return None, "Unexpected weather data received. Please try again."


def save_search(city, weather):
    """Save the search to MongoDB when the database is available."""
    if searches_collection is None:
        return

    try:
        searches_collection.insert_one({
            "guest_id": get_guest_id(),
            "city": weather["city"],
            "country": weather["country"],
            "temperature": weather["temperature"],
            "description": weather["description"],
            "searched_at": datetime.now(timezone.utc)
        })
    except PyMongoError as error:
        app.logger.error("Could not save search history: %s", error)




@app.get("/")
def home():
    city = request.args.get("city", "").strip()

    weather = None
    error = None

    if city:
        weather, error = get_weather(city)

        if weather:
            save_search(city, weather)

    return render_template(
        "index.html",
        weather=weather,
        error=error,
        city=city
    )




@app.route("/forecast", methods=["GET", "POST"])
def forecast_page():
    city = request.values.get("city", "").strip()
    weather = None
    error = None

    if city:
        weather, error = get_weather(city)
        if weather:
            save_search(city, weather)

    return render_template(
        "forecast.html",
        weather=weather,
        error=error,
        city=city
    )


@app.get("/history")
def history():
    records = []

    if searches_collection is not None:
        try:
            records = list(
                searches_collection.find(
                    {"guest_id": get_guest_id()}
                ).sort("searched_at", -1).limit(50)
            )
        except PyMongoError as error:
            app.logger.error("Could not load history: %s", error)
            flash("Search history is temporarily unavailable.", "error")

    return render_template("history.html", records=records)


@app.post("/history/delete/<record_id>")
def delete_history(record_id):
    if searches_collection is not None:
        try:
            searches_collection.delete_one({
                "_id": ObjectId(record_id),
                "guest_id": get_guest_id()
            })
            flash("Search record deleted.", "success")
        except (PyMongoError, ValueError):
            flash("Could not delete this record.", "error")
    else:
        flash("MongoDB is not connected.", "error")

    return redirect(url_for("history"))


@app.post("/history/clear")
def clear_history():
    if searches_collection is not None:
        try:
            searches_collection.delete_many({
                "guest_id": get_guest_id()
            })
            flash("Search history cleared.", "success")
        except PyMongoError:
            flash("Could not clear history.", "error")
    else:
        flash("MongoDB is not connected.", "error")

    return redirect(url_for("history"))


@app.get("/about")
def about():
    return render_template("about.html")


@app.get("/health")
def health():
    database_status = "connected" if db is not None else "disconnected"
    return {
        "app": "Weathora",
        "status": "running",
        "mongodb": database_status
    }


if __name__ == "__main__":
    app.run(debug=True)
