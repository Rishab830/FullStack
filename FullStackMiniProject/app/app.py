from base64 import b64encode
from bson import Binary
from flask import Flask, render_template, request, redirect, url_for, session
from pymongo import MongoClient
from flask_session import Session
from datetime import datetime, timedelta
import io
from urllib.parse import unquote as urllib_unquote

app = Flask(__name__)
app.config["SESSION_TYPE"] = "filesystem"
app.jinja_env.globals.update(zip=zip, int=int, len=len)
Session(app)

@app.template_filter('unquote')
def unquote(url):
    safe = app.jinja_env.filters['safe']
    return safe(urllib_unquote(url))

client = MongoClient('mongodb://localhost:27017/')
db = client['BidHub']
user_collection = db['Users']
product_collection = db['Products']

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
        products = list(product_collection.find({'user_id':user['id']}))
        for product in products:
            if product['end_time'] < datetime.now():
                history = product['history']
                history.sort(key=lambda x: x['amount'], reverse=True)
                user_collection.update_one({'id': history[0]['user_id']}, {'$push': { 'owned_products': product}})
                user_collection.update_one({'id': history[0]['user_id']}, {'$inc': { 'total_spent': product['price']}})
                product_collection.delete_one({'product_id': product['product_id']})
                
        return redirect(url_for('buyer', name=name))
    else:
        return render_template('login.html', login_error='incorrect credentials')
    
@app.route('/register', methods=['GET', 'POST'])
def register():
    email = request.form.get('email')
    user = user_collection.find_one({'email': email})
    if user:
        return render_template('signup.html', signup_error='email already exists, try logging in')
    id = user_collection.count_documents({}) + 1
    name = request.form.get('name')
    password = request.form.get('password')
    phone = request.form.get('phone')
    address = request.form.get('address')
    user_collection.insert_one({
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
        'listings': 0})
    session['user_id'] = id
    return redirect(url_for('buyer', name=name))

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
            if listing['time_left'].days > 1:
                listing['is_editable'] = True
            else:
                listing['is_editable'] = False
    return render_template('listing.html', id=id, name=name, listings=listings)

@app.route('/product', methods=['GET', 'POST'])
def product():
    user_id = session['user_id']
    user = user_collection.find_one({'id': int(user_id)})
    name = user['name']
    if request.method == 'POST':
        product_id = product_collection.count_documents({}) + 1
        title = request.form['title']
        description = request.form['description']
        image_file = request.files['image']
        price = int(request.form['startingPrice'])
        duration = request.form['duration']
        category = request.form['category']
        condition = request.form['condition']

        end_time = datetime.now().replace(microsecond=0) + timedelta(days=int(duration))
        print(end_time)

        if image_file:
            image_data = image_file.read()
            product_collection.insert_one({
                'user_id': user_id,
                'product_id': product_id,
                'title': title,
                'description': description,
                'price': price,
                'end_time': end_time,
                'category': category,
                'condition': condition,
                'image': Binary(image_data),
                'history': [{
                    'user_id': session['user_id'],
                    'bidder': name,
                    'time': datetime.now().replace(microsecond=0),
                    'amount': price
                }]
            })
            user_collection.update_one({'id': user_id}, {'$inc': {'num_of_bids': 1, 'listings': 1}})
        return redirect(url_for('buyer', name=name))

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
    return render_template("modal.html", selected_product=product, name=name, products=products, time_lefts=time_lefts, histories=history)

@app.route('/bid', methods=['POST'])
def bid():
    product_id = request.args.get('product_id')
    price = request.form.get('bidAmount')
    product_collection.update_one({'product_id':int(product_id)}, {'$set': {'price': int(price)}})
    curr_time = datetime.now().replace(microsecond=0)
    name = user_collection.find_one({'id': int(session['user_id'])})['name']
    result = product_collection.update_one({'product_id': int(product_id)}, {'$push': { 'history': {'user_id': session['user_id'], 'bidder': name, 'time': curr_time, 'amount': int(price)}}})
    user_collection.update_one({'id': session['user_id']}, {'$inc': {'num_of_bids': 1}})
    print(result)
    return redirect(url_for('buyer'))

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
            if listing['time_left'].days > 1:
                listing['is_editable'] = True
            else:
                listing['is_editable'] = False
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
        for i in range(1,len(times)):
            gaps.append((times[i]-times[i-1]).seconds)
        print(gaps)
        bid_freq = int(sum(gaps)/len(gaps))
        bid_freq = f'{bid_freq//86400}d {(bid_freq % 86400)//3600}h'
    avg_bid = sum(bids)/len(bids)
    if product.get('image'):
        product['image_base64'] = b64encode(product['image']).decode('utf-8')
    return render_template('view_listing.html', product=product, avg_bid=avg_bid, bid_freq=bid_freq)

@app.route('/updateListing', methods=['POST'])
def updateListing():
    product_id = request.args.get('product_id')
    title = request.form['title']
    description = request.form['description']
    image_file = request.files['image']
    category = request.form['category']
    condition = request.form['condition']
    if image_file:
        image_data = image_file.read()
        product_collection.update_one({'product_id':int(product_id)}, {'$set': {
            'title': title,
            'description': description,
            'category': category,
            'condition': condition,
            'image': Binary(image_data),
        }})
    else:
        product_collection.update_one({'product_id':int(product_id)}, {'$set': {
            'title': title,
            'description': description,
            'category': category,
            'condition': condition,
        }})
    return redirect(url_for('listing'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.args.get('dashboard') == 'True':
        metrics = {}
        metrics['total_users'] = len(list(user_collection.find({})))
        metrics['total_auctions'] = len(list(product_collection.find({})))
        metrics['total_revenue'] = 0
        metrics['total_sales'] = 0
        for user in user_collection.find({}):
            metrics['total_revenue'] += user['total_spent']
            metrics['total_sales'] += len(user['owned_products'])
        metrics['total_revenue'] = int(metrics['total_revenue'] * 5/100)
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
    user_collection.delete_one({'id': int(user_id)})
    return redirect(url_for('admin', users=True))

@app.route('/delete_product', methods=['GET'])
def delete_product():
    product_id = request.args.get('product_id')
    product_collection.delete_one({'product_id': int(product_id)})
    return redirect(url_for('admin', products=True))

if __name__ == '__main__':
    app.run(debug=True)