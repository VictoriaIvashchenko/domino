import unittest
import json
from main import app, db, User, Board, generate_test_board

class FlaskTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
        self.app = app.test_client()
        with app.app_context():
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_register_user(self):
        response = self.app.post('/register', json={
            'username': 'testuser',
            'password': 'testpassword'
        })
        self.assertEqual(response.status_code, 201)
        self.assertIn('User registered successfully', response.get_json()['message'])

    def test_register_existing_user(self):
        user = User(username='testuser', password='testpassword')
        with app.app_context():
            db.session.add(user)
            db.session.commit()
        response = self.app.post('/register', json={
            'username': 'testuser',
            'password': 'testpassword'
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('Username already exists', response.get_json()['error'])

    def test_login_user(self):
        user = User(username='Mike')
        user.set_password('123')
        with app.app_context():
            db.session.add(user)
            db.session.commit()
        response = self.app.post('/login', json={
            'username': 'Mike',
            'password': '123'
        })
        self.assertEqual(response.status_code, 401)

    def test_login_invalid_user(self):
        response = self.app.post('/login', json={
            'username': 'invaliduser',
            'password': 'invalidpassword'
        })
        self.assertEqual(response.status_code, 401)
        self.assertIn('Invalid username or password', response.get_json()['error'])

    def test_generate_board(self):
        response = self.app.get('/generate_board')
        self.assertEqual(response.status_code, 200)
        self.assertIn('id', response.get_json())
        self.assertIn('board', response.get_json())

    def test_get_board(self):
        board = generate_test_board()
        board_entry = Board(initial_board=json.dumps(board))
        with app.app_context():
            db.session.add(board_entry)
            db.session.commit()
        response = self.app.get(f'/get_board/1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['initial_board'], board)


    def test_print_board(self):
        board = generate_test_board()
        response = self.app.post('/print_board', json={'board': board})
        self.assertEqual(response.status_code, 200)
        self.assertIn('board_str', response.get_json())

if __name__ == '__main__':
    unittest.main()
