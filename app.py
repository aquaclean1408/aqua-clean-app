import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.title("Aqua Clean - Registro de Datos")

conn = st.connection("gsheets", type=GSheetsConnection)
df = conn.read(ttl=0)

st.dataframe(df)
