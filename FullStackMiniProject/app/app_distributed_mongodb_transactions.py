from base64 import b64encode
from bson import Binary
from flask import Flask, render_template, request, redirect, url_for, session
from pymongo import MongoClient
from flask_session import Session
from datetime import datetime, timedelta
from urllib.parse import unquote as urllib_unquote
import os

app = Flask(__name__)
app.config["SESSION_TYPE"] = "redis"  # Use Redis for distributed sessions
app.config["SESSION_REDIS"] = "redis://localhost:6379"  # Configure Redis
app.jinja_env.globals.update(zip=zip, int=int, len=len)
Session(app)

@app.template_filter('unquote')
def unquote(url):
    safe = app.jinja_env.filters['safe']
    return safe(urllib_unquote(url))

# MongoDB setup - Must be a replica set for transactions
client = MongoClient('mongodb://localhost:27017/?replicaSet=rs0')
db = client['BidHub']
user_collection = db['Users']
product_collection = db['Products']
audit_collection = db['AuditLog']  # For audit trail

# Instance identifier for distributed deployment
INSTANCE_ID = os.getenv('INSTANCE_ID', 'instance-1')

print(f"Starting Flask instance: {INSTANCE_ID}")

@app.route('/')
def home():
    session['user_id'] = None
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    return render_template('signup.html')

@app.route('/auth', methods=['POST'])
def auth():
    email = request.form['email']
    password = request.form['password']

    if email == 'admin@gmail.com' and password == 'admin':
        return redirect(url_for('admin', dashboard=True))

    user = user_collection.find_one({"email": email, "password": password})

    if user:
        name = user['name']
        session['user_id'] = user['id']

        # Check and finalize expired auctions
        # Note: This should ideally be a background job in production
        products = list(product_collection.find({'user_id':user['id']}))

        for product in products:
            if product['end_time'] < datetime.now():
                finalize_auction(product)

        return redirect(url_for('buyer', name=name))
    else:
        return render_template('login.html', login_error='incorrect credentials')

def finalize_auction(product):
    """Finalize expired auction using MongoDB transaction"""
    with client.start_session() as session_db:
        with session_db.start_transaction():
            try:
                history = product['history']
                history.sort(key=lambda x: x['amount'], reverse=True)
                winner = history[0]

                # Transfer ownership to winner
                user_collection.update_one(
                    {'id': winner['user_id']},
                    {
                        '$push': {'owned_products': product},
                        '$inc': {'total_spent': product['price']}
                    },
                    session=session_db
                )

                # Delete product from active auctions
                product_collection.delete_one(
                    {'product_id': product['product_id']},
                    session=session_db
                )

                # Audit log (still within transaction)
                audit_collection.insert_one({
                    'action': 'END_AUCTION',
                    'product_id': product['product_id'],
                    'winner_id': winner['user_id'],
                    'final_price': product['price'],
                    'timestamp': datetime.now(),
                    'instance_id': INSTANCE_ID
                }, session=session_db)

                # Transaction commits automatically if no exception
                print(f"Auction {product['product_id']} finalized. Winner: {winner['user_id']}")

            except Exception as e:
                # Transaction automatically rolls back
                print(f"Error finalizing auction: {e}")
                raise

@app.route('/register', methods=['GET', 'POST'])
def register():
    email = request.form.get('email')

    # Check if user exists (outside transaction for performance)
    existing_user = user_collection.find_one({'email': email})
    if existing_user:
        return render_template('signup.html', signup_error='email already exists, try logging in')

    # Use MongoDB transaction for registration
    with client.start_session() as session_db:
        with session_db.start_transaction():
            try:
                # Generate ID within transaction to avoid conflicts
                id = user_collection.count_documents({}, session=session_db) + 1

                name = request.form.get('name')
                password = request.form.get('password')
                phone = request.form.get('phone')
                address = request.form.get('address')

                new_user = {
                    'id': id,
                    'name': name,
                    'password': password,
                    'email': email,
                    'phone': phone,
                    'address': address,
                    'owned_products': [],
                    'num_of_bids': 0,
                    'total_spent': 0,
                    'joined_on': datetime.now(),
                    'listings': 0
                }

                # Insert user
                user_collection.insert_one(new_user, session=session_db)

                # Audit log
                audit_collection.insert_one({
                    'action': 'CREATE_USER',
                    'user_id': id,
                    'email': email,
                    'timestamp': datetime.now(),
                    'instance_id': INSTANCE_ID
                }, session=session_db)

                # Transaction commits here
                print(f"User {id} registered successfully on {INSTANCE_ID}")

                session['user_id'] = id
                return redirect(url_for('buyer', name=name))

            except Exception as e:
                # Automatic rollback
                print(f"Registration error: {e}")
                return render_template('signup.html', signup_error='Registration failed. Please try again.')

