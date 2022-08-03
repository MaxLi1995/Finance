import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, date

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET"])
@login_required
def index():
    row = db.execute("select symbol, sum(amount) as amount from history where user_id = ? group by symbol", session["user_id"])
    fund = db.execute("select cash from users where id = ?", session["user_id"])
    stock_prices = {}
    for a in row:
        stock_prices[a.get("symbol")] = lookup(a.get("symbol")).get("price")

    return render_template("index.html", fund=fund, row=row, price=stock_prices)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 403)

        if not request.form.get("shares"):
            return apology("must provide number of stock to buy", 403)

        amount = request.form.get("shares")
        stock_detail = lookup(request.form.get("symbol"))
        fund = db.execute("select cash from users where id = ?", session["user_id"])

        if stock_detail is None:
            return apology("stock does not exist", 403)
        elif fund[0].get("cash") - int(amount) * stock_detail.get("price") < 0:
            return apology("not enough funds", 403)
        else:
            remaining = fund[0].get("cash") - int(amount) * stock_detail.get("price")
            db.execute("insert into history (user_id, symbol, amount, date, price) values(?, ?, ?, ?, ?)", session["user_id"], stock_detail.get("symbol"), amount, date.today().strftime("%m/%d/%y") + ' ' + datetime.now().strftime("%H:%M:%S"), stock_detail.get("price"))
            db.execute("update users set cash = ? where id = ?", str(round(remaining, 2)), session["user_id"])
            flash("purchase sucessful")


        return redirect("/")
    else:
        return render_template("buy.html")



@app.route("/history", methods=["GET"])
@login_required
def history():

    row = db.execute("select symbol, amount, price, date from history where user_id = ?", session["user_id"])

    return render_template("history.html", history=row)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 400)

        detail = lookup(request.form.get("symbol"))

        if detail is None:
            return apology("stock doesn't exist", 400)
        else:
            return render_template("quoted.html", value=detail)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords does not match", 400)

        username = request.form.get("username")
        password = request.form.get("password")

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(rows) == 0:
            db.execute("insert into users (username, hash) values(?, ?)", username, generate_password_hash(password))
            rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

            # Remember which user has logged in
            session["user_id"] = rows[0]["id"]
            flash("registration successful")

            # Redirect user to home page
            return redirect("/")
        else:
            return apology("username already exists", 400)



    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 403)

        if not request.form.get("shares"):
            return apology("must provide number of stock to sell", 403)

        amount = int(request.form.get("shares"))
        stock_detail = lookup(request.form.get("symbol"))
        info = db.execute("select symbol, sum(amount) as amount from history where user_id = ? and symbol is ? group by symbol", session["user_id"], request.form.get("symbol").upper())
        fund = db.execute("select cash from users where id = ?", session["user_id"])[0].get("cash")


        if stock_detail is None:
            return apology("stock does not exist", 403)
        elif amount > int(info[0].get("amount")) or info[0].get("amount") is None:
            return apology("selling more stock than owned", 403)
        else:
            value = stock_detail.get("price") * amount
            db.execute("insert into history (user_id, symbol, amount, date, price) values(?, ?, ?, ?, ?)", session["user_id"], stock_detail.get("symbol"), -amount, date.today().strftime("%m/%d/%y") + ' ' + datetime.now().strftime("%H:%M:%S"), stock_detail.get("price"))
            db.execute("update users set cash = ? where id = ?", str(round(value + fund, 2)), session["user_id"])
            flash("sold sucessfully")


        return redirect("/")
    else:
        return render_template("sell.html")
