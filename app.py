import streamlit as st
import psycopg2
import psycopg2.extras

def get_conn():
    return psycopg2.connect(st.secrets["NEON_DATABASE_URL"], sslmode="require")

# ── Data fetchers ─────────────────────────────────────────────────────────────

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
            ROUND(AVG(expected_rate), 1) as avg_expected_rate
        FROM books
        GROUP BY COALESCE(series, 'Standalone'), author
        ORDER BY author, series NULLS LAST
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def get_series_books(series, author):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if series == 'Standalone':
        cur.execute("""
            SELECT * FROM books
            WHERE series IS NULL AND author = %s
            ORDER BY booktitle
        """, (author,))
    else:
        cur.execute("""
            SELECT * FROM books
            WHERE series = %s AND author = %s
            ORDER BY subseries NULLS FIRST, reading_order NULLS LAST, booktitle
        """, (series, author))
    rows = cur.fetchall()
    conn.close()
    return rows

def update_book(book_id, fields: dict):
    conn = get_conn()
    cur = conn.cursor()
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [book_id]
    cur.execute(f"UPDATE books SET {set_clause} WHERE id = %s", values)
    conn.commit()
    conn.close()

# ── Helpers ───────────────────────────────────────────────────────────────────

STATUSES = ['TBR', 'Finished', 'Part of the Series Read', 'DNF', 'Abandoned']
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

def compute_status(row):
    total    = row['total_books']
    finished = row['finished']
    dnf      = row['dnf']
    abandoned= row['abandoned']
    series   = row['series']
    if series == 'Standalone':
        if finished > 0:  return 'Finished'
        if dnf > 0:       return 'DNF'
        if abandoned > 0: return 'Abandoned'
        return 'TBR'
    if finished == total: return 'Finished'
    if finished > 0:      return 'Part of the Series Read'
    if dnf > 0:           return 'DNF'
    if abandoned > 0:     return 'Abandoned'
    return 'TBR'

def stars(rate, max_rate=10):
    if not rate:
        return '<span style="color:#555">—</span>'
    filled = round(rate / max_rate * 5)
    empty  = 5 - filled
    pct    = rate / max_rate
    if pct >= 0.8:   color = '#c9a84c'
    elif pct >= 0.6: color = '#a0c878'
    elif pct >= 0.4: color = '#e09050'
    else:            color = '#c05050'
    return f'<span style="color:{color}">{"★"*filled}{"☆"*empty}</span> <span style="color:#aaa; font-size:0.8rem;">{rate}</span>'

def badge(status):
    color = STATUS_COLOR.get(status, '#555')
    icon  = STATUS_ICON.get(status, '📚')
    return f'<span style="background:{color}22; color:{color}; border:1px solid {color}66; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:600;">{icon} {status}</span>'