@app.route('/buyer', methods=['GET', 'POST'])
def buyer():
    id = session['user_id']
    user = user_collection.find_one({'id': int(id)})
    name = user['name']

    products = list(db.Products.find({}))
    time_lefts = []

    for product in products:
        if product.get('image'):
            product['image_base64'] = b64encode(product['image']).decode('utf-8')

        time_left = product['end_time'] - datetime.now()
        time_lefts.append(f"{time_left.days} days {time_left.seconds//3600} hours left")

    return render_template('buyer.html', name=name, products=products, time_lefts=time_lefts, user=user)

@app.route('/seller', methods=['GET','POST'])
def seller():
    id = session['user_id']
    user = user_collection.find_one({'id': int(id)})
    name = user['name']
    return render_template('seller.html', name=name)

@app.route('/listing', methods=['GET','POST'])
def listing():
    id = session['user_id']
    user = user_collection.find_one({'id': int(id)})
    name = user['name']

    listings = list(product_collection.find({'user_id': int(id)}))

    for listing in listings:
        if listing.get('image'):
            listing['image_base64'] = b64encode(listing['image']).decode('utf-8')

        listing['time_left'] = listing['end_time'] - datetime.now()
        listing['is_editable'] = listing['time_left'].days > 1

    return render_template('listing.html', id=id, name=name, listings=listings)

@app.route('/product', methods=['GET', 'POST'])
def product():
    user_id = session['user_id']
    user = user_collection.find_one({'id': int(user_id)})
    name = user['name']

    if request.method == 'POST':
        # Use MongoDB transaction for product creation
        with client.start_session() as session_db:
            with session_db.start_transaction():
                try:
                    product_id = product_collection.count_documents({}, session=session_db) + 1
                    title = request.form['title']
                    description = request.form['description']
                    image_file = request.files['image']
                    price = int(request.form['startingPrice'])
                    duration = request.form['duration']
                    category = request.form['category']
                    condition = request.form['condition']
                    end_time = datetime.now().replace(microsecond=0) + timedelta(days=int(duration))

                    image_data = None
                    if image_file:
                        image_data = image_file.read()

                    new_product = {
                        'user_id': user_id,
                        'product_id': product_id,
                        'title': title,
                        'description': description,
                        'price': price,
                        'end_time': end_time,
                        'category': category,
                        'condition': condition,
                        'image': Binary(image_data) if image_data else None,
                        'history': [{
                            'user_id': user_id,
                            'bidder': name,
                            'time': datetime.now().replace(microsecond=0),
                            'amount': price
                        }]
                    }

                    # Insert product
                    product_collection.insert_one(new_product, session=session_db)

                    # Update user stats
                    user_collection.update_one(
                        {'id': user_id},
                        {'$inc': {'num_of_bids': 1, 'listings': 1}},
                        session=session_db
                    )

                    # Audit log
                    audit_collection.insert_one({
                        'action': 'CREATE_PRODUCT',
                        'product_id': product_id,
                        'user_id': user_id,
                        'title': title,
                        'price': price,
                        'timestamp': datetime.now(),
                        'instance_id': INSTANCE_ID
                    }, session=session_db)

                    print(f"Product {product_id} created on {INSTANCE_ID}")
                    return redirect(url_for('buyer', name=name))

                except Exception as e:
                    print(f"Error creating product: {e}")
                    return redirect(url_for('seller'))

