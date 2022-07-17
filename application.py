import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # SELECT the necessary STOCK and USER information from the database
    user_info = db.execute("SELECT cash FROM users WHERE id= ?", session["user_id"])
    user_stocks = db.execute("SELECT * FROM stocks WHERE userid= ?", session["user_id"])
    cash = user_info[0]["cash"]

    # For each STOCK the user owns, update the stock price and calculate the new total
    for row in user_stocks:
        print(row)
        stock_symbol = str(row['symbol'])
        stock_shares = int(row['shares'])
        print(stock_symbol)
        print(stock_shares)
        new_price = lookup("stock_symbol")
        print(new_price)
        new_total = stock_shares * new_price
        db.execute("UPDATE stocks SET price = :price, total = :total WHERE userid = :userid AND symbol = :symbol",
                    userid = session["user_id"], # Use current sessions user_id
                    symbol = stock_symbol, # Use the purchase information for the stock symbol
                    price = new_price, # Use the updated price from the lookup() function
                    total = new_total # Use the NEW total calculated price of the stock
        )

    # REFRESH the newly UPDATED stock information for the current user
    user_stocks = db.execute("SELECT * FROM stocks WHERE userid= ?", session["user_id"])

    # Calculate the TOTAL VALUE of the User's portfolio
    total_sum = db.execute("SELECT SUM(total) FROM stocks WHERE userid= ?", session["user_id"])
    total_stocks = total_sum[0]["SUM(total)"]
    total = cash + total_stocks

    # Render the page pushing through the necessary information to be displayed
    return render_template("index.html", row=user_stocks, cash=cash, total=total)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        # Ensure name of stock was submitted
        if not request.form.get("stock"):
            return apology("must provide stock name", 403)

        # Ensure number of shares was specified
        elif not request.form.get("shares"):
            return apology("must provide number of shares", 403)

        # Check that a valid stock was submitted
        stock_info = lookup(request.form.get("stock"))
        if not stock_info:
            return apology("invalid stock name")

        # Query the "users" table to determine the Cash Balance of the current user
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        user_cash = cash[0]["cash"]

        # Calculate the total price of the stock comparing stock price to the number of shares
        total_price = int(request.form.get("shares")) * float(stock_info["price"])

        # Check adequate number of funds exist
        if total_price <= user_cash:

            # Query the "stocks" table to pull the user's information for the current stock
            stock_userbalance = db.execute("SELECT * FROM stocks WHERE symbol = ? AND userid = ?", stock_info["symbol"], session["user_id"])

            # IF the user is buying a new stock, INSERT the new stock into the table with the number of shares and price they were bought at
            if len(stock_userbalance) != 1:
                db.execute("INSERT INTO stocks(userid, symbol, shares, price, total) VALUES(?, ?, ?, ?, ?)",
                    session["user_id"], # INSERT the current session's user_id
                    stock_info["symbol"], # INSERT the stock symbol of the purchased stock
                    request.form.get("shares"), # INSERT the amount of shares specified by the user
                    stock_info["price"], # INSERT the price of the stock at the time of purchase
                    total_price # Insert the "Total Price" of the purchase
                )

            # ELSE UPDATE the "stocks table" with the newly purchased stock information
            else:
                db.execute("UPDATE stocks SET shares = (shares + :newshare), total = (total + :newtotal) WHERE userid = :userid AND symbol = :symbol",
                    userid = session["user_id"], # Use current sessions user_id
                    symbol = stock_info["symbol"], # Use the purchase information for the stock symbol
                    newshare = request.form.get("shares"), # UPDATE the specified shares onto existing share total
                    newtotal = total_price # UPDATE the new total value from the current amount
                )

            # UPDATE the current user's CASH balance for the price of the purchased shares
            balance = user_cash - total_price
            db.execute("UPDATE users SET cash = ? WHERE id = ?", balance, session["user_id"])

            # INSERT the purchase into the "history" table of the database
            db.execute("INSERT INTO history(userid, symbol, shares, price, total) VALUES(?, ?, ?, ?, ?)",
                    session["user_id"], # INSERT the current session's user_id
                    stock_info["symbol"], # INSERT the stock symbol of the purchased stock
                    request.form.get("shares"), # INSERT the amount of shares specified by the user
                    stock_info["price"], # INSERT the price of the stock at the time of purchase
                    total_price # Insert the "Total Price" of the purchase
            )

        # IF the user doesn't enough funds return an apology
        else:
            return apology("Insufficient funds")

        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # SELECT all transaction records for the current user ORDERED BY most recent
    history = db.execute("SELECT * FROM history WHERE userid= ?", session["user_id"])

    # Render the history template and push through the necessary transaction information
    return render_template("history.html", history=history)

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
    """Get stock quote."""

    username = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("symbol"):
            return apology("Please provide a stock", 403)

        stock = lookup(request.form.get("symbol"))

        if stock == None:
            return apology("No matching stock found")
        else:
            return render_template("quoted.html", stock=stock, username=username[0]["username"])

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html", username=username[0]["username"])


@app.route("/register", methods=["GET", "POST"])
def register():

    """Register user""" # FINISHED #

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

        # Ensure password was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username doesn't already exist
        if len(rows) != 0 :
            return apology("Username already taken", 403)

        else:

            # Store password and confirmation and compare that they are the same
            passkey = request.form.get("password")
            check = request.form.get("confirmation")

            if passkey == check:

                # Generate a hash code for the submitted password using the provide information from Werkzeug Security
                phash = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8)

                # Insert the username and password hash into the finance database, users table
                db.execute("INSERT INTO users(username, hash) VALUES(?, ?)" , request.form.get("username"), phash)

                # Redirect to the homepage of the website
                return redirect("/")

            else:
                return apology("passwords do not match.")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure stock symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide stock", 403)

        # Ensure the number of shares was submitted
        elif not request.form.get("shares"):
            return apology("must provide password", 403)

        # Ensure the number of shares was a valid value
        if request.form.get("shares") <= 0:
            return apology("Number of stocks must be greater than 0")

        # Ensure the specified number of shares does not exceed the User's available stocks
        available = db.execute("SELECT shares FROM stocks WHERE symbol = ? AND userid = ?", request.form.get("symbol"), session["user_id"])

        if available[0]['shares'] < request.form.get("shares"):
            return apology("User does not have enough shares to make sale.", 403)

        # Calculate value of sale
        quote = lookup(request.form.get("symbol"))

        if quote == None:
            return apology("Please input a valid stock")

        # Query the "users" table to determine the Cash Balance of the current user
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        user_cash = cash[0]["cash"]

        # Calculate the dollar value of the transaction
        transaction_value = quote['price'] * (request.form.get("shares"))

        # UPDATE the current user's CASH balance for the price of the sold shares
        balance = user_cash + transaction_value
        db.execute("UPDATE users SET cash = ? WHERE id = ?", balance, session["user_id"])


        db.execute("UPDATE stocks SET shares = (shares + :newshare), total = (total + :newtotal) WHERE userid = :userid AND symbol = :symbol",
                    userid = session["user_id"], # Use current sessions user_id
                    symbol = stock_info["symbol"], # Use the purchase information for the stock symbol
                    newshare = request.form.get("shares"), # UPDATE the specified shares onto existing share total
                    newtotal = total_price # UPDATE the new total value from the current amount










    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("sell.html" stocks=stocks)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
