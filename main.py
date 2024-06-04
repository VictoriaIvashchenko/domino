from flask import Flask, request, jsonify, g
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from flasgger import Swagger, swag_from
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import json
import random
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///boards.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = secrets.token_urlsafe(16)  # Генеруємо випадковий секретний ключ
db = SQLAlchemy(app)
swagger = Swagger(app)

executor = ThreadPoolExecutor(max_workers=4)  # Створюємо пул потоків з 4 робочими потоками


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()

    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Invalid input"}), 400

    username = data['username']
    password = data['password']

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 400

    new_user = User(username=username)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({"message": "User registered successfully"}), 201


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()

    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid username or password'}), 401

    return jsonify({'message': 'Login successful'}), 200


# Функція-декоратор для перевірки авторизації
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'Authorization header is missing'}), 401

        token = auth_header.split(' ')[1]  # Отримуємо токен з заголовка Authorization

        if not token_is_valid(token):
            return jsonify({'error': 'Invalid token'}), 401

        g.current_user = get_user_from_token(token)  # Зберігаємо поточного користувача в глобальному контексті

        return f(*args, **kwargs)

    return decorated_function


class Board(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    initial_board = db.Column(db.Text, nullable=False)
    solved_board = db.Column(db.Text, nullable=True)

    def __init__(self, initial_board, solved_board=None):
        self.initial_board = initial_board
        self.solved_board = solved_board


def is_valid(board, x, y):
    return 0 <= x < len(board) and 0 <= y < len(board[0]) and board[x][y] == -1


def place_domino(board, x1, y1, x2, y2, v1, v2):
    board[x1][y1] = v1
    board[x2][y2] = v2


def remove_domino(board, x1, y1, x2, y2):
    board[x1][y1] = -1
    board[x2][y2] = -1


def find_empty(board):
    for x in range(len(board)):
        for y in range(len(board[0])):
            if board[x][y] == -1:
                return x, y
    return None


def solve_domino(board, dominoes):
    empty_pos = find_empty(board)
    if not empty_pos:
        return True

    x, y = empty_pos

    # Possible directions for placing a domino: right and down
    directions = [(0, 1), (1, 0)]
    for dx, dy in directions:
        nx, ny = x + dx, y + dy
        if is_valid(board, nx, ny):
            for i, (v1, v2) in enumerate(dominoes):
                place_domino(board, x, y, nx, ny, v1, v2)  # mark with domino index + 2
                remaining_dominoes = dominoes[:i] + dominoes[i + 1:]
                if solve_domino(board, remaining_dominoes):
                    return True
                remove_domino(board, x, y, nx, ny)

    return False


def print_board(board):
    horizontal_line = "+---" * len(board[0]) + "+"
    board_str = horizontal_line + "\n"
    for row in board:
        for cell in row:
            if cell == -1:
                board_str += "|   "
            elif cell == -2:
                board_str += "|   "
            else:
                board_str += f"| {cell} "
        board_str += "|\n" + horizontal_line + "\n"
    return board_str


def validate_board(board):
    if not isinstance(board, list):
        return False, "Board must be a list."
    for row in board:
        if not isinstance(row, list):
            return False, "Each row in the board must be a list."
        for cell in row:
            if not isinstance(cell, int):
                return False, "Each cell in the board must be an integer."
    return True, ""


def generate_test_board():
    rows = 11
    cols = 11
    board = [[-1 if random.random() > 0.3 else -2 for _ in range(cols)] for _ in range(rows)]
    return board


@app.route('/solve', methods=['POST'])
@swag_from({
    'tags': ['Domino Solver'],
    'description': 'Solve the domino board.',
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'integer', 'example': 1}
                }
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Successful response with the solved board.',
            'schema': {
                'type': 'object',
                'properties': {
                    'solution': {
                        'type': 'array',
                        'items': {
                            'type': 'array',
                            'items': {'type': 'integer'}
                        }
                    }
                }
            }
        },
        400: {
            'description': 'Invalid input or no solution found.',
            'schema': {
                'type': 'object',
                'properties': {
                    'error': {'type': 'string'}
                }
            }
        }
    }
})
def solve():
    if not request.is_json:
        return jsonify({"error": "Invalid input, JSON expected"}), 400

    data = request.get_json()
    board_id = data.get('id')

    if board_id is None:
        return jsonify({"error": "Board ID is required"}), 400

    board_entry = Board.query.get(board_id)
    if board_entry is None:
        return jsonify({"error": "Board not found"}), 404

    board = json.loads(board_entry.initial_board)

    dominoes = [(i, j) for i in range(7) for j in range(i, 7)]
    if solve_domino(board, dominoes):
        solved_board_str = json.dumps(board)
        board_entry.solved_board = solved_board_str
    else:
        board_entry.solved_board = "No solution exists"

    db.session.commit()
    return jsonify({"solution": board})


