import streamlit as st
import base64
import requests
import pandas as pd
from io import BytesIO
from io import StringIO
from datetime import datetime
from datetime import date


# ======================
# Dropbox token
# ======================

GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
REPO = st.secrets["GITHUB_REPO"]
BRANCH = "main"  # or whichever branch you use

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def github_file_url(path):
    return f"https://api.github.com/repos/{REPO}/contents/{path}"

def load_csv_from_github(path, columns):
    url = github_file_url(path)
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        content = base64.b64decode(r.json()["content"]).decode("utf-8")
        return pd.read_csv(StringIO(content))
    else:
        return pd.DataFrame(columns=columns)

def save_csv_to_github(df, path, commit_msg="Update data file"):
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    content = base64.b64encode(csv_buffer.getvalue().encode()).decode()

    url = github_file_url(path)
    r = requests.get(url, headers=headers)
    sha = r.json()["sha"] if r.status_code == 200 else None

    data = {
        "message": commit_msg,
        "content": content,
        "branch": BRANCH
    }
    if sha:
        data["sha"] = sha

    r = requests.put(url, headers=headers, json=data)
    if r.status_code not in (200, 201):
        st.error(f"Failed to save {path}: {r.text}")
    else:
        st.success(f"Saved {path} to GitHub!")

DRIVING_FILE = "driving_log.csv"
FUEL_FILE = "fuel_log.csv"

driving_columns = ["Date", "Driver", "Km After", "Driven Km", "Comment", "User"]
fuel_columns = ["Date", "Fueler", "Km", "Euros", "Liters", "Note", "Km since last fueling"]

driving_df = load_csv_from_github(DRIVING_FILE, driving_columns)
fuel_df = load_csv_from_github(FUEL_FILE, fuel_columns)

# ======================
# Everything below can now safely use driving_df and fuel_df
# ======================

last_km = driving_df["Km After"].iloc[-1] if len(driving_df) > 0 else 0
st.write(f"Last km: {last_km}")

user =st.session_state
if hasattr(st, "experimental_user"):
    user_info = st.experimental_user
    user_email = user_info.get("email", "LocalUser") if user_info else "LocalUser"
else:
    user_email = "LocalUser"


st.write(user)
def get_user_name():
    if hasattr(st, "experimental_user"):
        st.write('in if')
        user_info = st.experimental_user
        if user_info:
            st.write(user_info)
            # Try username first, fallback to email, then to LocalUser
            return user_info.get("name") or user_info.get("email") or "LocalUser"
    return "LocalUser"

user_name = get_user_name()
st.write(f"Logged in as: {user_name}")


# Add Driving Trip form, fueling form, stats, etc.

# ======================
# Add Driving Trip
# ======================
st.header("Add Driving Trip")
st.write(f"Letzter Kilometerstand: {last_km} km")  # Display last entry

with st.form("trip_form"):
    trip_date = st.date_input("Date", date.today())  # default = today
    driver = st.text_input("Driver")
    km_after = st.number_input("Kilometers After", min_value=0)
    comment = st.text_input("Comment")
    submitted = st.form_submit_button("Submit Trip")
    trip_date_str = trip_date.strftime("%d.%m.%Y")

if submitted:
    last_km = driving_df["Km After"].iloc[-1] if len(driving_df) > 0 else 0
    driven_km = km_after - last_km

    if driven_km <= 0:
        st.error(f"Error: Kilometers must be greater than last entry ({last_km})")
    else:
   
        # No fueling in between → just one entry
        new_row = {
            "Date": trip_date,
            "Driver": driver,
            "Km After": km_after,
            "Driven Km": driven_km,
            "Comment": comment,
            "User": user_email
        }
        driving_df = pd.concat([driving_df, pd.DataFrame([new_row])], ignore_index=True)

        save_csv_to_github(driving_df, DRIVING_FILE)
        st.session_state["driving_df"] = driving_df
    
        st.success(f"Trip saved! Driven km: {driven_km}")

