import streamlit as st
import requests
import pandas as pd

API_URL = "http://localhost:8000"

st.set_page_config(page_title="Single Asset View", page_icon="📈")
st.markdown("# Single Asset View")

# Fetch available assets for dropdown
@st.cache_data
def get_assets():
    try:
        response = requests.get(f"{API_URL}/assets")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Error connecting to API: {e}")
    return []

assets = get_assets()
asset_options = {a['symbol']: a for a in assets}
existing_symbols = list(asset_options.keys())

# --- Asset Selection ---
st.subheader("Select or Add an Asset")

col1, col2 = st.columns(2)

with col1:
    selected_from_list = st.selectbox(
        "Choose from existing assets",
        options=[""] + existing_symbols,
        format_func=lambda x: "-- Select --" if x == "" else x
    )

with col2:
    custom_symbol = st.text_input(
        "Or enter a new symbol (e.g., TSLA, ETH-USD)",
        placeholder="TSLA"
    ).strip().upper()

# Determine which symbol to use
if custom_symbol:
    selected_symbol = custom_symbol
    is_new_asset = custom_symbol not in existing_symbols
elif selected_from_list:
    selected_symbol = selected_from_list
    is_new_asset = False
else:
    selected_symbol = None
    is_new_asset = False

if selected_symbol:
    st.markdown("---")
    
    # Asset type selection for new assets
    if is_new_asset:
        st.info(f"**{selected_symbol}** is not in our database yet. Click 'Fetch & Cache' to retrieve its data.")
        asset_type = st.radio("Asset Type", ["stock", "crypto"], horizontal=True)
    else:
        asset_type = asset_options.get(selected_symbol, {}).get('asset_type', 'stock')
    
    # Sync/Fetch Button
    button_label = "Fetch & Cache Data" if is_new_asset else f"Sync Data for {selected_symbol}"
    if st.button(button_label):
        with st.spinner("Fetching data from market..."):
            try:
                res = requests.post(
                    f"{API_URL}/sync/{selected_symbol}", 
                    params={"asset_type": asset_type}
                )
                if res.status_code == 200:
                    st.success(f"Successfully synced {selected_symbol}")
                    st.cache_data.clear()
                    st.experimental_rerun()
                else:
                    st.error(f"Sync failed: {res.text}")
            except Exception as e:
                st.error(f"Error connecting to API: {e}")

    # Fetch and display history
    try:
        res = requests.get(f"{API_URL}/prices/{selected_symbol}")
        if res.status_code == 200:
            data = res.json()
            if data:
                df = pd.DataFrame(data)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                for col in df.select_dtypes(include=['object']).columns:
                    df[col] = df[col].astype(str)
                    
                df = df.sort_values("timestamp")
                
                st.subheader(f"Price History ({selected_symbol}) - Weekly")
                st.line_chart(df, x="timestamp", y="close_price")
                
                with st.expander("View Raw Data"):
                    st.write(df.to_dict(orient='records'))
            elif not is_new_asset:
                st.info("No data found. Try syncing the asset.")
    except Exception as e:
        if not is_new_asset:
            st.error(f"API Error: {e}")
