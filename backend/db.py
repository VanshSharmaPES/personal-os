import psycopg2
import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(os.getenv("NEON_DATABASE_URL"))

def add_application(company, role, notes=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO applications (company, role, notes, follow_up_date)
        VALUES (%s, %s, %s, CURRENT_DATE + INTERVAL '7 days')
        RETURNING id
    """, (company, role, notes))
    id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return id

def add_deadline(title, due_date, category='academic'):
    if isinstance(due_date, str):
        due_date = date.fromisoformat(due_date)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO deadlines (title, due_date, category)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (title, due_date, category))
    id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return id

def get_pending_applications():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, company, role, date_applied, follow_up_date
        FROM applications
        WHERE status = 'applied'
        ORDER BY follow_up_date ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_upcoming_deadlines():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, due_date, category
        FROM deadlines
        WHERE status = 'pending'
        AND due_date >= CURRENT_DATE
        ORDER BY due_date ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def update_application_status(id, status):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE applications SET status = %s WHERE id = %s
    """, (status, id))
    conn.commit()
    cur.close()
    conn.close()

def find_applications_by_company(company):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, company, role, status
        FROM applications
        WHERE LOWER(company) LIKE LOWER(%s)
        AND status NOT IN ('rejected', 'offer')
        ORDER BY created_at DESC
    """, (f'%{company}%',))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def nudge_already_sent(reference_id, reference_type, nudge_type):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM nudges_sent
        WHERE reference_id = %s
        AND reference_type = %s
        AND nudge_type = %s
    """, (reference_id, reference_type, nudge_type))
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists

def mark_nudge_sent(reference_id, reference_type, nudge_type):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO nudges_sent (reference_id, reference_type, nudge_type)
        VALUES (%s, %s, %s)
    """, (reference_id, reference_type, nudge_type))
    conn.commit()
    cur.close()
    conn.close()

def get_latest_activity():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT last_github_commit_date, last_linkedin_post_date, checked_at
        FROM activity_log
        ORDER BY checked_at DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def upsert_activity(github_date, linkedin_date):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO activity_log (last_github_commit_date, last_linkedin_post_date)
        VALUES (%s, %s)
    """, (github_date, linkedin_date))
    conn.commit()
    cur.close()
    conn.close()

def is_article_shown(link):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM shown_articles WHERE link = %s", (link,))
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists

def mark_article_shown(link):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO shown_articles (link) VALUES (%s) ON CONFLICT (link) DO NOTHING",
        (link,)
    )
    conn.commit()
    cur.close()
    conn.close()