# ======================
# Add Fueling
# ======================
st.header("Add Fueling")
with st.form("fuel_form"):
    f_date = st.date_input("Date", date.today(), key="fuel_date")
    fueler = st.text_input("Fueler", key="fueler")
    km_fuel = st.number_input("Kilometers", min_value=0, key="km")
    euros = st.number_input("Euros", min_value=0.0, key="euros")
    liters = st.number_input("Liters (optional)", min_value=0.0, key="liters")
    note = st.text_input("Note", key="note")
    fuel_submitted = st.form_submit_button("Submit Fueling")
    fuel_date_str = trip_date.strftime("%d.%m.%Y")

    
    
    if fuel_submitted:
        f_date_str = f_date.strftime("%d.%m.%Y")

        last_km_fuel = fuel_df["Km"].iloc[-1] if len(fuel_df) > 0 else 0
        last_km_drive = driving_df["Km After"].iloc[-1] if len(driving_df) > 0 else 0

        # Basic validation
        if km_fuel <= last_km_fuel:
            st.error(f"Kilometers must be greater than last fueling ({last_km_fuel})")
        elif km_fuel > last_km_drive:
            st.error(f"Add trip first, then fueling! Kilometers are higher than last trip ({last_km_drive})")
        else:
            # Save fueling
            km_since_last = km_fuel - last_km_fuel
            new_fuel = {
                "Date": f_date_str,
                "Fueler": fueler,
                "Km": km_fuel,
                "Euros": euros,
                "Liters": liters,
                "Note": note,
                "Km since last fueling": km_since_last
            }
            fuel_df = pd.concat([fuel_df, pd.DataFrame([new_fuel])], ignore_index=True)
            save_csv_to_github(fuel_df, FUEL_FILE)
            st.session_state["fuel_df"] = fuel_df
            st.success(f"Fueling saved! Km since last fueling: {km_since_last}")

            # ---- Check for trips that include this fueling ----
            trips_to_split = driving_df[(driving_df["Km After"] >= last_km_fuel) & (driving_df["Km After"] <= km_fuel)]
            
         # Find trips that include this fueling
            # Split trip at fueling
        for idx, trip in driving_df.iterrows():
            start_km = trip["Km After"] - trip["Driven Km"]
            end_km = trip["Km After"]
            
            if start_km < km_fuel < end_km:
                # Segment before fueling
                segment1 = {
                    "Date": trip["Date"],
                    "Driver": trip["Driver"],
                    "Km After": km_fuel,
                    "Driven Km": km_fuel - start_km,
                    "Comment": "AUTOMATICALLY FUELED",
                    "User": user_email
                }
                # Segment after fueling
                segment2 = {
                    "Date": trip["Date"],
                    "Driver": trip["Driver"],
                    "Km After": end_km,
                    "Driven Km": end_km - km_fuel,
                    "Comment": trip["Comment"],
                    "User": trip["User"]
                }

                # Drop the original trip
                driving_df = driving_df.drop(idx)

                # Append the two segments
                driving_df = pd.concat([driving_df, pd.DataFrame([segment1, segment2])], ignore_index=True)

                # Sort by kilometers to keep correct order
                driving_df = driving_df.sort_values("Km After").reset_index(drop=True)

                save_csv_to_github(driving_df, DRIVING_FILE)
                st.session_state["driving_df"] = driving_df
                break

                

        # ======================
        # Driver Stats
        # ======================
        st.header("Driver Stats")
if len(driving_df) > 0:
    total_km = driving_df.groupby("Driver")["Driven Km"].sum().reset_index()
    st.subheader("Total Kilometers per Driver")
    st.dataframe(total_km)
else:
    st.write("No trips logged yet.")

# ======================
# Fuel Cost Sharing and Balance Grid
# ======================
st.header("Fuel Cost Sharing & Balance Grid EXPERIMENTAL NOT EVERYTHING TESTED YET")
if len(fuel_df) > 0 and len(driving_df) > 0:
    # Include both drivers and fuelers
    drivers = sorted(set(driving_df["Driver"].unique()) | set(fuel_df["Fueler"].unique()))
    balances = {d1: {d2: 0 for d2 in drivers} for d1 in drivers}
    
    for idx, fuel in fuel_df.iterrows():
        km_start = fuel["Km"] - fuel["Km since last fueling"]
        interval_trips = driving_df[(driving_df["Km After"] > km_start) & (driving_df["Km After"] <= fuel["Km"])]
        driver_km = interval_trips.groupby("Driver")["Driven Km"].sum()
        total_interval_km = driver_km.sum()
        if total_interval_km > 0:
            for d in driver_km.index:
                share = driver_km[d] / total_interval_km * fuel["Euros"]
                if d != fuel["Fueler"]:
                    balances[d][fuel["Fueler"]] += share
    
    # Build balance grid
    grid = pd.DataFrame(balances).T

    # Drop rows and columns that are entirely zero
    grid = grid.loc[(grid != 0).any(axis=1), (grid != 0).any(axis=0)]

    # Rename axes
    grid.index = [f"{name} owes" for name in grid.index]
    grid.columns = [f"{name} gets" for name in grid.columns]

    st.subheader("Who Owes Whom (€)")
    if grid.empty:
        st.write("Currently no balances.")
    else:
        st.dataframe(grid.style.format("{:.2f}"))
else:
    st.write("Not enough data for fuel stats yet.")
