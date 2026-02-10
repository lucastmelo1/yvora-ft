import streamlit as st
import sys
import platform

st.set_page_config(page_title="Yvora FT | Sanity", layout="wide")
st.title("Yvora FT - Sanity Check")
st.success("Deploy OK. O app iniciou.")

st.write("Python:", sys.version)
st.write("Platform:", platform.platform())
