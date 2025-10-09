from base64 import b64encode
from bson import Binary
from flask import Flask, render_template, request, redirect, url_for, session
from pymongo import MongoClient
from flask_session import Session
import io

app = Flask(__name__)
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

client = MongoClient('mongodb://localhost:27017/')
db = client['BidHub']
user_collection = db['Users']
product_collection = db['Products']

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    return render_template('signup.html')

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    username = request.form.get('username')
    password = request.form.get('password')
    user = user_collection.find_one({"username": username, "password": password})
    name = user['name']
    if user:
        session['user'] = user['id']
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
    user_collection.insert_one({'id': id, 'name': name, 'password': password, 'email': email})
    session['user'] = user['id']
    return redirect(url_for('buyer', name=name))

@app.route('/buyer', methods=['GET', 'POST'])
def buyer():
    id = session['user']
    name = user_collection.find_one({'id': int(id)})['name']
    products = list(db.Products.find())
    for product in products:
        if product.get('image'): 
            product['image_base64'] = b64encode(product['image']).decode('utf-8')
    return render_template('buyer.html', name=name, products=products)

@app.route('/seller', methods=['GET','POST'])
def seller():
    id = request.args['id']
    user = user_collection.find_one({'id': int(id)})
    name = user['name']
    return render_template('seller.html', id=id, name=name)

@app.route('/listing', methods=['GET','POST'])
def listing():
    id = request.args['id']
    user = user_collection.find_one({'id': int(id)})
    name = user['name']
    listings = list(product_collection.find({'user_id': int(id)}))
    for listing in listings:
        if listing.get('image'):
            listing['image_base64'] = b64encode(listing['image']).decode('utf-8')
        if int(listing['duration']) < 3:
            listing['is_editable'] = False
        else:
            listing['is_editable'] = True
        print(listing)
    return render_template('listing.html', id=id, name=name, listings=listings)

@app.route('/product', methods=['GET', 'POST'])
def product():
    user_id = int(request.args['user_id'])
    name = user_collection.find_one({'id': int(user_id)})['name']
    if request.method == 'POST':
        product_id = product_collection.count_documents({}) + 1
        title = request.form['title']
        description = request.form['description']
        image_file = request.files['image']
        price = int(request.form['startingPrice'])
        duration = request.form['duration']
        category = request.form['category']
        condition = request.form['condition']
        if image_file:
            image_data = image_file.read()
            product_collection.insert_one({
                'user_id': user_id,
                'product_id': product_id,
                'title': title,
                'description': description,
                'price': price,
                'duration': duration,
                'category': category,
                'condition': condition,
                'image': Binary(image_data)
            })
        return redirect(url_for('buyer', id=user_id, name=name))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    user_id = int(request.args['id'])
    user = user_collection.find_one({'id': user_id})
    return render_template('profile.html', user=user, edit=False)

if __name__ == '__main__':
    app.run(debug=True)