# ── Global style ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="My Bookshelf", page_icon="📚", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600&family=Crimson+Pro&display=swap');
html, body, [class*="css"] { font-family: 'Crimson Pro', serif; background: #0f0f0f; color: #e8e0d0; }
h1, h2, h3 { font-family: 'Playfair Display', serif; color: #c9a84c !important; }
.series-title { font-family: 'Playfair Display', serif; font-size: 1rem; color: #e8e0d0; }
.author-name  { font-size: 0.8rem; color: #7a7060; margin-top: 2px; }
div[data-testid="stHorizontalBlock"]:hover { background: #1e1e1e; border-radius: 8px; }
.subseries-header {
    font-family: 'Playfair Display', serif;
    color: #c9a84c;
    font-size: 0.95rem;
    border-bottom: 1px solid #2e2a20;
    padding-bottom: 4px;
    margin: 18px 0 10px;
}
.book-row {
    background: #1a1a1a;
    border: 1px solid #2e2a20;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 6px;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

if 'selected_series' not in st.session_state:
    st.session_state.selected_series = None
if 'selected_author' not in st.session_state:
    st.session_state.selected_author = None
if 'editing_book' not in st.session_state:
    st.session_state.editing_book = None

# ══════════════════════════════════════════════════════════════════════════════
# DETAIL PAGE
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.selected_series:
    series = st.session_state.selected_series
    author = st.session_state.selected_author

    if st.button("← Back to Library"):
        st.session_state.selected_series = None
        st.session_state.selected_author = None
        st.session_state.editing_book    = None
        st.rerun()

    st.markdown(f"## {series}")
    st.markdown(f"<div style='color:#7a7060; margin-top:-12px; margin-bottom:16px;'>{author}</div>", unsafe_allow_html=True)
    st.divider()

    books = get_series_books(series, author)

    # Group by subseries
    groups = {}
    for b in books:
        key = b['subseries'] or '—'
        groups.setdefault(key, []).append(b)

    for group_name, group_books in groups.items():
        if len(groups) > 1:
            label = group_name if group_name != '—' else 'Main Series'
            st.markdown(f'<div class="subseries-header">📂 {label}</div>', unsafe_allow_html=True)

        for book in group_books:
            book_id = book['id']
            is_editing = st.session_state.editing_book == book_id

            with st.container():
                # ── View mode ─────────────────────────────────────────────
                if not is_editing:
                    c1, c2, c3, c4, c5 = st.columns([4, 2, 1, 1, 1])
                    order_str = f"#{int(book['reading_order'])} — " if book['reading_order'] else ""
                    c1.markdown(f"<div class='series-title'>{order_str}{book['booktitle']}</div>", unsafe_allow_html=True)
                    c2.markdown(badge(book['status'] or 'TBR'), unsafe_allow_html=True)
                    c3.markdown(stars(book['my_rate']), unsafe_allow_html=True)
                    c4.markdown(stars(book['gr_rate']), unsafe_allow_html=True)
                    if c5.button("✏️ Edit", key=f"edit_{book_id}"):
                        st.session_state.editing_book = book_id
                        st.rerun()

                # ── Edit mode ─────────────────────────────────────────────
                else:
                    st.markdown(f"<div class='series-title' style='margin-bottom:12px;'>Editing: {book['booktitle']}</div>", unsafe_allow_html=True)

                    col_a, col_b = st.columns(2)
                    new_title  = col_a.text_input("Title",  value=book['booktitle'] or '', key=f"title_{book_id}")
                    new_author = col_b.text_input("Author", value=book['author'] or '',    key=f"author_{book_id}")

                    col_c, col_d = st.columns(2)
                    new_series    = col_c.text_input("Series",    value=book['series'] or '',    key=f"series_{book_id}")
                    new_subseries = col_d.text_input("Subseries", value=book['subseries'] or '', key=f"sub_{book_id}")

                    col_e, col_f = st.columns(2)
                    cur_order  = int(book['reading_order']) if book['reading_order'] else 0
                    new_order  = col_e.number_input("Reading order", min_value=0, value=cur_order, key=f"order_{book_id}")
                    cur_status = book['status'] if book['status'] in STATUSES else 'TBR'
                    new_status = col_f.selectbox("Status", STATUSES, index=STATUSES.index(cur_status), key=f"status_{book_id}")

                    col_g, col_h, col_i = st.columns(3)
                    new_my_rate  = col_g.number_input("My Rating",       0.0, 10.0, float(book['my_rate'] or 0),       0.5, key=f"my_{book_id}")
                    new_gr_rate  = col_h.number_input("GR Rating",       0.0, 10.0, float(book['gr_rate'] or 0),       0.5, key=f"gr_{book_id}")
                    new_exp_rate = col_i.number_input("Expected Rating",  0.0, 10.0, float(book['expected_rate'] or 0), 0.5, key=f"exp_{book_id}")

                    new_pros    = st.text_input("Pros",    value=book['pros'] or '',        key=f"pros_{book_id}")
                    new_cons    = st.text_input("Cons",    value=book['cons'] or '',        key=f"cons_{book_id}")
                    new_comment = st.text_area("Comment", value=book['my_comment'] or '',   key=f"comment_{book_id}")

                    col_save, col_cancel = st.columns([1, 5])
                    if col_save.button("💾 Save", key=f"save_{book_id}"):
                        update_book(book_id, {
                            'booktitle':     new_title,
                            'author':        new_author,
                            'series':        new_series or None,
                            'subseries':     new_subseries or None,
                            'reading_order': new_order or None,
                            'status':        new_status,
                            'my_rate':       new_my_rate or None,
                            'gr_rate':       new_gr_rate or None,
                            'expected_rate': new_exp_rate or None,
                            'pros':          new_pros or None,
                            'cons':          new_cons or None,
                            'my_comment':    new_comment or None,
                        })
                        st.session_state.editing_book = None
                        st.success("✅ Saved!")
                        st.rerun()
                    if col_cancel.button("Cancel", key=f"cancel_{book_id}"):
                        st.session_state.editing_book = None
                        st.rerun()

            st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)

    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN LIBRARY PAGE
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("# 📚 My Bookshelf")
st.divider()

col_search, col_filter, col_sort = st.columns([3, 2, 2])
search        = col_search.text_input("", placeholder="🔍  Search by title, series or author…")
status_filter = col_filter.selectbox("Status", ["All"] + STATUSES, label_visibility="collapsed")
sort_by       = col_sort.selectbox("Sort by", ["Author", "Series", "GR Rating ↓", "Expected Rating ↓"], label_visibility="collapsed")

series_list = get_series_list()

# Apply filters
filtered = []
for row in series_list:
    status = compute_status(row)
    if status_filter != "All" and status != status_filter:
        continue
    if search:
        haystack = f"{row['series']} {row['author']}".lower()
        if search.lower() not in haystack:
            continue
    filtered.append({**row, 'status': status})

# Apply sort
if sort_by == "Author":
    filtered.sort(key=lambda r: (r['author'].lower(), r['series'].lower()))
elif sort_by == "Series":
    filtered.sort(key=lambda r: r['series'].lower())
elif sort_by == "GR Rating ↓":
    filtered.sort(key=lambda r: r['avg_gr_rate'] or 0, reverse=True)
elif sort_by == "Expected Rating ↓":
    filtered.sort(key=lambda r: r['avg_expected_rate'] or 0, reverse=True)

st.markdown(f"<p style='color:#7a7060; font-size:0.85rem;'>{len(filtered)} entries</p>", unsafe_allow_html=True)

# Column headers
h1, h2, h3, h4, h5 = st.columns([4, 2, 2, 2, 1])
for col, label in zip([h1,h2,h3,h4,h5], ["Series / Title","Status","GR Rating","Expected","Books"]):
    col.markdown(f"<small style='color:#7a7060;'>{label}</small>", unsafe_allow_html=True)
st.divider()

for row in filtered:
    c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 2, 1])
    with c1:
        st.markdown(f"<div class='series-title'>{row['series']}</div><div class='author-name'>{row['author']}</div>", unsafe_allow_html=True)
    with c2:
        st.markdown(badge(row['status']), unsafe_allow_html=True)
    with c3:
        st.markdown(stars(row['avg_gr_rate']), unsafe_allow_html=True)
    with c4:
        st.markdown(stars(row['avg_expected_rate']), unsafe_allow_html=True)
    with c5:
        if st.button("→", key=f"open_{row['series']}_{row['author']}"):
            st.session_state.selected_series = row['series']
            st.session_state.selected_author = row['author']
            st.rerun()

    st.markdown('<div style="height:2px"></div>', unsafe_allow_html=True)
