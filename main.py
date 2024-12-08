from flask import Flask, render_template, request, session, redirect, url_for
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import random

app = Flask(__name__)
CORS(app)
app.secret_key = 'your_secret_key'
socketio = SocketIO(app)

lobby_users = []  # List to keep track of all users in the lobby
host_connected = False  # Variable to check if host is connected

current_question_index = 0
answers = {}  # Dictionary to store player answers
self_scores = {}  # Track SELF scores for each player
collective_score = 4  # Track COLLECTIVE score
players_answered = set()  # Track players who have answered
victims = ["null", "null"]  # Track players who have been hurt


# prisoner: 0 is defect, 1 is cooperate.
# risk: 1 is risk, 0 is safety.
# donate: 1 is donate, 0 is keep.

#prisoner, risk, donate, donate, prisoner.

questions = {
    "The Octet finds an untouched supply of MegaCorp tv dinners.": {"Eat your fill only.": 1, "Eat and take extras for later.": 0},
    "Riots are breaking out over dwindling resources after mega corp declares that food is now for upper management only.": {"Join the resistance.": 1, "Stay back.": 0},
    str("Player(s) "+ victims[-1]+ " and "+ victims[-2]+ " were injured by a Megacorp brand Ai policebot while fleeing from the riots.") : {"Trade 1 self point for a medical kit to treat them.": 1, "Do nothing.": 0},
    "Runoff from a megacorp factory has turned your drinking water purple.": {"Spend 4 collective points for a filter.": 0, "Just drink it.": 1},
    "A large resistance group is planning to storm the Megacorp HQ in a last stand." : {"Join them.": 0, "Stay back.": 1},
}



@app.route('/host')
def host():
    global host_connected
    host_connected = True
    return render_template('host.html')

@app.route('/', methods=['GET', 'POST'])
def index():
    error_message = None
    if request.method == 'POST':
        username = request.form['username'].strip()
        if username in lobby_users:
            error_message = "Name already taken"
        else:
            session['username'] = username
            lobby_users.append(username)
            self_scores[username] = 2  # Initialize SELF scores
            return redirect('/lobby')
    return render_template('index.html', error=error_message)

@app.route('/lobby')
def lobby():
    if 'username' not in session:
        return redirect('/')
    return render_template('lobby.html', username=session['username'])

@socketio.on('join')
def on_join(data):
    username = session.get('username')
    if username:
        emit(
            'update_users',
            {
                'users': lobby_users,
                'self_scores': self_scores,
            },
            broadcast=True,
        )

@socketio.on('leave')
def on_leave():
    username = session.get('username')
    if username:
        lobby_users.remove(username)
        self_scores.pop(username, None)
        session.pop('username', None)
    emit('update_users', {'users': lobby_users}, broadcast=True)
    leave_room('lobby')

@socketio.on('disconnect')
def on_disconnect():
    global host_connected
    username = session.get('username')
    if username:
        lobby_users.remove(username)
        self_scores.pop(username, None)
        session.pop('username', None)
        emit('update_users', {'users': lobby_users}, broadcast=True)
    elif request.sid == 'host':  # If host disconnects
        host_connected = False

@socketio.on('start_game')
def handle_start_game():
    global current_question_index, answers, players_answered, collective_score
    current_question_index = 0
    answers.clear()
    players_answered.clear()
    collective_score = 4  # Reset collective score
    for user in lobby_users:
        self_scores[user] = 2  # Reset SELF scores

    question_text = list(questions.keys())[current_question_index]
    options = list(questions[question_text].keys())
    emit(
        'game_question',
        {
            'question': question_text,
            'options': options,
            'self_score': 2,
            'collective_score': 4,
        },
        broadcast=True,
    )

@socketio.on('submit_answer')
def handle_submit_answer(data):
    username = session.get('username')
    choice = data['choice']
    question_text = list(questions.keys())[current_question_index]
    options = list(questions[question_text].keys())
    answer = options[choice]

    if username not in players_answered:
        players_answered.add(username)
        answers[username] = questions[question_text][answer]

        # Notify the host
        emit('update_answers', {'user': username, 'choice': choice}, broadcast=True)

        # Check if all players have answered
        if len(players_answered) == len(lobby_users):
            calculate_scores_and_announce_results()

