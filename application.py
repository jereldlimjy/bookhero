import os

from flask import Flask, session, render_template, request, session, flash, redirect, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from flask_bcrypt import check_password_hash, generate_password_hash

from helpers import login_required

import requests

app = Flask(__name__)
app.secret_key = "dfdfsdsdsdsdsadsa"

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


@app.route("/")
@login_required
def index():
    return render_template("home.html")

@app.route("/register", methods=["GET", "POST"])
def register():
	"""Register user"""

	if request.method == "POST":

		username = request.form.get("username")
		password = request.form.get("password")
		confirmation = request.form.get("confirmation")

		# Ensure no fields are empty
		if not (username or password or confirmation):
			return render_template("error.html", message="Please fill in all required fields!")

		rows = db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).rowcount

		# Check whether username is taken
		if rows != 0:
			return render_template("error.html", message="Too late, username is already taken!")

		# Check if username is valid
		if username.isalnum() == False:
			return render_template("error.html", message="Please enter a valid username.")

		# Check whether password and confirmation are the same
		if not password == confirmation:
			return render_template("error.html", message="Please ensure that your passwords are the same!")

		hashed_password = generate_password_hash(password).decode('utf-8')

		# Insert new user into users database
		db.execute("INSERT INTO users (username, password) VALUES (:username, :password)", {"username": username, "password": hashed_password})
		db.commit()

		flash("Registration success!")
		return render_template("index.html")

	return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
	"""Log user in"""

	# Forget any user id
	session.clear()

	if request.method == "POST":

		username = request.form.get("username")
		password = request.form.get("password")

		# Ensure username and password are filled
		if not (username or password):
			return render_template("error.html", message="Please fill in all required fields!")

		rows = db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).fetchone()

		if rows is None:
			return render_template("error.html", message="Sorry, user not found! Please try again or register an account.")

		if username == rows["username"] and check_password_hash(rows["password"], password) == True:
			session["user_id"] = rows["id"]

			return redirect("/")

		else:
			return render_template("error.html", message="Please ensure that your password is correct!")

	return render_template("index.html")

@app.route("/logout")
@login_required
def logout():
	"""Log user out"""

	session.clear()

	# Redirect to welcome page
	return redirect("/")

@app.route("/search", methods=["POST"])
@login_required
def search():

	if request.method == "POST":
		search_by = request.form.get("search_by")
		search = "%" + request.form.get("search") + "%"

		# Query via column name and input
		if search_by == "isbn":
			rows = db.execute("SELECT * FROM books WHERE isbn ILIKE :search", {"search": search})

		elif search_by == "title":
			rows = db.execute("SELECT * FROM books WHERE title ILIKE :search", {"search": search})

		elif search_by == "author":
			rows = db.execute("SELECT * FROM books WHERE author ILIKE :search", {"search": search})

		else:
			rows = db.execute("SELECT * FROM books WHERE year ILIKE :search", {"search": search})

		if rows.rowcount == 0:
			return render_template("error.html", message="Sorry, no results found. Please try searching again!")

		rows = rows.fetchall()
		
		return render_template("search.html", rows=rows, search=request.form.get("search"))

	else:
		return render_template("error.html", message="Sorry, please search for a book using the form!")

@app.route("/book/<int:book_id>")
@login_required
def book(book_id):

	# Ensure the book exists
	book = db.execute("SELECT * FROM books WHERE id = :id", {"id": book_id}).fetchone()

	if book is None:
		return render_template("error.html", message="Sorry, something went wrong! :(")

	isbn = book["isbn"]

	# Request to Goodreads API
	res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": os.getenv("KEY"), "isbns": isbn})

	# Error retrieving data
	if res.status_code != 200:
		raise Exception("ERROR: API request unsuccessful.")

	data = res.json()

	avg_rating = data["books"][0]["average_rating"]
	ratings = int(data["books"][0]["work_ratings_count"])

	# Add comma separator
	ratings = ('{:,}'.format(ratings))

	reviews = db.execute("SELECT username, review, rating, DATE(date) FROM reviews JOIN users ON users.id = reviews.user_id WHERE book_id = :book_id ORDER BY reviews.id DESC", {"book_id": book_id}).fetchall()

	return render_template("book.html", book=book, avg_rating=avg_rating, ratings=ratings, reviews=reviews)

@app.route("/book/<int:book_id>", methods=["POST"])
@login_required
def review(book_id):

	book = db.execute("SELECT * FROM books WHERE id = :id", {"id": book_id}).fetchone()

	review = request.form.get("review")
	rating = request.form.get("rating")

	# Ensure review is valid
	if review is None:
		return render_template("error.html", message="Sorry, an error occurred while submitting your review")

	# Check if user submitted a review before
	rows = db.execute("SELECT * FROM reviews WHERE user_id = :user_id AND book_id = :book_id", {"user_id": session["user_id"], "book_id": book_id}).rowcount

	if rows != 0:
		return render_template("error.html", message="Sorry, you have already reviewed this book!")

	db.execute("INSERT INTO reviews (user_id, book_id, rating, review) VALUES (:user_id, :book_id, :rating, :review)", {"user_id": session["user_id"], "rating": rating, "book_id": book_id, "review": review})
	db.commit()

	return redirect(f"/book/{book_id}")

@app.route("/api/<string:isbn>")
def book_api(isbn):
	# Return book details in json

	# avg_score cast as float because json doesn't support decimal
	row = db.execute("SELECT title, author, year, isbn, CAST(ROUND(AVG(rating)::numeric,1) AS FLOAT) AS avg_score, COUNT(rating) AS review_count FROM books LEFT JOIN reviews ON books.id = reviews.book_id WHERE isbn=:isbn GROUP BY(title,author,year,isbn);", {"isbn": isbn}).fetchone()

	# If ISBN number is invalid
	if row is None:
		return jsonify({"error": "Invalid isbn"}), 422

	return jsonify({
		"title": row.title,
		"author": row.author,
		"year": row.year,
		"isbn": row.isbn,
		"review_count": row.review_count,
		"average_score": row.avg_score
		})