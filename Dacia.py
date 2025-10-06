import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import dropbox
import os

# ======================
# Dropbox Setup
# ======================
dbx = None  # placeholder

if "DROPBOX_TOKEN" not in st.session_state:
    st.warning("Please enter your Dropbox access token to activate the app.")
    token_input = st.text_input("Dropbox Access Token", type="password")
    
    if st.button("Activate App"):
        if token_input:
            st.session_state["DROPBOX_TOKEN"] = token_input
            st.success("App activated!")
            st.experimental_rerun()  # rerun the app now that token exists
        else:
            st.error("Token cannot be empty.")
else:
    TOKEN = st.session_state["DROPBOX_TOKEN"]
    dbx = dropbox.Dropbox(TOKEN)
    st.success("Dropbox connected!")

# ======================
# Only run Dropbox-dependent code if dbx exists
# ======================
if dbx:
    DRIVING_FILE = "/driving_log.csv"
    FUEL_FILE = "/fuel_log.csv"

    driving_columns = ["Date", "Driver", "Km After", "Driven Km", "Comment", "User"]
    fuel_columns = ["Date", "Driver", "Km At Fuel", "Liters", "Euros", "Comment", "User"]

    # Load CSVs
    def load_csv(path, columns):
        try:
            metadata, res = dbx.files_download(path)
            data = res.content
            df = pd.read_csv(BytesIO(data))
            return df
        except dropbox.exceptions.ApiError:
            return pd.DataFrame(columns=columns)

    driving_df = load_csv(DRIVING_FILE, driving_columns)
    fuel_df = load_csv(FUEL_FILE, fuel_columns)

    st.write(driving_df)  # show driving log
    st.write(fuel_df)     # show fuel log

    # Save CSV to Dropbox
    def save_csv(df, path):
        with BytesIO() as f:
            df.to_csv(f, index=False)
            f.seek(0)
            dbx.files_upload(f.read(), path, mode=dropbox.files.WriteMode.overwrite)

    # Get last kilometers
    last_km = driving_df["Km After"].iloc[-1] if len(driving_df) > 0 else 0

    # ======================
    # Add Driving Trip
    # ======================
    st.header("Add Driving Trip")
    st.write(f"Letzter Kilometerstand: {last_km} km")  # Display last entry

    with st.form("trip_form"):
        date = st.date_input("Date", datetime.today())
        driver = st.text_input("Driver")
        km_after = st.number_input("Kilometers After", min_value=0)
        comment = st.text_input("Comment")
        submitted = st.form_submit_button("Submit Trip")
        
        if submitted:
            last_km = driving_df["Km After"].iloc[-1] if len(driving_df) > 0 else 0
            driven_km = km_after - last_km
            if driven_km <= 0:
                st.error(f"Error: Kilometers must be greater than last entry ({last_km})")
            else:
                user = "LocalUser"
                new_row = {"Date": date, "Driver": driver, "Km After": km_after,
                        "Driven Km": driven_km, "Comment": comment, "User": user}
                driving_df = pd.concat([driving_df, pd.DataFrame([new_row])], ignore_index=True)
                save_csv(driving_df, DRIVING_FILE)
                st.success(f"Trip saved! Driven km: {driven_km}")

    # ======================
    # Add Fueling
    # ======================
    st.header("Add Fueling")
    with st.form("fuel_form"):
        f_date = st.date_input("Date", datetime.today(), key="fuel_date")
        fueler = st.text_input("Fueler", key="fueler")
        km = st.number_input("Kilometers", min_value=0, key="km")
        euros = st.number_input("Euros", min_value=0.0, key="euros")
        liters = st.number_input("Liters (optional)", min_value=0.0, key="liters")
        note = st.text_input("Note", key="note")
        fuel_submitted = st.form_submit_button("Submit Fueling")
        
        if fuel_submitted:
            last_km = fuel_df["Km"].iloc[-1] if len(fuel_df) > 0 else 0
            if km <= last_km:
                st.error(f"Kilometers must be greater than last fueling ({last_km})")
            else:
                km_since_last = km - last_km
                new_fuel = {"Date": f_date, "Fueler": fueler, "Km": km,
                            "Euros": euros, "Liters": liters, "Note": note,
                            "Km since last fueling": km_since_last}
                fuel_df = pd.concat([fuel_df, pd.DataFrame([new_fuel])], ignore_index=True)
                save_csv(fuel_df, FUEL_FILE)
                st.success(f"Fueling saved! Km since last fueling: {km_since_last}")

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
    st.header("Fuel Cost Sharing & Balance Grid")
    if len(fuel_df) > 0 and len(driving_df) > 0:
        drivers = driving_df["Driver"].unique()
        balances = {d1: {d2: 0 for d2 in drivers} for d1 in drivers}
        
        for idx, fuel in fuel_df.iterrows():
            km_start = fuel["Km"] - fuel["Km since last fueling"]
            interval_trips = driving_df[(driving_df["Km After"] > km_start) & (driving_df["Km After"] <= fuel["Km"])]
            driver_km = interval_trips.groupby("Driver")["Driven Km"].sum()
            total_interval_km = driver_km.sum()
            if total_interval_km > 0:
                for d in driver_km.index:
                    share = driver_km[d]/total_interval_km * fuel["Euros"]
                    if d != fuel["Fueler"]:
                        balances[d][fuel["Fueler"]] += share
        
        # Display balance grid
        st.subheader("Who Owes Whom (€)")
        grid = pd.DataFrame(balances).T  # rows = debtor, columns = creditor
        st.dataframe(grid)
    else:
        st.write("Not enough data for fuel stats yet.")
