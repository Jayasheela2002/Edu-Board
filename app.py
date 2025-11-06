from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from config import Config
from flask_socketio import SocketIO, join_room, leave_room, emit
import os
import random

# ------------------ APP & DB SETUP ------------------
app = Flask(__name__)
app.config.from_object(Config)

# configure upload folder (default 'uploads' unless overridden in Config)
app.config['UPLOAD_FOLDER'] = app.config.get('UPLOAD_FOLDER', 'uploads')
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ------------------ MANY-TO-MANY TABLE ------------------
board_collaborators = db.Table(
    'board_collaborators',
    db.Column('board_id', db.Integer, db.ForeignKey('board.id', ondelete="CASCADE"), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), primary_key=True)
)

# ------------------ MODELS ------------------
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    boards = db.relationship('Board', backref='owner', lazy=True, cascade="all, delete")


class Board(db.Model):
    __tablename__ = 'board'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    lists = db.relationship('List', backref='board', cascade="all, delete", lazy=True)
    collaborators = db.relationship('User', secondary=board_collaborators, backref='shared_boards', lazy='subquery')


class List(db.Model):
    __tablename__ = 'list'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    board_id = db.Column(db.Integer, db.ForeignKey('board.id', ondelete="CASCADE"), nullable=False)
    cards = db.relationship('Card', backref='list', cascade="all, delete", lazy=True, order_by="Card.position")


class Card(db.Model):
    __tablename__ = 'card'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    position = db.Column(db.Integer, default=0)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    list_id = db.Column(db.Integer, db.ForeignKey('list.id', ondelete="CASCADE"), nullable=False)

# ------------------ MOTIVATIONAL LINES ------------------
motivations = [
    "Push yourself — no one else will do it for you!",
    "Success is built one small step at a time.",
    "Dream big. Start small. Act now.",
    "Every day is progress — keep going!",
    "Your only limit is your effort today."
]

@app.context_processor
def inject_motivation():
    # A random motivational line injected into all templates as `motivation`
    return {'motivation': random.choice(motivations)}

# ------------------ LOGIN MANAGEMENT ------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ------------------ ROUTES ------------------
@app.route('/')
def home():
    return redirect(url_for('login'))

# ------------------ AUTH ------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        uname = request.form['username']
        pwd = request.form['password']

        if User.query.filter_by(username=uname).first():
            flash('Username already exists!')
            return redirect(url_for('register'))

        hashed_pwd = generate_password_hash(pwd)
        new_user = User(username=uname, password=hashed_pwd)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form['username']
        pwd = request.form['password']
        user = User.query.filter_by(username=uname).first()

        if user and check_password_hash(user.password, pwd):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials!')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('login'))

# ------------------ DASHBOARD ------------------
@app.route('/dashboard')
@login_required
def dashboard():
    owned = Board.query.filter_by(user_id=current_user.id).all()
    shared = current_user.shared_boards
    boards = owned + shared
    return render_template('dashboard.html', boards=boards)

# ------------------ BOARD CRUD ------------------
@app.route('/create_board', methods=['POST'])
@login_required
def create_board():
    name = request.form['board_name']
    new_board = Board(name=name, user_id=current_user.id)
    db.session.add(new_board)
    db.session.commit()
    flash("✅ Board created successfully!")
    # emit to all connected clients (dashboard refresh)
    socketio.emit('refresh_dashboard')
    return redirect(url_for('dashboard'))


@app.route('/update_board/<int:board_id>', methods=['POST'])
@login_required
def update_board(board_id):
    board = Board.query.get_or_404(board_id)
    if board.owner.id != current_user.id:
        flash("⚠️ Unauthorized action.")
        return redirect(url_for('dashboard'))
    board.name = request.form['board_name']
    db.session.commit()
    flash("✅ Board renamed successfully!")
    socketio.emit('refresh_dashboard')
    return redirect(url_for('dashboard'))


