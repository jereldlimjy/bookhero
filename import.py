import csv
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

# Set up database
engine = create_engine(os.getenv("DATABASE_URL")) 
db = scoped_session(sessionmaker(bind=engine))

def main():
	f = open("cs50w/project1/books.csv")
	reader = csv.reader(f)

	# Skip headings
	next(reader)

	for isbn, title, author, year in reader:
		db.execute("INSERT INTO books (isbn, title, author, year) VALUES (:isbn, :title, :author, :year)", 
				    {"isbn": isbn, "title": title, "author": author, "year": year})

# Already imported
db.commit()

if __name__ == "__main__":
	main()