@app.route('/bid', methods=['POST'])
def bid():
    product_id = request.args.get('product_id')
    price = request.form.get('bidAmount')
    user_id = session['user_id']

    # Use MongoDB transaction for bid placement (CRITICAL for race condition prevention)
    with client.start_session() as session_db:
        with session_db.start_transaction():
            try:
                # Read current product state within transaction
                product = product_collection.find_one(
                    {'product_id': int(product_id)},
                    session=session_db
                )

                if not product:
                    raise ValueError("Product not found")

                # Validate bid (must be higher than current price)
                new_price = int(price)
                if new_price <= product['price']:
                    raise ValueError(f"Bid must be higher than current price ${product['price']}")

                # Get user info
                user = user_collection.find_one({'id': int(user_id)}, session=session_db)
                curr_time = datetime.now().replace(microsecond=0)

                history_entry = {
                    'user_id': user_id,
                    'bidder': user['name'],
                    'time': curr_time,
                    'amount': new_price
                }

                # Update product atomically
                product_collection.update_one(
                    {'product_id': int(product_id)},
                    {
                        '$set': {'price': new_price},
                        '$push': {'history': history_entry}
                    },
                    session=session_db
                )

                # Update user stats
                user_collection.update_one(
                    {'id': user_id},
                    {'$inc': {'num_of_bids': 1}},
                    session=session_db
                )

                # Audit log
                audit_collection.insert_one({
                    'action': 'BID',
                    'product_id': int(product_id),
                    'user_id': user_id,
                    'amount': new_price,
                    'timestamp': curr_time,
                    'instance_id': INSTANCE_ID
                }, session=session_db)

                print(f"Bid placed on {INSTANCE_ID}: Product {product_id}, Amount ${new_price}")

            except Exception as e:
                print(f"Error placing bid: {e}")
                # Transaction automatically rolls back

    return redirect(url_for('buyer'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    user_id = session['user_id']
    edit = request.args.get('edit')
    user = user_collection.find_one({'id': user_id})
    return render_template('profile.html', user=user, edit=edit)

@app.route('/modal', methods=['GET', 'POST'])
def modal():
    id = session['user_id']
    name = user_collection.find_one({'id': int(id)})['name']

    products = list(db.Products.find())
    time_lefts = []

    for product in products:
        if product.get('image'):
            product['image_base64'] = b64encode(product['image']).decode('utf-8')

        time_left = product['end_time'] - datetime.now()
        time_lefts.append(f"{time_left.days} days {time_left.seconds//3600} hours left")

    product_id = request.args.get('product_id')
    product = product_collection.find_one({"product_id": int(product_id)})

    history = product['history']
    history.sort(key=lambda x: x['amount'], reverse=True)

    return render_template("modal.html", selected_product=product, name=name,
                         products=products, time_lefts=time_lefts, histories=history)

@app.route('/updateProfile', methods=['POST'])
def updateProfile():
    data = request.form
    username = data['username']
    email = data['email']
    phone = data['phone']
    address = data['address']

    user_collection.update_one({'id':session['user_id']},{'$set': {
        'username': username,
        'email': email,
        'phone': phone,
        'address': address
    }})

    return redirect(url_for('profile', edit=False))

@app.route('/editListing', methods=['GET'])
def editListing():
    id = session['user_id']
    user = user_collection.find_one({'id': int(id)})
    name = user['name']

    listings = list(product_collection.find({'user_id': int(id)}))

    for listing in listings:
        if listing.get('image'):
            listing['image_base64'] = b64encode(listing['image']).decode('utf-8')

        listing['time_left'] = listing['end_time'] - datetime.now()
        listing['is_editable'] = listing['time_left'].days > 1

    product_id = int(request.args.get('product_id'))
    product = product_collection.find_one({'product_id': product_id})

    return render_template('edit_listing.html', product=product, name=name, listings=listings)

@app.route('/viewListing', methods=['GET'])
def viewListing():
    product_id = int(request.args.get('product_id'))
    product = product_collection.find_one({'product_id': product_id})

    product['time_left'] = product['end_time'] - datetime.now()

    histories = product['history']
    bids = []
    times = []
    gaps = []
    bid_freq = '∞'

    for history in histories:
        bids.append(history['amount'])
        times.append(history['time'])

    if len(times) > 1:
        for i in range(1, len(times)):
            gaps.append((times[i] - times[i-1]).seconds)

        bid_freq = int(sum(gaps)/len(gaps))
        bid_freq = f'{bid_freq//86400}d {(bid_freq % 86400)//3600}h'

    avg_bid = sum(bids)/len(bids)

    if product.get('image'):
        product['image_base64'] = b64encode(product['image']).decode('utf-8')

    return render_template('view_listing.html', product=product, avg_bid=avg_bid, bid_freq=bid_freq)

@app.route('/updateListing', methods=['POST'])
def updateListing():
    product_id = request.args.get('product_id')

    with client.start_session() as session_db:
        with session_db.start_transaction():
            try:
                title = request.form['title']
                description = request.form['description']
                image_file = request.files['image']
                category = request.form['category']
                condition = request.form['condition']

                update_data = {
                    'title': title,
                    'description': description,
                    'category': category,
                    'condition': condition
                }

                if image_file and image_file.filename:
                    image_data = image_file.read()
                    update_data['image'] = Binary(image_data)

                product_collection.update_one(
                    {'product_id': int(product_id)},
                    {'$set': update_data},
                    session=session_db
                )

                # Audit log
                audit_collection.insert_one({
                    'action': 'UPDATE_PRODUCT',
                    'product_id': int(product_id),
                    'timestamp': datetime.now(),
                    'instance_id': INSTANCE_ID
                }, session=session_db)

            except Exception as e:
                print(f"Error updating listing: {e}")

    return redirect(url_for('listing'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.args.get('dashboard') == 'True':
        metrics = {}
        metrics['total_users'] = user_collection.count_documents({})
        metrics['total_auctions'] = product_collection.count_documents({})
        metrics['total_revenue'] = 0
        metrics['total_sales'] = 0

        # Use aggregation for better performance
        pipeline = [
            {'$group': {
                '_id': None,
                'total_spent': {'$sum': '$total_spent'},
                'total_sales': {'$sum': {'$size': '$owned_products'}}
            }}
        ]

        result = list(user_collection.aggregate(pipeline))
        if result:
            metrics['total_revenue'] = int(result[0]['total_spent'] * 0.05)
            metrics['total_sales'] = result[0]['total_sales']

        return render_template('admin.html', dashboard=True, metrics=metrics)

    elif request.args.get('products') == 'True':
        products = list(product_collection.find({}))
        for product in products:
            product['time_left'] = product['end_time'] - datetime.now()
        return render_template('admin.html', products_view=True, products=products)

    elif request.args.get('users') == 'True':
        users = list(user_collection.find({}))
        return render_template('admin.html', users_view=True, users=users)

@app.route('/delete_user', methods=['GET'])
def delete_user():
    user_id = request.args.get('user_id')

    with client.start_session() as session_db:
        with session_db.start_transaction():
            try:
                user_collection.delete_one({'id': int(user_id)}, session=session_db)

                audit_collection.insert_one({
                    'action': 'DELETE_USER',
                    'user_id': int(user_id),
                    'timestamp': datetime.now(),
                    'instance_id': INSTANCE_ID
                }, session=session_db)

            except Exception as e:
                print(f"Error deleting user: {e}")

    return redirect(url_for('admin', users=True))

@app.route('/delete_product', methods=['GET'])
def delete_product():
    product_id = request.args.get('product_id')

    with client.start_session() as session_db:
        with session_db.start_transaction():
            try:
                product_collection.delete_one({'product_id': int(product_id)}, session=session_db)

                audit_collection.insert_one({
                    'action': 'DELETE_PRODUCT',
                    'product_id': int(product_id),
                    'timestamp': datetime.now(),
                    'instance_id': INSTANCE_ID
                }, session=session_db)

            except Exception as e:
                print(f"Error deleting product: {e}")

    return redirect(url_for('admin', products=True))

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