@app.route('/delete_board/<int:board_id>', methods=['POST'])
@login_required
def delete_board(board_id):
    board = Board.query.get_or_404(board_id)
    if board.owner.id != current_user.id:
        flash("⚠️ Unauthorized action.")
        return redirect(url_for('dashboard'))
    db.session.delete(board)
    db.session.commit()
    flash("🗑️ Board deleted successfully!")
    socketio.emit('refresh_dashboard')
    return redirect(url_for('dashboard'))

# ------------------ VIEW BOARD ------------------
@app.route('/board/<int:board_id>')
@login_required
def view_board(board_id):
    board = Board.query.get_or_404(board_id)
    if board.owner.id != current_user.id and current_user not in board.collaborators:
        flash("Access denied.")
        return redirect(url_for('dashboard'))
    lists = List.query.filter_by(board_id=board.id).all()
    return render_template('board.html', board=board, lists=lists)

# ------------------ COLLABORATORS ------------------
@app.route('/add_collaborator/<int:board_id>', methods=['POST'])
@login_required
def add_collaborator(board_id):
    board = Board.query.get_or_404(board_id)
    if board.owner.id != current_user.id:
        flash("Only board owners can add collaborators.")
        return redirect(url_for('view_board', board_id=board_id))

    username = request.form['username'].strip()
    user = User.query.filter_by(username=username).first()

    if not user:
        flash("❌ User not found!")
    elif user == board.owner or user in board.collaborators:
        flash("⚠️ User is already a collaborator or owner.")
    else:
        board.collaborators.append(user)
        db.session.commit()
        flash(f"✅ {username} added as collaborator!")
        socketio.emit('refresh_board', {'board_id': board_id}, room=f'board_{board_id}')

    return redirect(url_for('view_board', board_id=board_id))

# ------------------ LIST CRUD ------------------
@app.route('/add_list/<int:board_id>', methods=['POST'])
@login_required
def add_list(board_id):
    name = request.form['list_name']
    new_list = List(name=name, board_id=board_id)
    db.session.add(new_list)
    db.session.commit()
    flash("✅ List added successfully!")
    socketio.emit('refresh_board', {'board_id': board_id}, room=f'board_{board_id}')
    return redirect(url_for('view_board', board_id=board_id))


@app.route('/update_list/<int:list_id>', methods=['POST'])
@login_required
def update_list(list_id):
    list_item = List.query.get_or_404(list_id)
    list_item.name = request.form['list_name']
    db.session.commit()
    flash("✅ List updated successfully!")
    socketio.emit('refresh_board', {'board_id': list_item.board_id}, room=f'board_{list_item.board_id}')
    return redirect(url_for('view_board', board_id=list_item.board_id))


@app.route('/delete_list/<int:list_id>', methods=['POST'])
@login_required
def delete_list(list_id):
    list_item = List.query.get_or_404(list_id)
    board_id = list_item.board_id
    db.session.delete(list_item)
    db.session.commit()
    flash("🗑️ List deleted successfully!")
    socketio.emit('refresh_board', {'board_id': board_id}, room=f'board_{board_id}')
    return redirect(url_for('view_board', board_id=board_id))

# ------------------ CARD CRUD ------------------
@app.route('/add_card/<int:list_id>', methods=['POST'])
@login_required
def add_card(list_id):
    title = request.form['card_title']
    description = request.form.get('card_description', '')
    new_card = Card(title=title, description=description, list_id=list_id)
    db.session.add(new_card)
    db.session.commit()
    flash("✅ Card added successfully!")
    try:
        board_id = new_card.list.board_id
    except Exception:
        board_id = list_id
    socketio.emit('refresh_board', {'board_id': board_id}, room=f'board_{board_id}')
    return redirect(request.referrer)


@app.route('/update_card/<int:card_id>', methods=['POST'])
@login_required
def update_card(card_id):
    card = Card.query.get_or_404(card_id)
    card.title = request.form['card_title']
    card.description = request.form.get('card_description', '')
    db.session.commit()
    flash("✅ Card updated successfully!")
    socketio.emit('refresh_board', {'board_id': card.list.board_id}, room=f'board_{card.list.board_id}')
    return redirect(request.referrer)


