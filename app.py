import streamlit as st
import psycopg2
import psycopg2.extras

def get_conn():
    return psycopg2.connect(st.secrets["NEON_DATABASE_URL"], sslmode="require")

def get_series_list():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COALESCE(series, 'Standalone') as series,
            author,
            COUNT(*) as total_books,
            COUNT(*) FILTER (WHERE status = 'Finished') as finished,
            COUNT(*) FILTER (WHERE status = 'DNF') as dnf,
            COUNT(*) FILTER (WHERE status = 'Abandoned') as abandoned,
            ROUND(AVG(gr_rate), 1) as avg_gr_rate,
            ROUND(AVG(expected_rate), 1) as avg_expected_rate,
            MIN(booktitle) as sample_title
        FROM books
        GROUP BY COALESCE(series, 'Standalone'), author
        ORDER BY author, series NULLS LAST
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def compute_status(row):
    total = row['total_books']
    finished = row['finished']
    dnf = row['dnf']
    abandoned = row['abandoned']
    series = row['series']

    if series == 'Standalone':
        if finished > 0: return 'Finished'
        if dnf > 0: return 'DNF'
        if abandoned > 0: return 'Abandoned'
        return 'TBR'

    if finished == total: return 'Finished'
    if finished > 0: return 'Part of the Series Read'
    if dnf > 0: return 'DNF'
    if abandoned > 0: return 'Abandoned'
    return 'TBR'

STATUS_COLOR = {
    'Finished':                '#4a7c59',
    'Part of the Series Read': '#7a6a2a',
    'TBR':                     '#2a4a7a',
    'DNF':                     '#7a2a2a',
    'Abandoned':               '#4a2a5a',
}
STATUS_ICON = {
    'Finished':                '✅',
    'Part of the Series Read': '📖',
    'TBR':                     '📚',
    'DNF':                     '❌',
    'Abandoned':               '🚫',
}

def stars(rate, max_rate=10):
    if not rate:
        return '<span style="color:#555">—</span>'
    filled = round(rate / max_rate * 5)
    empty = 5 - filled
    pct = rate / max_rate
    if pct >= 0.8:   color = '#c9a84c'
    elif pct >= 0.6: color = '#a0c878'
    elif pct >= 0.4: color = '#e09050'
    else:            color = '#c05050'
    return f'<span style="color:{color}; font-size:1rem;">{"★"*filled}{"☆"*empty}</span> <span style="color:#aaa; font-size:0.8rem;">{rate}</span>'

st.set_page_config(page_title="My Bookshelf", page_icon="📚", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600&family=Crimson+Pro&display=swap');
html, body, [class*="css"] { font-family: 'Crimson Pro', serif; background: #0f0f0f; color: #e8e0d0; }
h1 { font-family: 'Playfair Display', serif; color: #c9a84c !important; }
.row-box {
    background: #1a1a1a;
    border: 1px solid #2e2a20;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 8px;
    cursor: pointer;
    transition: border-color 0.2s;
}
.row-box:hover { border-color: #c9a84c; }
.series-title { font-family: 'Playfair Display', serif; font-size: 1rem; color: #e8e0d0; }
.author-name  { font-size: 0.8rem; color: #7a7060; margin-top: 2px; }
.status-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

st.markdown("# 📚 My Bookshelf")
st.divider()

search = st.text_input("", placeholder="🔍  Search by title, series or author…")
status_filter = st.selectbox("Filter by status", ["All", "Finished", "Part of the Series Read", "TBR", "DNF", "Abandoned"], label_visibility="collapsed")

series_list = get_series_list()

for row in series_list:
    status = compute_status(row)

    if status_filter != "All" and status != status_filter:
        continue
    if search:
        haystack = f"{row['series']} {row['author']} {row['sample_title']}".lower()
        if search.lower() not in haystack:
            continue

    color  = STATUS_COLOR[status]
    icon   = STATUS_ICON[status]
    badge  = f'<span class="status-badge" style="background:{color}22; color:{color}; border:1px solid {color}66">{icon} {status}</span>'
    gr     = stars(row['avg_gr_rate'])
    exp    = stars(row['avg_expected_rate'])
    books_str = f'<span style="color:#7a7060; font-size:0.8rem;">{row["total_books"]} book{"s" if row["total_books"]>1 else ""}</span>'

    col1, col2, col3, col4 = st.columns([4, 2, 2, 2])
    with col1:
        st.markdown(f'<div class="series-title">{row["series"]}</div><div class="author-name">{row["author"]}</div>', unsafe_allow_html=True)
    with col2:
        st.markdown(badge, unsafe_allow_html=True)
    with col3:
        st.markdown(f'<span style="color:#7a7060;font-size:0.75rem;">GR </span>{gr}', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<span style="color:#7a7060;font-size:0.75rem;">Expected </span>{exp}', unsafe_allow_html=True)
    
    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
