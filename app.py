from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database connection
def get_db_connection():
    conn = sqlite3.connect('p2p_trades.db')
    conn.row_factory = sqlite3.Row
    return conn


# Route to home page (redirect to login if user is not logged in)
@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('search'))  # If logged in, redirect to the search page


# Route to sign up page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
                         (username, hashed_password))
            conn.commit()
            conn.close()
            flash('Signup successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists. Please choose another one.', 'danger')
            return redirect(url_for('signup'))

    return render_template('signup.html')


# Route to login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']  # Store user ID in session
            session['username'] = user['username']
            flash('Login successful!', 'success')
            return redirect(url_for('search'))  # Redirect to the search page after login
        else:
            flash('Login failed. Check your username and password.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')


# Route to logout (clears session)
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


# Route to Search
@app.route('/search', methods=['GET', 'POST'])
def search():
    if 'user_id' not in session:
        flash('Please log in to continue.', 'warning')
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Pagination logic
    page = request.args.get('page', 1, type=int)
    limit = 10
    offset = (page - 1) * limit

    conn = get_db_connection()

    # Fetch unique payment methods and received bank names for dropdowns
    payment_methods_query = "SELECT DISTINCT PaymentMethod FROM payment_methods"
    received_bank_query = "SELECT DISTINCT ReceivedIn FROM payment_methods"

    payment_methods = [row[0] for row in conn.execute(payment_methods_query).fetchall()]
    received_banks = [row[0] for row in conn.execute(received_bank_query).fetchall()]
    coins = ['BTC', 'ETH', 'LTC', 'USDT', 'USDC', 'BNB', 'SOL', 'XRP', 'TRX', 'BCH']

    # Initialize search parameters
    start_date = request.form.get('start_date') if request.method == 'POST' else request.args.get('start_date')
    end_date = request.form.get('end_date') if request.method == 'POST' else request.args.get('end_date')
    coin = request.form.get('coin', '').upper() if request.method == 'POST' else request.args.get('coin', '').upper()
    payment_method = request.form.get('payment_method', '') if request.method == 'POST' else request.args.get('payment_method', '')
    received_in = request.form.get('received_in', '') if request.method == 'POST' else request.args.get('received_in', '')
    amount = request.form.get('amount', '') if request.method == 'POST' else request.args.get('amount', '')
    buyer_name = request.form.get('buyer_name', '').upper() if request.method == 'POST' else request.args.get('buyer_name', '').upper()

    trades = []
    total_trades = 0

    # Search functionality
    query = '''
        SELECT trade.OrderNo, trade.Coin, trade.TradeDate, trade.TradeTime, 
               price.UnitPrice, price.Quantity, price.TotalFiat, 
               payment_methods.PaymentMethod, payment_methods.ReceivedIn, 
               buyer.Name, buyer.Phone
        FROM trade
        JOIN price ON trade.OrderNo = price.OrderNo
        JOIN payment_methods ON trade.OrderNo = payment_methods.OrderNo
        JOIN buyer ON trade.OrderNo = buyer.OrderNo
        WHERE trade.user_id = ?
    '''
    params = [user_id]

    # Add conditions based on the search fields
    if start_date and end_date:
        query += ' AND trade.TradeDate BETWEEN ? AND ?'
        params.extend([start_date, end_date])
    if coin:
        query += ' AND UPPER(trade.Coin) = ?'
        params.append(coin)
    if payment_method:
        query += ' AND payment_methods.PaymentMethod = ?'
        params.append(payment_method)
    if received_in:
        query += ' AND payment_methods.ReceivedIn = ?'
        params.append(received_in)
    if amount:
        query += ' AND price.TotalFiat = ?'
        params.append(float(amount))
    if buyer_name:
        query += ' AND UPPER(buyer.Name) = ?'
        params.append(buyer_name)

    # Execute the query for the filtered trades with pagination
    query += ' ORDER BY trade.OrderNo DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])

    cur = conn.cursor()
    cur.execute(query, params)
    trades = [dict(trade) for trade in cur.fetchall()]

    # Count total trades matching the search criteria for pagination
    count_query = '''
        SELECT COUNT(*)
        FROM trade
        JOIN price ON trade.OrderNo = price.OrderNo
        JOIN payment_methods ON trade.OrderNo = payment_methods.OrderNo
        JOIN buyer ON trade.OrderNo = buyer.OrderNo
        WHERE trade.user_id = ?
    '''
    count_params = [user_id]

    # Add conditions to count query as well
    if start_date and end_date:
        count_query += ' AND trade.TradeDate BETWEEN ? AND ?'
        count_params.extend([start_date, end_date])
    if coin:
        count_query += ' AND UPPER(trade.Coin) = ?'
        count_params.append(coin)
    if payment_method:
        count_query += ' AND payment_methods.PaymentMethod = ?'
        count_params.append(payment_method)
    if received_in:
        count_query += ' AND payment_methods.ReceivedIn = ?'
        count_params.append(received_in)
    if amount:
        count_query += ' AND price.TotalFiat = ?'
        count_params.append(float(amount))
    if buyer_name:
        count_query += ' AND UPPER(buyer.Name) = ?'
        count_params.append(buyer_name)

    total_trades = conn.execute(count_query, count_params).fetchone()[0]

    conn.close()
    total_pages = (total_trades + limit - 1) // limit  # Calculate total pages

    searching = request.method == 'POST'  # True if the user is searching

    return render_template('index.html', trades=trades, page=page, total_pages=total_pages, coins=coins,
                           payment_methods=payment_methods, received_banks=received_banks, searching=searching)



