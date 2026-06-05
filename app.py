import streamlit as st
import psycopg2
import psycopg2.extras
import requests

def get_conn():
    return psycopg2.connect(st.secrets["NEON_DATABASE_URL"], sslmode="require")

# ── Data fetchers ─────────────────────────────────────────────────────────────

def get_series_list():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COALESCE(series, booktitle) as series,
            author,
            CASE WHEN series IS NULL THEN TRUE ELSE FALSE END as is_standalone,
            COUNT(*) as total_books,
            COUNT(*) FILTER (WHERE status = 'Finished') as finished,
            COUNT(*) FILTER (WHERE status = 'DNF') as dnf,
            COUNT(*) FILTER (WHERE status = 'Abandoned') as abandoned,
            ROUND(AVG(my_rate), 1) as avg_my_rate,
            ROUND(AVG(gr_rate), 1) as avg_gr_rate,
            ROUND(AVG(expected_rate), 1) as avg_expected_rate,
            (ARRAY_AGG(cover_url ORDER BY reading_order NULLS LAST)
                FILTER (WHERE cover_url IS NOT NULL))[1] as cover_url
        FROM books
        GROUP BY COALESCE(series, booktitle), author,
                 CASE WHEN series IS NULL THEN TRUE ELSE FALSE END
        ORDER BY author, series NULLS LAST
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

