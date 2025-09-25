from flask import Flask, render_template, request
from pymongo import MongoClient

app = Flask(__name__)

client = MongoClient('mongodb://localhost:27017/')
db = client['BidHub']
user_collection = db['Users']

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
    if user:
        return render_template('buyer.html', name=user['name'])
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
    return render_template('buyer.html', name=user_collection.find_one({'id': id})['name'])

@app.route('/buyer', methods=['GET', 'POST'])
def buyer():
    name = request.args['name']
    return render_template('buyer.html', name=name)

@app.route('/seller', methods=['GET','POST'])
def seller():
    name = request.args['name']
    return render_template('seller.html', name=name)

if __name__ == '__main__':
    app.run(debug=True)