def calculate_scores_and_announce_results():
    global current_question_index, collective_score, victims

    # run timer

    # question 1: prisoner's dilemma
    if current_question_index == 0:
        # tally

        # in this case risk means eat, safety means eat and take extra.
        risk_count = sum(1 for value in answers.values() if value == 1)
        safety_count = len(answers) - risk_count

        if risk_count > safety_count:
            majority_decision = f"Most ate their fill. +1 to members who ate their fill and +2 to members who took extra. +1 to the collective."
        
            # calc scores
            for user, value in answers.items():
                    if value == 0:
                        self_scores[user] += 2
                    if value == 1:
                        self_scores[user] += 1
            collective_score += 1
        
        elif safety_count > risk_count:
            majority_decision = f"Most tried to take extra food, creating a shortage. +1 to members who managed to take extra. -1 to the collective."

            for user, value in answers.items():
                    if value == 0:
                        self_scores[user] += 1
                    if value == 1:
                        self_scores[user] -= 1
            collective_score -= 1

        else:
            majority_decision = f"Most tried to take extra food, creating a shortage. +1 to members who managed to take extra. -1 to the collective."

            for user, value in answers.items():
                    if value == 0:
                        self_scores[user] += 1
                    if value == 1:
                        self_scores[user] -= 1
            collective_score -= 1

    # question 2: risk vs safety
    elif current_question_index == 1:
        # tally
        risk_count = sum(1 for value in answers.values() if value == 1)
        safety_count = len(answers) - risk_count

        if risk_count == 0:
            majority_decision = f"No one joined the riot for resources. The octet is starving. -1 to all members and -2 to the collective."

            # calc scores
            for user, value in answers.items():
                    self_scores[user] -= 1
            collective_score -= 2

        elif risk_count > safety_count:
            majority_decision = f"Most joined the riot and acquired extra food, avoiding injury through safety in numbers. +1 to all members and +2 to the collective."
        
            # calc scores
            for user, value in answers.items():
                    self_scores[user] += 1
            collective_score += 2
        
        elif safety_count > risk_count:
            majority_decision = f"Only {risk_count} joined the riot, risking injury going out for food without enough help. -3 to those members and -1 to the collective."

            for user, value in answers.items():
                    if value == 0:
                        self_scores[user] -= 3
                        victims += user
            collective_score -= 2

        else:
            majority_decision = f"Only {risk_count} joined the riot, risking injury going out for food without enough help. -3 to those members and -1 to the collective."

            for user, value in answers.items():
                    if value == 0:
                        self_scores[user] -= 3
                        victims += user
            collective_score -= 2

    # question 3: donate vs keep
    elif current_question_index == 2:

        #points needed to heal victims:
        points_needed = 3 * len(victims)-2

        for user, value in answers.items():
            if value == 1: # donated points
                        self_scores[user] -= 1
                        points_needed -= 1
        
        if points_needed > 0:
            majority_decision = f"Not enough points were spent to heal to the injured member, and they perished. -2 to the collective."
            collective_score -= 2
        else:
            majority_decision = f"Enough points were spent to heal the injured member. +2 to the collective."
            collective_score += 2

    # question 4: buy a water filter?
    elif current_question_index == 3:
        # in this case risking it is bad.
        risk_count = sum(1 for value in answers.values() if value == 1)
        safety_count = len(answers) - risk_count

        if risk_count > safety_count:
            majority_decision = f"Most voted to drink the water, but some got sick. -1 or -2 to all members."
        
            # calc scores
            for user, value in answers.items():
                    self_scores[user] -= 1
        
        elif safety_count > risk_count:
            majority_decision = f"Most voted to spend collective points on a water filter and no one gets sick. + 1 to all members and -4 to the collective"

            for user, value in answers.items():
                    self_scores[user] += 1
                    victims += user
                    collective_score -= 4

        else:
            majority_decision = f"Most voted to spend collective points on a water filter and no one gets sick. + 1 to all members and -4 to the collective"

            for user, value in answers.items():
                    self_scores[user] += 1
                    victims += user
                    collective_score -= 4
    
    # final prisoner's dilemma!
    elif current_question_index == 4:
        # tally
        risk_count = sum(1 for value in answers.values() if value == 1)
        safety_count = len(answers) - risk_count

        if risk_count == 0:
            majority_decision = f"No one joined the final revolution. The octet continues to live under oppression. -4 to the collective."
            collective_score -= 4

        elif safety_count == 0:
            majority_decision = f"All members joined the revolution, and ended MegaCorp's resource monopoly with their collective strength. +2 to all members and +4 to the collective."
            collective_score += 4
            for user, value in answers.items():
                    self_scores[user] += 2

        # a few members defect
        else:
            majority_decision = f"Only some members joined the revolution, but without the strength of the entire octet, were crushed by Megacorp. -3 to revolutionaries, +3 to defectors, and -2 to the collective."

            for user, value in answers.items():
                    if value == 0:
                        self_scores[user] += 3
                    elif value == 1:
                         self_scores[user] -= 3
            collective_score -= 2
             
            

    # Check if this is the last question
    is_last_question = current_question_index == len(questions) - 1

    emit(
        'show_results',
        {
            'majority_decision': majority_decision,
            'self_scores': self_scores,
            'collective_score': collective_score,
            'is_last_question': is_last_question,
        },
        broadcast=True,
    )

def calculate_prisoner_dilemma():

     # Tally defectors and cooperators
    defect_count = sum(1 for value in answers.values() if value == 0)
    cooperate_count = len(answers) - defect_count

    # Determine majority decision
    if defect_count > cooperate_count:
        majority_decision = f"{defect_count} people defected"
    elif cooperate_count > defect_count:
        majority_decision = f"{cooperate_count} people cooperated"
    else:
        majority_decision = f"{defect_count} people defected"

    # Update Collective score
    if cooperate_count > defect_count:
        collective_score += 1
    else:
        collective_score -= 1

    # Update Self scores for each player
    for user, value in answers.items():
        if cooperate_count > defect_count:
            if value == 0:  # Player defected
                self_scores[user] += 2
            elif value == 1:  # Player cooperated
                self_scores[user] += 1
        else:  # Cooperators <= Defectors
            if value == 0:  # Player defected
                self_scores[user] += 0
            elif value == 1:  # Player cooperated
                self_scores[user] -= 1

def hurt_random():
    victim = random.choice(lobby_users)
    victim.self_scores[victim] -= 4  # Victim loses 4 points

@socketio.on('next_question')
def handle_next_question():
    global current_question_index, answers, players_answered
    current_question_index += 1
    if current_question_index < len(questions):
        answers.clear()
        players_answered.clear()

        question_text = list(questions.keys())[current_question_index]
        options = list(questions[question_text].keys())
        emit(
            'game_question',
            {
                'question': question_text,
                'options': options,
                'self_score': 0,
                'collective_score': collective_score,
            },
            broadcast=True,
        )
    else:
        emit('end_game', {}, broadcast=True)  # End the game

if __name__ == '__main__':
    socketio.run(app, port=9629, debug=True) 