# Route to add trade page
@app.route('/add_trade', methods=['GET', 'POST'])
def add_trade():
    if 'user_id' not in session:
        flash('Please log in to continue.', 'warning')
        return redirect(url_for('login'))

    # Define lists for dropdowns
    payment_methods = ['UPI', 'PhonePe', 'Gpay', 'IMPS', 'NEFT', 'RTGS', 'Bank Transfer']  # Example payment methods
    coins = ['BTC', 'ETH', 'LTC', 'USDT', 'USDC', 'BNB', 'SOL', 'XRP', 'TRX', 'BCH']  # Example coins
    received_banks = ['ICICI', 'Federal', 'KOTAK', 'HDFC', 'Canara', 'Equitas', 'Axis']  # Example banks

    if request.method == 'POST':
        # Get form data
        order_no = request.form['order_no']
        coin = request.form['coin']  # This will be selected from dropdown
        trade_date = request.form['trade_date']
        trade_time = request.form['trade_time']
        unit_price = request.form['unit_price']
        quantity = request.form['quantity']
        total_fiat = request.form['total_fiat']
        payment_method = request.form['payment_method']  # This will be selected from dropdown
        received_in = request.form['received_in']  # This will be selected from dropdown
        buyer_name = request.form['buyer_name']
        buyer_phone = request.form['buyer_phone']

        user_id = session['user_id']  # Get the logged-in user's ID

        conn = get_db_connection()

        # Insert into the trade table
        conn.execute('INSERT INTO trade (user_id, OrderNo, TradeDate, TradeTime, UnitPrice, Quantity, TotalFiat, Coin) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', 
                     (user_id, order_no, trade_date, trade_time, unit_price, quantity, total_fiat, coin))

        # Insert into price table
        conn.execute('INSERT INTO price (OrderNo, UnitPrice, Quantity, TotalFiat, user_id) VALUES (?, ?, ?, ?, ?)', 
                     (order_no, unit_price, quantity, total_fiat, user_id))

        # Insert into payment_methods table
        conn.execute('INSERT INTO payment_methods (OrderNo, PaymentMethod, ReceivedIn, user_id) VALUES (?, ?, ?, ?)', 
                     (order_no, payment_method, received_in, user_id))

        # Insert into buyer table
        conn.execute('INSERT INTO buyer (OrderNo, Name, Phone, user_id) VALUES (?, ?, ?, ?)', 
                     (order_no, buyer_name, buyer_phone, user_id))

        conn.commit()
        conn.close()
        flash('Trade added successfully!', 'success')
        return redirect(url_for('search'))

    return render_template('add_trade.html', payment_methods=payment_methods, coins=coins, received_banks=received_banks)


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']  # Get the logged-in user's ID from the session

    # Connect to the database
    conn = get_db_connection()
    cursor = conn.cursor()

    # Execute the query to get total trades and volume
    cursor.execute('''
        SELECT 
            COUNT(*) AS total_trades, 
            SUM(TotalFiat) AS total_volume 
        FROM 
            trade 
        WHERE 
            user_id = ?;
    ''', (user_id,))
    
    user_data = cursor.fetchone()  # Fetch the result
    conn.close()

    # Prepare data for rendering
    profile_data = {
        'username': session['username'],  # Get the username from session
        'total_trades': user_data[0],     # Total trades
        'total_volume': user_data[1]       # Total volume
    }

    return render_template('profile.html', user_data=profile_data)


@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            flash("Passwords do not match!", "danger")
            return render_template('reset_password.html')

        # Hash the new password before storing it
        hashed_password = generate_password_hash(new_password)

        # Assuming you have the user's ID stored in session after identity verification
        user_id = session['user_id']

        # Update the password in the database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users
            SET password = ?
            WHERE id = ?;
        ''', (hashed_password, user_id))

        conn.commit()
        conn.close()

        flash("Password reset successful!", "success")
        return redirect(url_for('search'))  # Redirect to the home page after successful password reset

    return render_template('reset_password.html')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)