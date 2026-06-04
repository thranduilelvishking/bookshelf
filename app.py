import streamlit as st
import psycopg2
import psycopg2.extras

def get_conn():
    return psycopg2.connect(st.secrets["NEON_DATABASE_URL"], sslmode="require")

try:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) as total FROM books")
    row = cur.fetchone()
    conn.close()
    st.success(f"✅ Connected! Found {row['total']} books in your database.")
except Exception as e:
    st.error(f"❌ Connection failed: {e}")
