import streamlit as st
import requests
import pandas as pd

API_URL = "http://localhost:8000"

st.set_page_config(page_title="Comparison View", page_icon="📊")
st.markdown("# Asset Comparison")

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
existing_symbols = [a['symbol'] for a in assets]

# --- Asset Selection ---
st.subheader("Select or Add Assets")

selected_symbols = st.multiselect(
    "Choose from existing assets",
    options=existing_symbols,
    default=existing_symbols[:2] if len(existing_symbols) >= 2 else existing_symbols
)

# Custom symbol input
st.markdown("**Or add new symbols:**")
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    new_symbol = st.text_input(
        "Enter a new symbol",
        placeholder="TSLA, NVDA, SOL-USD...",
        label_visibility="collapsed"
    ).strip().upper()
with col2:
    new_asset_type = st.selectbox("Type", ["stock", "crypto"], label_visibility="collapsed")
with col3:
    add_clicked = st.button("Add & Fetch")

if add_clicked and new_symbol:
    if new_symbol not in existing_symbols:
        with st.spinner(f"Fetching {new_symbol}..."):
            try:
                res = requests.post(
                    f"{API_URL}/sync/{new_symbol}",
                    params={"asset_type": new_asset_type}
                )
                if res.status_code == 200:
                    st.success(f"Added and synced {new_symbol}!")
                    st.cache_data.clear()
                    st.experimental_rerun()
                else:
                    st.error(f"Failed to add {new_symbol}: {res.text}")
            except Exception as e:
                st.error(f"Error: {e}")
    else:
        st.warning(f"{new_symbol} already exists. Select it from the list above.")

st.markdown("---")

# Build comparison table
if selected_symbols:
    comparison_data = []
    missing_data_symbols = []
    
    for symbol in selected_symbols:
        try:
            res = requests.get(f"{API_URL}/prices/{symbol}")
            data = res.json() if res.status_code == 200 else []
            
            if data:
                latest = data[0]
                comparison_data.append({
                    "Symbol": symbol,
                    "Latest Date": latest['timestamp'],
                    "Close Price": f"${latest['close_price']:,.2f}" if latest['close_price'] else "N/A",
                    "Volume": f"{latest['volume']:,.0f}" if latest['volume'] else "N/A"
                })
            else:
                missing_data_symbols.append(symbol)
        except Exception:
            missing_data_symbols.append(symbol)
            
    if comparison_data:
        st.subheader("Comparison Table (Weekly Data)")
        st.write(comparison_data)
    
    if missing_data_symbols:
        st.warning(f"No data found for: {', '.join(missing_data_symbols)}. Try syncing them from the Single Asset page.")
else:
    st.info("Select at least one asset to compare.")
