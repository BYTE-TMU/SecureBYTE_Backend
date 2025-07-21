import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, request, jsonify
from flask_cors import CORS
import os

# Get the database URL from environment variable
SERVICE_ACCOUNT_PATH = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if not SERVICE_ACCOUNT_PATH:
    raise RuntimeError('FIREBASE_SERVICE_ACCOUNT environment variable not set.')

cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
DATABASE_URL = "https://byte-b61ba-default-rtdb.firebaseio.com/"
firebase_admin.initialize_app(cred, {
    'databaseURL': DATABASE_URL
})

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return 'Welcome to SecureBYTE Backend!'

@app.route('/items', methods=['POST'])
def create_item():
    data = request.json
    ref = db.reference('items')
    new_ref = ref.push(data)
    return jsonify({'id': new_ref.key, 'message': 'Item created'}), 201

@app.route('/items', methods=['GET'])
def get_items():
    ref = db.reference('items')
    items = ref.get() or {}
    result = [{'id': k, **v} for k, v in items.items()]
    return jsonify(result)

@app.route('/items/<item_id>', methods=['PUT'])
def update_item(item_id):
    data = request.json
    ref = db.reference(f'items/{item_id}')
    ref.update(data)
    return jsonify({'message': 'Item updated'})

@app.route('/items/<item_id>', methods=['DELETE'])
def delete_item(item_id):
    ref = db.reference(f'items/{item_id}')
    ref.delete()
    return jsonify({'message': 'Item deleted'})

if __name__ == '__main__':
    app.run(debug=True)