def get_series_books(series, author, is_standalone):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if is_standalone:
        cur.execute("""
            SELECT * FROM books
            WHERE series IS NULL AND author = %s AND booktitle = %s
        """, (author, series))
    else:
        cur.execute("""
            SELECT * FROM books
            WHERE series = %s AND author = %s
            ORDER BY subseries NULLS FIRST, reading_order NULLS LAST, booktitle
        """, (series, author))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_author_books(author):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COALESCE(series, booktitle) as series,
            CASE WHEN series IS NULL THEN TRUE ELSE FALSE END as is_standalone,
            COUNT(*) as total_books,
            COUNT(*) FILTER (WHERE status = 'Finished') as finished,
            COUNT(*) FILTER (WHERE status = 'DNF') as dnf,
            COUNT(*) FILTER (WHERE status = 'Abandoned') as abandoned,
            ROUND(AVG(my_rate), 1) as avg_my_rate,
            ROUND(AVG(gr_rate), 1) as avg_gr_rate,
            ROUND(AVG(expected_rate), 1) as avg_expected_rate,
            (ARRAY_AGG(cover_url ORDER BY reading_order NULLS LAST)
                FILTER (WHERE cover_url IS NOT NULL))[1] as cover_url
        FROM books
        WHERE author = %s
        GROUP BY COALESCE(series, booktitle), author,
                 CASE WHEN series IS NULL THEN TRUE ELSE FALSE END
        ORDER BY series NULLS LAST
    """, (author,))
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

def fetch_cover_url(title, author):
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{requests.utils.quote(title)}+inauthor:{requests.utils.quote(author)}&maxResults=1"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            items = r.json().get('items', [])
            if items:
                img = items[0].get('volumeInfo', {}).get('imageLinks', {})
                cover = img.get('thumbnail') or img.get('smallThumbnail')
                if cover:
                    return cover.replace('http://', 'https://')
    except Exception:
        pass
    try:
        url = f"https://covers.openlibrary.org/b/title/{requests.utils.quote(title)}-L.jpg"
        r = requests.get(url, timeout=5)
        if r.status_code == 200 and len(r.content) > 1000:
            return url
    except Exception:
        pass
    return None

def fetch_author_pic(author_name):
    try:
        url = f"https://openlibrary.org/search/authors.json?q={requests.utils.quote(author_name)}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            docs = r.json().get('docs', [])
            if docs and docs[0].get('key'):
                key = docs[0]['key']
                return f"https://covers.openlibrary.org/a/id/{key}-M.jpg"
    except Exception:
        pass
    return None

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
    total     = row['total_books']
    finished  = row['finished']
    dnf       = row['dnf']
    abandoned = row['abandoned']
    if finished == total:  return 'Finished'
    if finished > 0:       return 'Part of the Series Read'
    if dnf > 0:            return 'DNF'
    if abandoned > 0:      return 'Abandoned'
    return 'TBR'

def stars(rate, max_rate=5):
    if not rate:
        return '<span style="color:#555">—</span>'
    try:
        val = float(rate)
    except ValueError:
        return '<span style="color:#555">—</span>'
        
    val = max(0.0, min(5.0, val))
    pct = val / max_rate
    if pct >= 0.8:   color = '#c9a84c'
    elif pct >= 0.6: color = '#a0c878'
    elif pct >= 0.4: color = '#e09050'
    else:            color = '#c05050'

    fill_percentage = pct * 100
    star_string = "★★★★★"
    
    return f"""
    <div style="display: inline-block; vertical-align: middle; line-height: 1;">
        <span style="
            font-family: Arial, sans-serif;
            position: relative;
            display: inline-block;
            font-size: 1.0rem;
            letter-spacing: 1px;
            background: linear-gradient(90deg, {color} {fill_percentage}%, #333 {fill_percentage}%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        ">{star_string}</span>
        <div style="color:#aaa; font-size:0.75rem; margin-top: 2px;">{val:.1f}/5</div>
    </div>
    """

def badge(status):
    color = STATUS_COLOR.get(status, '#555')
    icon  = STATUS_ICON.get(status, '📚')
    return f'<span style="background:{color}22; color:{color}; border:1px solid {color}66; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:600;">{icon} {status}</span>'

def cover_img(url, height=75):
    if url:
        return f'<img src="{url}" style="height:{height}px; width:{height*0.65:.0f}px; object-fit:cover; border-radius:4px; border:1px solid #2e2a20;">'
    return f'<div style="height:{height}px; width:{height*0.65:.0f}px; background:#1a1a1a; border-radius:4px; border:1px solid #2e2a20; display:flex; align-items:center; justify-content:center; font-size:1.2rem;">📖</div>'

# ── Global style ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="My Bookshelf", page_icon="📚", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600&family=Crimson+Pro&display=swap');
html, body, [class*="css"] { font-family: 'Crimson Pro', serif; background: #0f0f0f; color: #e8e0d0; }
h1, h2, h3 { font-family: 'Playfair Display', serif; color: #c9a84c !important; }
.series-title { font-family: 'Playfair Display', serif; font-size: 1rem; color: #c9a84c; }
.author-name  { font-size: 0.8rem; color: #7a7060; margin-top: 2px; }

div[data-testid="stHorizontalBlock"] {
    transition: background-color 0.2s ease-in-out;
    padding: 6px 8px;
    border-radius: 8px;
    align-items: center;
}
div[data-testid="stHorizontalBlock"]:hover { 
    background: rgba(201, 168, 76, 0.08) !important; 
}
.subseries-header {
    font-family: 'Playfair Display', serif;
    color: #c9a84c;
    font-size: 0.95rem;
    border-bottom: 1px solid #2e2a20;
    padding-bottom: 4px;
    margin: 18px 0 10px;
}
div[data-testid="stHorizontalBlock"] button[kind="secondary"] {
    background: none !important;
    border: none !important;
    color: #c9a84c !important;
    font-family: 'Playfair Display', serif !important;
    font-size: 1rem !important;
    padding: 0 !important;
    text-decoration: underline;
    text-underline-offset: 3px;
    text-decoration-color: #c9a84c88;
    cursor: pointer;
}
div[data-testid="stHorizontalBlock"] button[kind="secondary"]:hover {
    color: #e8c96a !important;
    text-decoration-color: #e8c96a;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

if 'selected_series'     not in st.session_state: st.session_state.selected_series     = None
if 'selected_author'     not in st.session_state: st.session_state.selected_author     = None
if 'selected_standalone' not in st.session_state: st.session_state.selected_standalone = False
if 'viewing_author'      not in st.session_state: st.session_state.viewing_author      = None
if 'editing_book'        not in st.session_state: st.session_state.editing_book        = None

# ══════════════════════════════════════════════════════════════════════════════
# AUTHOR PAGE
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.viewing_author and not st.session_state.selected_series:
    author = st.session_state.viewing_author

    if st.button("← Back to Library"):
        st.session_state.viewing_author = None
        st.rerun()

    # Author Header Banner Area with Profile Picture
    pic_col, name_col = st.columns([1, 8])
    with pic_col:
        author_pic_url = fetch_author_pic(author)
        if author_pic_url:
            st.markdown(f'<img src="{author_pic_url}" style="width:75px; height:75px; object-fit:cover; border-radius:50%; border:2px solid #c9a84c;">', unsafe_allow_html=True)
        else:
            st.markdown('<div style="width:75px; height:75px; background:#222; border-radius:50%; border:2px solid #7a7060; display:flex; align-items:center; justify-content:center; font-size:1.5rem;">✍️</div>', unsafe_allow_html=True)
    with name_col:
        st.markdown(f"<h2 style='margin:0;'>{author}</h2>", unsafe_allow_html=True)
    st.divider()

    rows = get_author_books(author)

    h1, h2, h3, h4, h5, h6, h7 = st.columns([1.0, 3.5, 1.5, 2, 1.5, 1.5, 1.5])
    for col, label in zip([h1,h2,h3,h4,h5,h6,h7], ["Cover", "Title / Series", "Saga", "Reading Status", "My Rating", "GR Rating", "Expected"]):
        col.markdown(f"<small style='color:#7a7060;'>{label}</small>", unsafe_allow_html=True)
    st.divider()

    for row in rows:
        status = compute_status(row)
        c1, c2, c3, c4, c5, c6, c7 = st.columns([1.0, 3.5, 1.5, 2, 1.5, 1.5, 1.5])

        with c1:
            st.markdown(cover_img(row.get('cover_url'), height=75), unsafe_allow_html=True)

        with c2:
            if st.button(row['series'], key=f"auth_open_{row['series']}", use_container_width=False):
                st.session_state.selected_series     = row['series']
                st.session_state.selected_author     = author
                st.session_state.selected_standalone = bool(row['is_standalone'])
                st.rerun()
            st.markdown(f"<div class='author-name' style='margin-top:-8px;'>{row['total_books']} book{'s' if row['total_books']>1 else ''}</div>", unsafe_allow_html=True)

        with c3:
            if row['is_standalone']:
                st.markdown('<span style="background:#1a2a3a; color:#6fb3f7; border:1px solid #2a4a7a66; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:600;">📄 Standalone</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span style="background:#1a3a25; color:#6fcf97; border:1px solid #4a7c5966; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:600;">✅ Series</span>', unsafe_allow_html=True)

        with c4:
            st.markdown(badge(status), unsafe_allow_html=True)

        with c5:
            st.markdown(stars(row['avg_my_rate']), unsafe_allow_html=True)

        with c6:
            st.markdown(stars(row['avg_gr_rate']), unsafe_allow_html=True)

        with c7:
            st.markdown(stars(row['avg_expected_rate']), unsafe_allow_html=True)

        st.markdown('<div style="height:2px"></div>', unsafe_allow_html=True)

    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# DETAIL PAGE
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.selected_series:
    series        = st.session_state.selected_series
    author        = st.session_state.selected_author
    is_standalone = st.session_state.selected_standalone

    if st.button("← Back"):
        st.session_state.selected_series     = None
        st.session_state.selected_author     = None
        st.session_state.selected_standalone = False
        st.session_state.editing_book        = None
        st.rerun()

    st.markdown(f"## {series}")
    if st.button(author, key="author_link"):
        st.session_state.selected_series     = None
        st.session_state.selected_standalone = False
        st.session_state.editing_book        = None
        st.session_state.viewing_author      = author
        st.rerun()

    st.divider()

    books = get_series_books(series, author, is_standalone)

    cover_urls = [b['cover_url'] for b in books if b.get('cover_url')]
    if cover_urls:
        st.markdown(f'<img src="{cover_urls[0]}" style="height:180px; border-radius:8px; border:1px solid #2e2a20; margin-bottom:16px;">', unsafe_allow_html=True)

    # 3 Ratings Layout inside Detail view
    hc0, hc1, hc2, hc3, hc4, hc5, hc6, hc7 = st.columns([0.5, 1.0, 3.5, 2, 1.2, 1.2, 1.2, 0.6])
    for col, label in zip([hc0,hc1,hc2,hc3,hc4,hc5,hc6,hc7], ["#", "Cover", "Title", "Reading Status", "My Rating", "GR Rating", "Expected", ""]):
        col.markdown(f"<small style='color:#7a7060;'>{label}</small>", unsafe_allow_html=True)
    st.divider()

    groups = {}
    for b in books:
        key = b['subseries'] or '—'
        groups.setdefault(key, []).append(b)

    for group_name, group_books in groups.items():
        if len(groups) > 1:
            label = group_name if group_name != '—' else 'Main Series'
            st.markdown(f'<div class="subseries-header">📂 {label}</div>', unsafe_allow_html=True)

        for book in group_books:
            book_id    = book['id']
            is_editing = st.session_state.editing_book == book_id

            with st.container():
                if not is_editing:
                    c0, c1, c2, c3, c4, c5, c6, c7 = st.columns([0.5, 1.0, 3.5, 2, 1.2, 1.2, 1.2, 0.6])
                    order_str = str(int(book['reading_order'])) if book['reading_order'] else "—"
                    c0.markdown(f"<div style='color:#7a7060; font-size:0.85rem;'>{order_str}</div>", unsafe_allow_html=True)

                    with c1:
                        st.markdown(cover_img(book.get('cover_url'), height=75), unsafe_allow_html=True)

                    c2.markdown(f"<div class='series-title'>{book['booktitle']}</div>", unsafe_allow_html=True)
                    c3.markdown(f"<div>{badge(book['status'] or 'TBR')}</div>", unsafe_allow_html=True)
                    c4.markdown(stars(book['my_rate']), unsafe_allow_html=True)
                    c5.markdown(stars(book['gr_rate']), unsafe_allow_html=True)
                    c6.markdown(stars(book['expected_rate']), unsafe_allow_html=True)
                    
                    with c7:
                        if st.button("✏️", key=f"edit_{book_id}"):
                            st.session_state.editing_book = book_id
                            st.rerun()

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
                    new_my_rate  = col_g.number_input("My Rating",      0.0, 5.0, float(book['my_rate'] or 0),       0.1, key=f"my_{book_id}")
                    new_gr_rate  = col_h.number_input("GR Rating",      0.0, 5.0, float(book['gr_rate'] or 0),       0.1, key=f"gr_{book_id}")
                    new_exp_rate = col_i.number_input("Expected Rating", 0.0, 5.0, float(book['expected_rate'] or 0), 0.1, key=f"exp_{book_id}")

                    new_pros    = st.text_input("Pros",    value=book['pros'] or '',       key=f"pros_{book_id}")
                    new_cons    = st.text_input("Cons",    value=book['cons'] or '',       key=f"cons_{book_id}")
                    new_comment = st.text_area("Comment",  value=book['my_comment'] or '', key=f"comment_{book_id}")

                    st.markdown("**Cover**")
                    cov1, cov2 = st.columns([3, 1])
                    new_cover_url = cov1.text_input("Cover URL", value=book.get('cover_url') or '', key=f"cover_{book_id}")
                    if cov2.button("🌐 Auto-fetch", key=f"fetch_{book_id}"):
                        fetched = fetch_cover_url(book['booktitle'], book['author'])
                        if fetched:
                            update_book(book_id, {'cover_url': fetched})
                            st.success("✅ Cover fetched!")
                            st.rerun()
                        else:
                            st.warning("No cover found.")
                    if new_cover_url:
                        st.markdown(cover_img(new_cover_url, height=120), unsafe_allow_html=True)

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
                            'cover_url':     new_cover_url or None,
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
search        = col_search.text_input("Search", placeholder="🔍  Search by title, series or author…", label_visibility="collapsed")
status_filter = col_filter.selectbox("Reading Status", ["All"] + STATUSES, label_visibility="collapsed")
sort_by       = col_sort.selectbox("Sort by", ["Title / Series A-Z", "Author", "GR Rating ↓", "Expected Rating ↓"], label_visibility="collapsed")

series_list = get_series_list()

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

if sort_by == "Title / Series A-Z":
    filtered.sort(key=lambda r: r['series'].lower())
elif sort_by == "Author":
    filtered.sort(key=lambda r: (r['author'].lower(), r['series'].lower()))
elif sort_by == "GR Rating ↓":
    filtered.sort(key=lambda r: r['avg_gr_rate'] or 0, reverse=True)
elif sort_by == "Expected Rating ↓":
    filtered.sort(key=lambda r: r['avg_expected_rate'] or 0, reverse=True)

st.markdown(f"<p style='color:#7a7060; font-size:0.85rem;'>{len(filtered)} entries</p>", unsafe_allow_html=True)

# Main Library columns adjust based on status filter selection
show_my_rating = (status_filter == "Finished")

if show_my_rating:
    columns_spec = [1.0, 3.5, 1.5, 2, 1.4, 1.4, 1.4]
    headers_spec = ["Cover", "Title / Series", "Saga", "Reading Status", "My Rating", "GR Rating", "Expected Rating"]
else:
    columns_spec = [1.0, 4, 2, 2, 2, 2]
    headers_spec = ["Cover", "Title / Series", "Saga", "Reading Status", "Goodreads Rating", "Expected Rating"]

h_cols = st.columns(columns_spec)
for col, label in zip(h_cols, headers_spec):
    col.markdown(f"<small style='color:#7a7060;'>{label}</small>", unsafe_allow_html=True)
st.divider()

for row in filtered:
    row_cols = st.columns(columns_spec)

    with row_cols[0]:
        st.markdown(cover_img(row.get('cover_url'), height=75), unsafe_allow_html=True)

    with row_cols[1]:
        if st.button(row['series'], key=f"open_{row['series']}_{row['author']}", use_container_width=False):
            st.session_state.selected_series     = row['series']
            st.session_state.selected_author     = row['author']
            st.session_state.selected_standalone = bool(row['is_standalone'])
            st.rerun()
        st.markdown(f"<div class='author-name' style='margin-top:-8px;'>{row['author']}</div>", unsafe_allow_html=True)

    with row_cols[2]:
        if row['is_standalone']:
            st.markdown('<span style="background:#1a2a3a; color:#6fb3f7; border:1px solid #2a4a7a66; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:600;">📄 Standalone</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span style="background:#1a3a25; color:#6fcf97; border:1px solid #4a7c5966; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:600;">✅ Series</span>', unsafe_allow_html=True)

    with row_cols[3]:
        st.markdown(badge(row['status']), unsafe_allow_html=True)

    if show_my_rating:
        with row_cols[4]: st.markdown(stars(row['avg_my_rate']), unsafe_allow_html=True)
        with row_cols[5]: st.markdown(stars(row['avg_gr_rate']), unsafe_allow_html=True)
        with row_cols[6]: st.markdown(stars(row['avg_expected_rate']), unsafe_allow_html=True)
    else:
        with row_cols[4]: st.markdown(stars(row['avg_gr_rate']), unsafe_allow_html=True)
        with row_cols[5]: st.markdown(stars(row['avg_expected_rate']), unsafe_allow_html=True)

    st.markdown('<div style="height:2px"></div>', unsafe_allow_html=True)