@app.route('/print_board', methods=['POST'])
@swag_from({
    'tags': ['Domino Solver'],
    'description': 'Print the domino board.',
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'board': {
                        'type': 'array',
                        'items': {
                            'type': 'array',
                            'items': {'type': 'integer'}
                        }
                    }
                }
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Successful response with the printed board.',
            'schema': {
                'type': 'object',
                'properties': {
                    'board_str': {'type': 'string'}
                }
            }
        },
        400: {
            'description': 'Invalid input.',
            'schema': {
                'type': 'object',
                'properties': {
                    'error': {'type': 'string'}
                }
            }
        }
    }
})
def print_board_endpoint():
    data = request.get_json()
    board = data.get('board')

    valid, error_message = validate_board(board)
    if not valid:
        return jsonify({"error": error_message}), 400

    board_str = print_board(board)
    return jsonify({"board_str": board_str})


@app.route('/generate_board', methods=['GET'])
@swag_from({
    'tags': ['Board Generator'],
    'description': 'Generate a new test board.',
    'responses': {
        200: {
            'description': 'Successful response with the generated board.',
            'schema': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'integer'},
                    'board': {
                        'type': 'array',
                        'items': {
                            'type': 'array',
                            'items': {'type': 'integer'}
                        }
                    }
                }
            }
        }
    }
})
def generate_board():
    board = generate_test_board()
    initial_board_str = json.dumps(board)
    board_entry = Board(initial_board=initial_board_str)

    db.session.add(board_entry)
    db.session.commit()

    return jsonify({"id": board_entry.id, "board": board})


@app.route('/get_board/<int:board_id>', methods=['GET'])
@swag_from({
    'tags': ['Board Retriever'],
    'description': 'Retrieve a board by ID.',
    'parameters': [
        {
            'name': 'board_id',
            'in': 'path',
            'required': True,
            'type': 'integer',
            'description': 'The ID of the board to retrieve.'
        }
    ],
    'responses': {
        200: {
            'description': 'Successful response with the board data.',
            'schema': {
                'type': 'object',
                'properties': {
                    'initial_board': {
                        'type': 'array',
                        'items': {
                            'type': 'array',
                            'items': {'type': 'integer'}
                        }
                    },
                    'solved_board': {
                        'type': 'array',
                        'items': {
                            'type': 'array',
                            'items': {'type': 'integer'}
                        }
                    }
                }
            }
        },
        404: {
            'description': 'Board not found.',
            'schema': {
                'type': 'object',
                'properties': {
                    'error': {'type': 'string'}
                }
            }
        }
    }
})
def get_board(board_id):
    board_entry = Board.query.get(board_id)
    if board_entry is None:
        return jsonify({"error": "Board not found"}), 404

    initial_board = json.loads(board_entry.initial_board)
    solved_board = json.loads(board_entry.solved_board) if board_entry.solved_board else None

    return jsonify({"initial_board": initial_board, "solved_board": solved_board})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