@app.route('/delete_card/<int:card_id>', methods=['POST'])
@login_required
def delete_card(card_id):
    card = Card.query.get_or_404(card_id)
    board_id = card.list.board_id
    db.session.delete(card)
    db.session.commit()
    flash("🗑️ Card deleted successfully!")
    socketio.emit('refresh_board', {'board_id': board_id}, room=f'board_{board_id}')
    return redirect(request.referrer)

# ------------------ CARD MOVE ------------------
@app.route('/move_card/<int:card_id>/<int:new_list_id>', methods=['POST'])
@login_required
def move_card(card_id, new_list_id):
    data = request.get_json()
    new_position = data.get('new_position', 0)
    card = Card.query.get_or_404(card_id)
    new_list = List.query.get_or_404(new_list_id)

    if new_list.board.owner.id != current_user.id and current_user not in new_list.board.collaborators:
        return jsonify({"error": "Unauthorized"}), 403

    card.list_id = new_list_id
    card.position = new_position
    db.session.commit()

    socketio.emit('card_moved', {
        'card_id': card.id,
        'new_list_id': new_list_id,
        'board_id': new_list.board_id
    }, room=f'board_{new_list.board_id}')

    return jsonify({"message": "Card moved successfully"}), 200

# ------------------ FILE UPLOAD ------------------
@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    """
    Saves the uploaded file into app.config['UPLOAD_FOLDER'] and returns a JSON:
    { "file_url": "<absolute url to /uploads/<filename>>" }
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # secure and prefix filename to avoid collisions
    filename = secure_filename(file.filename)
    timestamp = int(datetime.utcnow().timestamp())
    final_name = f"{timestamp}_{filename}"
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], final_name)
    # ensure directory exists
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    file.save(save_path)

    # return absolute URL to the uploaded file (served by /uploads/<filename>)
    file_url = url_for('uploaded_file', filename=final_name, _external=True)
    return jsonify({'file_url': file_url}), 200

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # serve uploaded files
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ------------------ SOCKET.IO EVENTS ------------------
@socketio.on('join_board')
def handle_join(data):
    room = f"board_{data['board_id']}"
    join_room(room)
    print(f"🟢 Joined {room}")

@socketio.on('leave_board')
def handle_leave(data):
    room = f"board_{data['board_id']}"
    leave_room(room)
    print(f"🔴 Left {room}")

# Global dashboard / collaborators chat - single shared room for quick team chat
@socketio.on('join_collab')
def handle_join_collab(data):
    # clients on dashboard call this to join the global collab room
    room = 'collab_room'
    username = data.get('username', 'Anonymous')
    join_room(room)
    emit('message', {'username': 'System', 'message': f'{username} joined the collaboration chat.'}, room=room)

@socketio.on('leave_collab')
def handle_leave_collab(data):
    room = 'collab_room'
    username = data.get('username', 'Anonymous')
    leave_room(room)
    emit('message', {'username': 'System', 'message': f'{username} left the collaboration chat.'}, room=room)

@socketio.on('send_collab_message')
def handle_collab_message(data):
    """
    Accepts { username, message? , file? , filename? }
    Broadcasts to collab_room a payload containing the same keys that arrived
    """
    room = 'collab_room'
    username = data.get('username', 'Anonymous')
    message = data.get('message')
    file = data.get('file')
    filename = data.get('filename')

    payload = {'username': username}
    if message:
        payload['message'] = message
    if file:
        payload['file'] = file
        if filename:
            payload['filename'] = filename

    # broadcast to everyone in the room
    emit('message', payload, room=room)

# Per-board chat events (only members who joined the board room will receive)
@socketio.on('send_board_message')
def handle_board_message(data):
    # data: board_id, username, message
    board_id = data.get('board_id')
    if not board_id:
        return
    room = f'board_{board_id}'
    username = data.get('username', 'Anonymous')
    message = data.get('message', '')
    emit('board_message', {'board_id': board_id, 'username': username, 'message': message}, room=room)

# ------------------ RUN ------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Database ready with real-time collaboration and uploads.")
    # Use eventlet or gevent in production. For local dev, this runs fine.
    socketio.run(app, debug=True)
