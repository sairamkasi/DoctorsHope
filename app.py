from flask import Flask, request, redirect, url_for, session, jsonify, render_template
import psycopg2  # pip install psycopg2
import uuid
import random
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pandas as pd
from twilio.rest import Client

app = Flask(__name__)
app.secret_key = "your_secret_key"  # REQUIRED for session handling

# DATABASE CONFIGURATION
DB_HOST = "localhost"
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASSWORD = "Ram@6688"

# ---------------------- DB CONNECTION ----------------------
def get_database_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

# ---------------------- CREATE TABLES ----------------------
def create_patient_table_if_not_exists():
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patient(
            id SERIAL PRIMARY KEY,
            UserName VARCHAR(100) NOT NULL,
            date_of_birth DATE NOT NULL,
            Email VARCHAR(150) NOT NULL UNIQUE,
            Password VARCHAR(150) NOT NULL,
            Number VARCHAR(15) NOT NULL
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

def create_doctor_table_if_not_exists():
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctor(
            id SERIAL PRIMARY KEY,
            UserName VARCHAR(100) NOT NULL,
            date_of_birth DATE NOT NULL,
            Email VARCHAR(150) NOT NULL UNIQUE,
            Password VARCHAR(150) NOT NULL,
            Number VARCHAR(15) NOT NULL
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

def create_admin_table_if_not_exists():
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin(
            id SERIAL PRIMARY KEY,
            UserName VARCHAR(100) NOT NULL,
            Password VARCHAR(150) NOT NULL
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

def create_appointment_table_if_not_exists():
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS appointment(
            id SERIAL PRIMARY KEY,
            first_name VARCHAR(100),
            second_name VARCHAR(100),
            date_of_birth DATE,
            gender VARCHAR(10),
            email VARCHAR(150),
            password VARCHAR(150),
            contact VARCHAR(15),
            time VARCHAR(50),
            emergency BOOLEAN DEFAULT FALSE,
            queue_number VARCHAR(10)  -- changed: was INTEGER, now VARCHAR
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

# Run table creation
create_patient_table_if_not_exists()
create_doctor_table_if_not_exists()
create_admin_table_if_not_exists()
create_appointment_table_if_not_exists()

# (Optional) A helper route to alter existing column if needed
@app.route("/_migrate_queue_number")
def migrate_queue_number():
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        cursor.execute("""
            ALTER TABLE appointment
            ALTER COLUMN queue_number TYPE VARCHAR(10)
            USING queue_number::VARCHAR;
        """)
        connection.commit()
        cursor.close()
        connection.close()
        return "Migration success: queue_number is now VARCHAR(10)"
    except Exception as e:
        return f"Migration failed: {e}", 500

# ---------------------- ROUTES ----------------------

@app.route("/Doctors_Hope")
def welcome():
    return render_template('welcome.html')

# ---------- HOME ----------
@app.route("/home")
def home():
    if "UserName" in session:
        return render_template("home.html", username=session["UserName"])
    return redirect(url_for("login"))

# keep imports ONCE at the top

@app.route("/docregister", methods=["GET", "POST"])
def docregister():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        # Save doctor to DB
        connection = get_database_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO doctor(UserName, date_of_birth, Email, Password, Number)
                VALUES (%s, %s, %s, %s, %s);
            """, (username, "1970-01-01", f"{username}@example.com", password, "0000000000"))
            connection.commit()
        except Exception as e:
            connection.rollback()
            print("Doctor Register Error:", e)
        finally:
            cursor.close()
            connection.close()

        return redirect(url_for("doclogin"))

    return render_template("docregister.html")


# ---------- appointment ----------
@app.route("/appointment", methods=["GET", "POST"])
def appointment():
    # Twilio credentials (replace with your own)
    TWILIO_ACCOUNT_SID = 'your_account_sid'
    TWILIO_AUTH_TOKEN = 'your_auth_token'
    TWILIO_PHONE_NUMBER = '+1234567890'  # Your Twilio phone number

    def send_sms(to_number, message):
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=to_number
        )

    if request.method == "POST":
        data = {
            "first_name": request.form.get("First_Name"),
            "second_name": request.form.get("Second_Name"),
            "dob": request.form.get("date_of_birth"),
            "gender": request.form.get("Gender"),
            "email": request.form.get("email"),
            "contact": request.form.get("Contact_Number"),
            "time": request.form.get("Time"),
            "emergency": True if request.form.get("emergency") == "on" else False
        }

        # Use today’s date or maybe the requested date — you used date_of_birth field wrongly?
        # In your original you used date_of_birth for appointment date — confusing.
        # Probably you meant a different column for appointment_date. But I keep your logic.
        today = datetime.date.today()

        connection = get_database_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT queue_number, emergency
            FROM appointment
            WHERE time = %s AND date_of_birth = %s
            ORDER BY emergency DESC, queue_number ASC
        """, (data["time"], today))
        existing = cursor.fetchall()

        def next_token(existing_tokens):
            used = set(str(q) for q, _ in existing_tokens)
            for letter in range(ord('A'), ord('Z')+1):
                for num in range(1, 10):
                    candidate = f"{chr(letter)}{num}"
                    if candidate not in used:
                        return candidate
            return str(uuid.uuid4())[:5]

        if data["emergency"]:
            queue_number = next_token(existing)
        else:
            non_emergency = [(q, e) for q, e in existing if e == False]
            used = set(str(q) for q, _ in non_emergency)
            found = None
            for letter in range(ord('A'), ord('Z')+1):
                for num in range(1, 10):
                    candidate = f"{chr(letter)}{num}"
                    if candidate not in used:
                        found = candidate
                        break
                if found:
                    break
            if found:
                queue_number = found
            else:
                queue_number = str(uuid.uuid4())[:5]

        try:
            cursor.execute("""
                INSERT INTO appointment(first_name, second_name, date_of_birth, gender, email, contact, time, emergency, queue_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data["first_name"], data["second_name"], data["dob"],
                data["gender"], data["email"], data["contact"],
                data["time"], data["emergency"], queue_number
            ))
            connection.commit()
        except Exception as e:
            connection.rollback()
            cursor.close()
            connection.close()
            print("Database Insert Error:", e)
            return render_template("appointment.html", error="Failed to book appointment due to DB error", username=session.get("UserName"))

        cursor.close()
        connection.close()

        token = queue_number
        try:
            appt_time = datetime.datetime.strptime(data["time"], "%H:%M").strftime("%I:%M %p")
        except Exception:
            appt_time = data["time"]

        # Send confirmation email
        sender_email = "doctorshope.2025@gmail.com"
        sender_password = "zqti jvbp kclt jbba"
        receiver_email = data["email"]
        subject = "Doctor's Hope Appointment Confirmation"
        body = f"""
        <h2 style='color:#0072ff;'>Doctor's Hope - Appointment Confirmed!</h2>
        <p>Dear {data['first_name']} {data['second_name']},</p>
        <p>Your appointment slot has been <b>successfully booked</b>.</p>
        <p><b>Token Number:</b> <span style='color:#0072ff;font-size:18px;'>{token}</span></p>
        <p><b>Appointment Time:</b> <span style='color:#0072ff;'>{appt_time}</span></p>
        <p><b>Emergency:</b> {'Yes' if data['emergency'] else 'No'}</p>
        <hr>
        <p>Thank you for choosing <b style='color:#0072ff;'>Doctor's Hope</b>.<br>
        Visit our website for more info: <a href='http://yourwebsite.com' style='color:#0072ff;'>Doctor's Hope</a></p>
        """
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
            server.quit()
        except Exception as e:
            print("Email send error:", e)

        # Optionally send SMS
        try:
            sms_message = (
                f"Doctor's Hope: Your appointment is booked!\n"
                f"Token: {token}\n"
                f"Time: {appt_time}\n"
                f"Thank you for choosing Doctor's Hope."
            )
            send_sms(data["contact"], sms_message)
        except Exception as e:
            print("SMS send error:", e)

        success_message = f"Appointment booked successfully! Your token number is {token}."
        return render_template("appointment.html", success=success_message, username=session.get("UserName"))

    if "UserName" in session:
        return render_template("appointment.html", username=session["UserName"])
    return redirect(url_for("home"))

# ---------- profile ----------
@app.route("/profile")
def profile():
    if "UserName" in session:
        return render_template("profile.html", username=session["UserName"])
    return redirect(url_for("home"))

# ---------- about ----------
@app.route("/about")
def about():
    if "UserName" in session:
        return render_template("about.html", username=session["UserName"])
    return redirect(url_for("home"))

# ---------- contact ----------
@app.route("/contact", methods=["GET", "POST"])
def contact():
    success = error = None
    username = session.get("UserName")
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        mobile = request.form.get("mobile")
        message = request.form.get("message")
        try:
            sender_email = email
            receiver_email = "doctorshope.2025@gmail.com"
            subject = f"Contact Us Message from {name} ({email})"
            body = f"Name: {name}\nEmail: {email}\nMobile: {mobile}\nMessage:\n{message}"
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = receiver_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login('doctorshope.2025@gmail.com', 'zqti jvbp kclt jbba')
            server.sendmail(sender_email, receiver_email, msg.as_string())
            server.quit()
            success = "Your message has been sent successfully!"
        except Exception as e:
            print("Contact send error:", e)
            error = "Failed to send message. Please try again later."
    return render_template("contact.html", success=success, error=error, username=username)

# ---------- specialist ----------
@app.route("/specialist")
def specialist():
    if "UserName" in session:
        return render_template("specialist.html", username=session["UserName"])
    return redirect(url_for("home"))

# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("UserName")
        password = request.form.get("Password")
        connection = get_database_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM patient WHERE UserName = %s AND Password = %s;", (username, password))
        user = cursor.fetchone()
        cursor.close()
        connection.close()
        if user:
            session["UserName"] = username
            return redirect(url_for("home"))
        else:
            error = "Invalid username or password!"
    return render_template("login.html", error=error)

# ---------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        UserName = request.form.get('UserName').strip()
        date_of_birth = request.form.get('date_of_birth').strip()
        Email = request.form.get('Email').strip()
        Password = request.form.get('Password').strip()
        Number = request.form.get('Number').strip()
        connection = get_database_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO patient(UserName, date_of_birth, Email, Password, Number)
                VALUES (%s, %s, %s, %s, %s);
            """, (UserName, date_of_birth, Email, Password, Number))
            connection.commit()
            cursor.close()
            connection.close()
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            connection.rollback()
            error = "Email already exists"
        except Exception as err:
            connection.rollback()
            error = f"Database error: {err}"
        finally:
            cursor.close()
            connection.close()
    return render_template('register.html', error=error)

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------------- DASHBOARD ----------------------
@app.route("/adminlogin", methods=["GET", "POST"])
def adminlogin():
    error = None
    if request.method == "POST":
        username = request.form.get("UserName")
        password = request.form.get("Password")
        connection = get_database_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM admin WHERE UserName = %s AND Password = %s;", (username, password))
        admin = cursor.fetchone()
        cursor.close()
        connection.close()
        if admin:
            session["AdminName"] = username
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid username or password!"
    return render_template("adminlogin.html", error=error)

@app.route("/doclogin", methods=["GET", "POST"])
def doclogin():
    error = None
    if request.method == "POST":
        email = request.form.get("Email")
        password = request.form.get("Password")
        connection = get_database_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM doctor WHERE Email = %s AND Password = %s;", (email, password))
        doctor = cursor.fetchone()
        cursor.close()
        connection.close()
        if doctor:
            session["DoctorName"] = doctor[1]
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid email or password!"
    return render_template("doclogin.html", error=error)

@app.route("/dashboard")
def dashboard():
    if "UserName" not in session:
        return redirect(url_for("login"))

    connection = get_database_connection()

    df_patients = pd.read_sql("SELECT date_of_birth FROM patient;", connection)
    if not df_patients.empty:
        df_patients['year'] = pd.to_datetime(df_patients['date_of_birth']).dt.year
        patient_counts = df_patients['year'].value_counts().sort_index()
    else:
        patient_counts = pd.Series(dtype=int)

    df_doctors = pd.read_sql("SELECT date_of_birth FROM doctor;", connection)
    if not df_doctors.empty:
        df_doctors['year'] = pd.to_datetime(df_doctors['date_of_birth']).dt.year
        doctor_counts = df_doctors['year'].value_counts().sort_index()
    else:
        doctor_counts = pd.Series(dtype=int)

    df_appts = pd.read_sql("SELECT gender, time FROM appointment;", connection)
    appointment_times = df_appts['time'].value_counts() if not df_appts.empty else pd.Series(dtype=int)
    appointment_genders = df_appts['gender'].value_counts() if not df_appts.empty else pd.Series(dtype=int)

    connection.close()

    return render_template(
        "dashboard.html",
        username=session["UserName"],
        patient_labels=list(patient_counts.index),
        patient_data=list(patient_counts.values),
        doctor_labels=list(doctor_counts.index),
        doctor_data=list(doctor_counts.values),
        appt_time_labels=list(appointment_times.index),
        appt_time_data=list(appointment_times.values),
        appt_gender_labels=list(appointment_genders.index),
        appt_gender_data=list(appointment_genders.values),
    )

@app.route("/visualization")
def visualization():
    if "UserName" not in session:
        return redirect(url_for("login"))

    connection = get_database_connection()

    df_patients = pd.read_sql("SELECT date_of_birth FROM patient;", connection)
    if not df_patients.empty:
        df_patients['year'] = pd.to_datetime(df_patients['date_of_birth']).dt.year
        patient_counts = df_patients['year'].value_counts().sort_index()
    else:
        patient_counts = pd.Series(dtype=int)

    df_doctors = pd.read_sql("SELECT date_of_birth FROM doctor;", connection)
    if not df_doctors.empty:
        df_doctors['year'] = pd.to_datetime(df_doctors['date_of_birth']).dt.year
        doctor_counts = df_doctors['year'].value_counts().sort_index()
    else:
        doctor_counts = pd.Series(dtype=int)

    df_appts = pd.read_sql("SELECT gender, time FROM appointment;", connection)
    appointment_times = df_appts['time'].value_counts() if not df_appts.empty else pd.Series(dtype=int)
    appointment_genders = df_appts['gender'].value_counts() if not df_appts.empty else pd.Series(dtype=int)

    connection.close()

    return render_template(
        "visualization.html",
        username=session["UserName"],
        patient_labels=[str(x) for x in patient_counts.index],
        patient_data=[int(x) for x in patient_counts.values],
        doctor_labels=[str(x) for x in doctor_counts.index],
        doctor_data=[int(x) for x in doctor_counts.values],
        appt_time_labels=[str(x) for x in appointment_times.index],
        appt_time_data=[int(x) for x in appointment_times.values],
        appt_gender_labels=[str(x) for x in appointment_genders.index],
        appt_gender_data=[int(x) for x in appointment_genders.values],
    )

@app.route("/adddoctr")
def adddoctr():
    if "UserName" in session:
        return render_template("adddoctr.html", username=session["UserName"])
    return redirect(url_for("login"))

@app.route("/patients")
def patients():
    if "UserName" not in session:
        return redirect(url_for("login"))
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT first_name, second_name, date_of_birth, gender, email, contact, time, emergency, queue_number
        FROM appointment;
    """)
    rows = cursor.fetchall()
    cursor.close()
    connection.close()
    patients = []
    for row in rows:
        patients.append({
            "first_name": row[0],
            "second_name": row[1],
            "date_of_birth": row[2],
            "gender": row[3],
            "email": row[4],
            "contact": row[5],
            "time": row[6],
            "emergency": row[7],
            "queue_number": row[8],
        })
    return render_template("patients.html", patients=patients, username=session["UserName"])

# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    app.run(debug=True, port=5005, host="0.0.0.0")
from flask import Flask, request, redirect, url_for, session, jsonify, render_template
import psycopg2  # pip install psycopg2
import uuid
import random
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pandas as pd
from twilio.rest import Client

app = Flask(__name__)
app.secret_key = "your_secret_key"  # REQUIRED for session handling

# DATABASE CONFIGURATION
DB_HOST = "localhost"
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASSWORD = "Ram@6688"

# ---------------------- DB CONNECTION ----------------------
def get_database_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

# ---------------------- CREATE TABLES ----------------------
def create_patient_table_if_not_exists():
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patient(
            id SERIAL PRIMARY KEY,
            UserName VARCHAR(100) NOT NULL,
            date_of_birth DATE NOT NULL,
            Email VARCHAR(150) NOT NULL UNIQUE,
            Password VARCHAR(150) NOT NULL,
            Number VARCHAR(15) NOT NULL
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

def create_doctor_table_if_not_exists():
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctor(
            id SERIAL PRIMARY KEY,
            UserName VARCHAR(100) NOT NULL,
            date_of_birth DATE NOT NULL,
            Email VARCHAR(150) NOT NULL UNIQUE,
            Password VARCHAR(150) NOT NULL,
            Number VARCHAR(15) NOT NULL
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

def create_admin_table_if_not_exists():
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin(
            id SERIAL PRIMARY KEY,
            UserName VARCHAR(100) NOT NULL,
            Password VARCHAR(150) NOT NULL
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

def create_appointment_table_if_not_exists():
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS appointment(
            id SERIAL PRIMARY KEY,
            first_name VARCHAR(100),
            second_name VARCHAR(100),
            date_of_birth DATE,
            gender VARCHAR(10),
            email VARCHAR(150),
            password VARCHAR(150),
            contact VARCHAR(15),
            time VARCHAR(50),
            emergency BOOLEAN DEFAULT FALSE,
            queue_number VARCHAR(10)  -- changed: was INTEGER, now VARCHAR
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

# Run table creation
create_patient_table_if_not_exists()
create_doctor_table_if_not_exists()
create_admin_table_if_not_exists()
create_appointment_table_if_not_exists()

# (Optional) A helper route to alter existing column if needed
@app.route("/_migrate_queue_number")
def migrate_queue_number():
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        cursor.execute("""
            ALTER TABLE appointment
            ALTER COLUMN queue_number TYPE VARCHAR(10)
            USING queue_number::VARCHAR;
        """)
        connection.commit()
        cursor.close()
        connection.close()
        return "Migration success: queue_number is now VARCHAR(10)"
    except Exception as e:
        return f"Migration failed: {e}", 500

# ---------------------- ROUTES ----------------------

@app.route("/Doctors_Hope")
def welcome():
    return render_template('welcome.html')

# ---------- HOME ----------
@app.route("/home")
def home():
    if "UserName" in session:
        return render_template("home.html", username=session["UserName"])
    return redirect(url_for("login"))

# ---------- appointment ----------
@app.route("/appointment", methods=["GET", "POST"])
def appointment():
    # Twilio credentials (replace with your own)
    TWILIO_ACCOUNT_SID = 'your_account_sid'
    TWILIO_AUTH_TOKEN = 'your_auth_token'
    TWILIO_PHONE_NUMBER = '+1234567890'  # Your Twilio phone number

    def send_sms(to_number, message):
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=to_number
        )

    if request.method == "POST":
        data = {
            "first_name": request.form.get("First_Name"),
            "second_name": request.form.get("Second_Name"),
            "dob": request.form.get("date_of_birth"),
            "gender": request.form.get("Gender"),
            "email": request.form.get("email"),
            "contact": request.form.get("Contact_Number"),
            "time": request.form.get("Time"),
            "emergency": True if request.form.get("emergency") == "on" else False
        }

        # Use today’s date or maybe the requested date — you used date_of_birth field wrongly?
        # In your original you used date_of_birth for appointment date — confusing.
        # Probably you meant a different column for appointment_date. But I keep your logic.
        today = datetime.date.today()

        connection = get_database_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT queue_number, emergency
            FROM appointment
            WHERE time = %s AND date_of_birth = %s
            ORDER BY emergency DESC, queue_number ASC
        """, (data["time"], today))
        existing = cursor.fetchall()

        def next_token(existing_tokens):
            used = set(str(q) for q, _ in existing_tokens)
            for letter in range(ord('A'), ord('Z')+1):
                for num in range(1, 10):
                    candidate = f"{chr(letter)}{num}"
                    if candidate not in used:
                        return candidate
            return str(uuid.uuid4())[:5]

        if data["emergency"]:
            queue_number = next_token(existing)
        else:
            non_emergency = [(q, e) for q, e in existing if e == False]
            used = set(str(q) for q, _ in non_emergency)
            found = None
            for letter in range(ord('A'), ord('Z')+1):
                for num in range(1, 10):
                    candidate = f"{chr(letter)}{num}"
                    if candidate not in used:
                        found = candidate
                        break
                if found:
                    break
            if found:
                queue_number = found
            else:
                queue_number = str(uuid.uuid4())[:5]

        try:
            cursor.execute("""
                INSERT INTO appointment(first_name, second_name, date_of_birth, gender, email, contact, time, emergency, queue_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data["first_name"], data["second_name"], data["dob"],
                data["gender"], data["email"], data["contact"],
                data["time"], data["emergency"], queue_number
            ))
            connection.commit()
        except Exception as e:
            connection.rollback()
            cursor.close()
            connection.close()
            print("Database Insert Error:", e)
            return render_template("appointment.html", error="Failed to book appointment due to DB error", username=session.get("UserName"))

        cursor.close()
        connection.close()

        token = queue_number
        try:
            appt_time = datetime.datetime.strptime(data["time"], "%H:%M").strftime("%I:%M %p")
        except Exception:
            appt_time = data["time"]

        # Send confirmation email
        sender_email = "doctorshope.2025@gmail.com"
        sender_password = "zqti jvbp kclt jbba"
        receiver_email = data["email"]
        subject = "Doctor's Hope Appointment Confirmation"
        body = f"""
        <h2 style='color:#0072ff;'>Doctor's Hope - Appointment Confirmed!</h2>
        <p>Dear {data['first_name']} {data['second_name']},</p>
        <p>Your appointment slot has been <b>successfully booked</b>.</p>
        <p><b>Token Number:</b> <span style='color:#0072ff;font-size:18px;'>{token}</span></p>
        <p><b>Appointment Time:</b> <span style='color:#0072ff;'>{appt_time}</span></p>
        <p><b>Emergency:</b> {'Yes' if data['emergency'] else 'No'}</p>
        <hr>
        <p>Thank you for choosing <b style='color:#0072ff;'>Doctor's Hope</b>.<br>
        Visit our website for more info: <a href='http://yourwebsite.com' style='color:#0072ff;'>Doctor's Hope</a></p>
        """
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
            server.quit()
        except Exception as e:
            print("Email send error:", e)

        # Optionally send SMS
        try:
            sms_message = (
                f"Doctor's Hope: Your appointment is booked!\n"
                f"Token: {token}\n"
                f"Time: {appt_time}\n"
                f"Thank you for choosing Doctor's Hope."
            )
            send_sms(data["contact"], sms_message)
        except Exception as e:
            print("SMS send error:", e)

        success_message = f"Appointment booked successfully! Your token number is {token}."
        return render_template("appointment.html", success=success_message, username=session.get("UserName"))

    if "UserName" in session:
        return render_template("appointment.html", username=session["UserName"])
    return redirect(url_for("home"))

# ---------- profile ----------
@app.route("/profile")
def profile():
    if "UserName" in session:
        return render_template("profile.html", username=session["UserName"])
    return redirect(url_for("home"))

# ---------- about ----------
@app.route("/about")
def about():
    if "UserName" in session:
        return render_template("about.html", username=session["UserName"])
    return redirect(url_for("home"))

@app.route("/docregister", methods=["GET", "POST"])
def docregister():
    if request.method == "POST":
        # Example doctor registration logic
        username = request.form.get("username")
        password = request.form.get("password")
        # save to database...
        return redirect(url_for("doclogin"))

    return render_template("docregister.html")


# ---------- contact ----------
@app.route("/contact", methods=["GET", "POST"])
def contact():
    success = error = None
    username = session.get("UserName")
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        mobile = request.form.get("mobile")
        message = request.form.get("message")
        try:
            sender_email = email
            receiver_email = "doctorshope.2025@gmail.com"
            subject = f"Contact Us Message from {name} ({email})"
            body = f"Name: {name}\nEmail: {email}\nMobile: {mobile}\nMessage:\n{message}"
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = receiver_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login('doctorshope.2025@gmail.com', 'zqti jvbp kclt jbba')
            server.sendmail(sender_email, receiver_email, msg.as_string())
            server.quit()
            success = "Your message has been sent successfully!"
        except Exception as e:
            print("Contact send error:", e)
            error = "Failed to send message. Please try again later."
    return render_template("contact.html", success=success, error=error, username=username)

# ---------- specialist ----------
@app.route("/specialist")
def specialist():
    if "UserName" in session:
        return render_template("specialist.html", username=session["UserName"])
    return redirect(url_for("home"))

# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("UserName")
        password = request.form.get("Password")
        connection = get_database_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM patient WHERE UserName = %s AND Password = %s;", (username, password))
        user = cursor.fetchone()
        cursor.close()
        connection.close()
        if user:
            session["UserName"] = username
            return redirect(url_for("home"))
        else:
            error = "Invalid username or password!"
    return render_template("login.html", error=error)

# ---------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        UserName = request.form.get('UserName').strip()
        date_of_birth = request.form.get('date_of_birth').strip()
        Email = request.form.get('Email').strip()
        Password = request.form.get('Password').strip()
        Number = request.form.get('Number').strip()
        connection = get_database_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                INSERT INTO patient(UserName, date_of_birth, Email, Password, Number)
                VALUES (%s, %s, %s, %s, %s);
            """, (UserName, date_of_birth, Email, Password, Number))
            connection.commit()
            cursor.close()
            connection.close()
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            connection.rollback()
            error = "Email already exists"
        except Exception as err:
            connection.rollback()
            error = f"Database error: {err}"
        finally:
            cursor.close()
            connection.close()
    return render_template('register.html', error=error)

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------------- DASHBOARD ----------------------
@app.route("/adminlogin", methods=["GET", "POST"])
def adminlogin():
    error = None
    if request.method == "POST":
        username = request.form.get("UserName")
        password = request.form.get("Password")
        connection = get_database_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM admin WHERE UserName = %s AND Password = %s;", (username, password))
        admin = cursor.fetchone()
        cursor.close()
        connection.close()
        if admin:
            session["AdminName"] = username
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid username or password!"
    return render_template("adminlogin.html", error=error)

@app.route("/doclogin", methods=["GET", "POST"])
def doclogin():
    error = None
    if request.method == "POST":
        email = request.form.get("Email")
        password = request.form.get("Password")
        connection = get_database_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM doctor WHERE Email = %s AND Password = %s;", (email, password))
        doctor = cursor.fetchone()
        cursor.close()
        connection.close()
        if doctor:
            session["DoctorName"] = doctor[1]
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid email or password!"
    return render_template("doclogin.html", error=error)

@app.route("/dashboard")
def dashboard():
    if "UserName" not in session:
        return redirect(url_for("login"))

    connection = get_database_connection()

    df_patients = pd.read_sql("SELECT date_of_birth FROM patient;", connection)
    if not df_patients.empty:
        df_patients['year'] = pd.to_datetime(df_patients['date_of_birth']).dt.year
        patient_counts = df_patients['year'].value_counts().sort_index()
    else:
        patient_counts = pd.Series(dtype=int)

    df_doctors = pd.read_sql("SELECT date_of_birth FROM doctor;", connection)
    if not df_doctors.empty:
        df_doctors['year'] = pd.to_datetime(df_doctors['date_of_birth']).dt.year
        doctor_counts = df_doctors['year'].value_counts().sort_index()
    else:
        doctor_counts = pd.Series(dtype=int)

    df_appts = pd.read_sql("SELECT gender, time FROM appointment;", connection)
    appointment_times = df_appts['time'].value_counts() if not df_appts.empty else pd.Series(dtype=int)
    appointment_genders = df_appts['gender'].value_counts() if not df_appts.empty else pd.Series(dtype=int)

    connection.close()

    return render_template(
        "dashboard.html",
        username=session["UserName"],
        patient_labels=list(patient_counts.index),
        patient_data=list(patient_counts.values),
        doctor_labels=list(doctor_counts.index),
        doctor_data=list(doctor_counts.values),
        appt_time_labels=list(appointment_times.index),
        appt_time_data=list(appointment_times.values),
        appt_gender_labels=list(appointment_genders.index),
        appt_gender_data=list(appointment_genders.values),
    )

@app.route("/visualization")
def visualization():
    if "UserName" not in session:
        return redirect(url_for("login"))

    connection = get_database_connection()

    df_patients = pd.read_sql("SELECT date_of_birth FROM patient;", connection)
    if not df_patients.empty:
        df_patients['year'] = pd.to_datetime(df_patients['date_of_birth']).dt.year
        patient_counts = df_patients['year'].value_counts().sort_index()
    else:
        patient_counts = pd.Series(dtype=int)

    df_doctors = pd.read_sql("SELECT date_of_birth FROM doctor;", connection)
    if not df_doctors.empty:
        df_doctors['year'] = pd.to_datetime(df_doctors['date_of_birth']).dt.year
        doctor_counts = df_doctors['year'].value_counts().sort_index()
    else:
        doctor_counts = pd.Series(dtype=int)

    df_appts = pd.read_sql("SELECT gender, time FROM appointment;", connection)
    appointment_times = df_appts['time'].value_counts() if not df_appts.empty else pd.Series(dtype=int)
    appointment_genders = df_appts['gender'].value_counts() if not df_appts.empty else pd.Series(dtype=int)

    connection.close()

    return render_template(
        "visualization.html",
        username=session["UserName"],
        patient_labels=[str(x) for x in patient_counts.index],
        patient_data=[int(x) for x in patient_counts.values],
        doctor_labels=[str(x) for x in doctor_counts.index],
        doctor_data=[int(x) for x in doctor_counts.values],
        appt_time_labels=[str(x) for x in appointment_times.index],
        appt_time_data=[int(x) for x in appointment_times.values],
        appt_gender_labels=[str(x) for x in appointment_genders.index],
        appt_gender_data=[int(x) for x in appointment_genders.values],
    )

@app.route("/adddoctr")
def adddoctr():
    if "UserName" in session:
        return render_template("adddoctr.html", username=session["UserName"])
    return redirect(url_for("login"))

@app.route("/Doctor_Hope")
def doctor_hope():
    return render_template("welcome.html")


@app.route("/patients")
def patients():
    if "UserName" not in session:
        return redirect(url_for("login"))
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT first_name, second_name, date_of_birth, gender, email, contact, time, emergency, queue_number
        FROM appointment;
    """)
    rows = cursor.fetchall()
    cursor.close()
    connection.close()
    patients = []
    for row in rows:
        patients.append({
            "first_name": row[0],
            "second_name": row[1],
            "date_of_birth": row[2],
            "gender": row[3],
            "email": row[4],
            "contact": row[5],
            "time": row[6],
            "emergency": row[7],
            "queue_number": row[8],
        })
    return render_template("patients.html", patients=patients, username=session["UserName"])

# ---------------------- MAIN ----------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000, host="localhost")
