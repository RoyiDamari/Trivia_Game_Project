import pytest
import os
import bcrypt
import base64
import random
from pymongo import MongoClient
from psycopg2 import connect
from psycopg2.extensions import connection as pg_connection
from pymongo.errors import PyMongoError
from login_and_registration import create_new_player, player_login
from game_logic import game_status, fetch_questions_mongo, play_game, finalize_game
from statistics import execute_statistics_procedure
from statistical_graphs import (generate_player_answered_vs_not_answered_pie_chart,
                                generate_player_correct_incorrect_pie_chart, generate_question_statistics_graph)
from unittest.mock import patch
from typing import Any


# Use the actual connection function to keep the connection logic consistent
def connect_to_pg() -> pg_connection:
    """
    Connect to PostgreSQL.
    :return: PostgreSQL connection object.
    """
    return connect(
        host=os.getenv("POSTGRES_HOST"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        port=os.getenv("POSTGRES_PORT")
    )


def connect_to_mongo() -> tuple[MongoClient, Any]:
    """
    Connect to MongoDB.
    :return: Tuple containing MongoDB client and database object.
    """
    try:
        # Load MongoDB settings from .env file
        host = os.getenv("MONGO_HOST")
        port = int(os.getenv("MONGO_PORT"))
        username = os.getenv("MONGO_USERNAME")
        password = os.getenv("MONGO_PASSWORD")
        database_name = os.getenv("MONGO_DB")

        # Establish MongoDB connection
        client = MongoClient(host=host, port=port, username=username, password=password)
        db = client[database_name]
        return client, db
    except PyMongoError as e:
        print(f"Error connecting to MongoDB: {e}")
        raise


# Fixtures using the real connection functions
@pytest.fixture(scope="module")
def pg_connection():
    connection = connect_to_pg()
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def mongo_db():
    client, db = connect_to_mongo()
    yield db
    client.close()  # Close the connection but do not drop the database


@pytest.fixture(scope="function")
def reset_db_state(pg_connection, mongo_db):
    """
    Reset player-related data in PostgreSQL and MongoDB while keeping shared questions intact.
    """
    # Clear player-related tables
    with pg_connection.cursor() as cursor:
        cursor.execute("DELETE FROM players;")
        cursor.execute("DELETE FROM player_answers;")
        cursor.execute("DELETE FROM game_sessions;")
    pg_connection.commit()

    # Clear action history in MongoDB
    mongo_db.action_history.delete_many({})


@pytest.fixture(scope="module", autouse=True)
def setup_questions(pg_connection, mongo_db):
    """
    Delete existing questions and prepopulate shared questions into PostgreSQL and MongoDB.
    """
    # Delete existing questions from PostgreSQL
    with pg_connection.cursor() as cursor:
        cursor.execute("DELETE FROM questions;")
    pg_connection.commit()

    # Delete existing questions from MongoDB
    mongo_db.questions.delete_many({})

    # Add shared questions
    add_questions_once(pg_connection, mongo_db)


def add_existing_player(pg_connection, username="existing_user", password="ValidPass@123",
                        purpose="create_new_player") -> int:
    """
    Adds a player to the PostgreSQL database for testing purposes.

    :param pg_connection: PostgreSQL connection object.
    :param username: Username to add.
    :param password: Password to add.
    :param purpose: Purpose of adding the player ("create_new_player" or "player_login").
    :return: The player_id of the newly created player.
    """
    if purpose == "player_login":
        hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        encoded_password = base64.b64encode(hashed_password).decode('utf-8')
    else:
        encoded_password = "hashed_password"  # Static placeholder since we are not testing password hashing here

    age = 25  # Default age for test users
    email = f"{username}@example.com"  # Generate a unique email based on the username

    with pg_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO players (username, password, email, age)
            VALUES (%s, %s, %s, %s)
            RETURNING player_id;
            """,
            (username, encoded_password, email, age)
        )
        player_id = cursor.fetchone()[0]  # Retrieve the player_id of the newly inserted player
    pg_connection.commit()
    return player_id


def add_questions_once(pg_connection, mongo_db):
    """
    Insert a predefined set of questions into PostgreSQL and MongoDB if not already present.
    """
    question_ids = list(range(1, 21))  # Predefined question IDs
    with pg_connection.cursor() as cursor:
        # Check if questions already exist in PostgreSQL
        cursor.execute("SELECT COUNT(*) FROM questions;")
        count = cursor.fetchone()[0]
        if count == 0:
            for question_id in question_ids:
                cursor.execute(
                    """
                    INSERT INTO questions (question_id, correct_answer)
                    VALUES (%s, %s);
                    """,
                    (question_id, 'a')  # Default correct answer
                )
            pg_connection.commit()

    # Insert into MongoDB if not already present
    for question_id in question_ids:
        if not mongo_db.questions.find_one({"question_id": question_id}):
            mongo_db.questions.insert_one({
                "question_id": question_id,
                "question_text": f"Question {question_id}",
                "answer_a": "Option A",
                "answer_b": "Option B",
                "answer_c": "Option C",
                "answer_d": "Option D",
                "correct_answer": "a"  # Default correct answer
            })


def create_session_for_player(pg_connection, username):
    """
    Create a new game session for a player using the predefined questions.
    """
    with pg_connection.cursor() as cursor:
        # Get player_id
        cursor.execute("SELECT player_id FROM players WHERE username = %s;", (username,))
        player_id = cursor.fetchone()[0]

        # Deactivate previous sessions
        cursor.execute(
            """
            UPDATE game_sessions
            SET is_active = FALSE
            WHERE player_id = %s AND is_active = TRUE;
            """,
            (player_id,)
        )

        # Create a new session and mark it active
        cursor.execute(
            """
            INSERT INTO game_sessions (player_id, is_active)
            VALUES (%s, TRUE);
            """,
            (player_id,)
        )

    pg_connection.commit()


def add_player_answers(pg_connection, username, question_ids, correct_indices=None):
    """
    Adds answers for a player in the player_answers table.

    :param pg_connection: PostgreSQL connection object.
    :param username: Username of the player.
    :param question_ids: Specific question IDs to insert answers for (must match database IDs).
    :param correct_indices: List of indices indicating which answers should be correct.
                            If None, answers are randomized. If provided, only those indices will be marked as correct.
    """
    with pg_connection.cursor() as cursor:
        # Get player_id
        cursor.execute("SELECT player_id FROM players WHERE username = %s;", (username,))
        player_id = cursor.fetchone()[0]

        # Get active session_id
        cursor.execute("SELECT session_id FROM game_sessions WHERE player_id = %s AND is_active = TRUE;", (player_id,))
        session_id = cursor.fetchone()[0]

        # Insert answers into player_answers table
        for idx, question_id in enumerate(question_ids):
            if correct_indices is not None:
                # Use specified indices to determine correctness
                is_correct = idx in correct_indices
                selected_answer = 'a' if is_correct else random.choice(['b', 'c', 'd'])
            else:
                # Randomize answers
                correct_answer = 'a'
                selected_answer = random.choice(['a', 'b', 'c', 'd'])
                is_correct = (selected_answer == correct_answer)

            cursor.execute(
                """
                INSERT INTO player_answers (player_id, question_id, session_id, selected_answer, is_correct, 
                answered_at)
                VALUES (%s, %s, %s, %s, %s, NOW());
                """,
                (player_id, question_id, session_id, selected_answer, is_correct)
            )
    pg_connection.commit()


# Tests for questions_solved trigger in game_sessions table
def test_trigger_update_game_sessions(pg_connection, reset_db_state):
    """
    Test the trigger `trg_update_game_sessions` to verify that the `questions_solved` column
    in the `game_sessions` table increments by 1 for every new entry in the `player_answers` table.
    """
    # Add a test player
    username = "test_player"
    add_existing_player(pg_connection, username=username, purpose="create_new_player")

    # Create a game session for the player
    create_session_for_player(pg_connection, username)

    # Define question IDs to be inserted one by one
    question_ids = list(range(1, 21))  # Assume 20 questions exist in the `questions` table

    # Insert answers and validate `questions_solved` increment in each iteration
    for i in range(len(question_ids)):
        question_id = question_ids[i]

        # Insert the answer into `player_answers`
        add_player_answers(pg_connection=pg_connection, username=username, question_ids=[question_id])

        # Check `questions_solved` in `game_sessions`
        with pg_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT questions_solved
                FROM game_sessions;
                """
            )
            questions_solved = cursor.fetchone()[0]

            # Assert `questions_solved` matches the number of inserted answers
            assert questions_solved == i + 1


# Tests for functions in login_and_registration file
def test_check_unique_username(pg_connection, reset_db_state):
    """
    Test the stored procedure 'check_unique_username' to ensure it correctly identifies unique and non-unique usernames.
    """
    # Add an existing user
    add_existing_player(pg_connection, username="existing_user", purpose="create_new_player")

    # Test that a new username is recognized as unique
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT fn_check_unique_username(%s);", ("new_user",))
        result = cursor.fetchone()
        assert result[0] is True

    # Test that an existing username is not recognized as unique
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT fn_check_unique_username(%s);", ("existing_user",))
        result = cursor.fetchone()
        assert result[0] is False


def test_check_unique_email(pg_connection, reset_db_state):
    """
    Test the stored procedure 'check_unique_email' to ensure it correctly identifies unique and non-unique emails.
    """
    # Add an existing user with a unique email
    existing_email = "user1@example.com"
    add_existing_player(pg_connection, username="user1", purpose="create_new_player")

    # Test that a new email is recognized as unique
    new_email = "new_email@example.com"

    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT fn_check_unique_email(%s);", (new_email,))
        result = cursor.fetchone()
        assert result[0] is True

    # Test that an existing email is not recognized as unique
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT fn_check_unique_email(%s);", (existing_email,))
        result = cursor.fetchone()
        assert result[0] is False


def test_create_new_player_success(pg_connection, mongo_db, reset_db_state):
    """
    Test the full interaction between the Python function, PostgreSQL, and MongoDB during player creation.
    """
    # Inputs for create_new_player
    user_inputs = [
        "test_user",  # Username (should be unique)
        "ValidPass@123",  # Password
        "ValidPass@123",  # Confirm password
        "test_user@email.com",  # Email (should be unique)
        "25"  # Age
    ]

    with patch('login_and_registration.get_valid_input', side_effect=user_inputs):
        # Run the create_new_player function
        result = create_new_player(pg_connection, mongo_db)

        # Verify that the function returned the expected username
        assert result == "test_user"

        # Verify PostgreSQL interaction: Check if the player was added to the database
        with pg_connection.cursor() as cursor:
            cursor.execute("SELECT * FROM players WHERE username = %s;", (result,))
            player = cursor.fetchone()
            assert player[1] == "test_user"

        # Verify MongoDB interaction: Check if the action was logged correctly
        logged_action = mongo_db.action_history.find_one({"username": "test_user"})
        assert logged_action['action'] == "User Register"
        assert logged_action['description'] == "New player has been signed up."
        assert logged_action['email'] == "test_user@email.com"


def test_player_login_success(pg_connection, mongo_db, reset_db_state):
    """
    Test the full interaction between the Python function, PostgreSQL, and MongoDB during player login.
    """
    # Add an existing player for the test
    add_existing_player(pg_connection, username="existing_user", password="ValidPass@123", purpose="player_login")

    # Inputs for player_login
    user_inputs = [
        "existing_user",  # Username
        "ValidPass@123"  # Password
    ]

    with patch('login_and_registration.get_valid_input', side_effect=user_inputs):
        # Mock the game_status function to return the username without executing its actual logic
        with patch('login_and_registration.game_status', return_value="existing_user"):
            # Run the player_login function
            result = player_login(pg_connection, mongo_db)

            # Verify that the function returned the expected result (player's username)
            assert result == "existing_user"

            # Verify MongoDB interaction: Check if the login action was logged correctly
            logged_action = mongo_db.action_history.find_one({"username": "existing_user"})
            assert logged_action['action'] == "User Login"
            assert logged_action['description'] == "Player successfully logged in."


def test_player_login_username_not_exist(pg_connection, mongo_db, reset_db_state):
    """
    Test the login failure process due to username who does not exist in the system.
    """
    # Inputs for player_login
    user_inputs = [
        "user_not_exist",  # Username Not Exist
        "ValidPass@123",  # Password
        "n"  # Quit after failed login attempt
    ]

    with patch('login_and_registration.get_valid_input', side_effect=user_inputs):

        # Run the player_login function
        result = player_login(pg_connection, mongo_db)

        # Verify that the function returned None (indicating failed login)
        assert result is None

        # Verify MongoDB interaction: Check if the failed login action was logged correctly
        logged_action = mongo_db.action_history.find_one({"username": "user_not_exist"})
        assert logged_action['action'] == "Login Failed"
        assert logged_action['description'] == "Failed login attempt."


def test_player_login_incorrect_username(pg_connection, mongo_db, reset_db_state):
    """
    Test the login failure process due to incorrect username input.
    """
    # Add an existing player for the test
    add_existing_player(pg_connection, username="existing_user", password="ValidPass@123", purpose="player_login")

    # Inputs for player_login
    user_inputs = [
        "incorrect_user",  # Incorrect Username
        "ValidPass@123",  # Password
        "n"  # Quit after failed login attempt
    ]

    with patch('login_and_registration.get_valid_input', side_effect=user_inputs):

        # Run the player_login function
        result = player_login(pg_connection, mongo_db)

        # Verify that the function returned None (indicating failed login)
        assert result is None

        # Verify MongoDB interaction: Check if the failed login action was logged correctly
        logged_action = mongo_db.action_history.find_one({"username": "incorrect_user"})
        assert logged_action['action'] == "Login Failed"
        assert logged_action['description'] == "Failed login attempt."


def test_player_login_incorrect_password(pg_connection, mongo_db, reset_db_state):
    """
    Test the login failure process due to incorrect password input.
    """
    # Add an existing player for the test
    add_existing_player(pg_connection, username="existing_user", password="ValidPass@123", purpose="player_login")

    # Inputs for player_login
    user_inputs = [
        "existing_user",  # Incorrect Username
        "UnValidPass@123",  # Incorrect Password
        "n"  # Quit after failed login attempt
    ]

    with patch('login_and_registration.get_valid_input', side_effect=user_inputs):

        # Run the player_login function
        result = player_login(pg_connection, mongo_db)

        # Verify that the function returned None (indicating failed login)
        assert result is None

        # Verify MongoDB interaction: Check if the failed login action was logged correctly
        logged_action = mongo_db.action_history.find_one({"username": "existing_user"})
        assert logged_action['action'] == "Login Failed"
        assert logged_action['description'] == "Failed login attempt."


# Tests for functions in game_logic file
def test_game_status_game_start_success(pg_connection, mongo_db, reset_db_state):
    """
    Test the stored procedure 'check_unanswered' to ensure it correctly returns unanswered questions
    and the game start successfully.
    """
    username = "new_player"
    # Add player
    add_existing_player(pg_connection, username=username, purpose="create_new_player")

    # Mock play_game to simulate its behavior
    with patch("game_logic.play_game", return_value=None) as mock_play_game:
        # Call game_status function to initialize the game flow
        result = game_status(pg_connection, mongo_db, username)
        assert result == "new_player"

    # Run the stored procedure to check unanswered questions
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_unanswered_questions(%s);", ("new_player",))
        unanswered_questions = cursor.fetchall()

    # Verify questions are fetched from MongoDB
    question_ids = [qid[0] for qid in unanswered_questions]

    # Assert the returned questions list (should be 20 unanswered questions)
    assert len(question_ids) == 20

    # Verify questions are fetched from MongoDB
    questions = fetch_questions_mongo(mongo_db, question_ids)
    assert len(questions) == 20

    # Verify play_game was called with the correct remaining questions
    mock_play_game.assert_called_once_with(pg_connection, "new_player", mongo_db, questions)

    # Verify the 'start_game' action was logged in MongoDB
    logged_action = mongo_db.action_history.find_one({"username": "new_player"})
    assert logged_action['action'] == "Game Start"
    assert logged_action['description'] == "The player has started the game."


def test_game_status_continue_game_success(pg_connection, mongo_db, reset_db_state):
    """
    Test the process of a player logging in, answering 5 questions, quitting, and then continuing the game.
    """
    username = "test_player"

    # Add player
    add_existing_player(pg_connection, username=username, purpose="create_new_player")

    # Create a new session for the player
    create_session_for_player(pg_connection, username)

    # Simulate the player answering the first 5 questions
    add_player_answers(pg_connection, username, question_ids=list(range(1, 6)))

    # Mock player login inputs
    login_inputs = [
        "y"  # Continue the game
    ]

    with patch("game_logic.get_valid_input", side_effect=login_inputs):
        # Mock play_game to simulate answering questions
        with patch("game_logic.play_game", return_value=None) as mock_play_game:
            # Call game_status function
            result = game_status(pg_connection, mongo_db, username)
            assert result == "test_player"

        # Verify the game was resumed with the correct questions
        with pg_connection.cursor() as cursor:
            cursor.execute("SELECT * FROM fn_get_unanswered_questions(%s);", ("test_player",))
            unanswered_questions = cursor.fetchall()

        # Verify questions are fetched from MongoDB
        question_ids = [qid[0] for qid in unanswered_questions]

        # Assert the returned questions list (should be 15 unanswered questions)
        assert len(question_ids) == 15

        # Verify questions are fetched from MongoDB
        questions = fetch_questions_mongo(mongo_db, question_ids)
        assert len(questions) == 15

        # Verify play_game was called with the correct remaining questions
        mock_play_game.assert_called_once_with(pg_connection, "test_player", mongo_db, questions)

        # Verify the 'continue_game' action was logged in MongoDB
        logged_action = mongo_db.action_history.find_one({"username": "test_player"})
        assert logged_action['action'] == "Game Continue"
        assert logged_action['description'] == "The player has continued the game."


def test_game_status_reset_game_success(pg_connection, mongo_db, reset_db_state):
    """
    Test the process where a player chooses not to continue the game, triggers reset_game,
    and starts a new game with fresh questions.
    """
    username = "test_player"

    # Add player
    player_id = add_existing_player(pg_connection, username=username, purpose="create_new_player")

    # Create a new session for the player
    create_session_for_player(pg_connection, username)

    # Simulate the player answering the first 5 questions
    add_player_answers(pg_connection, username, question_ids=list(range(1, 6)))

    # Mock player input to choose "no" when prompted to continue the game
    login_inputs = [
        "n"  # Choose not to continue the game
    ]

    with patch("game_logic.get_valid_input", side_effect=login_inputs):
        # Mock play_game to simulate the new game process
        with patch("game_logic.play_game", return_value=None) as mock_play_game:
            # Call game_status function, which internally calls reset_game
            result = game_status(pg_connection, mongo_db, username)

            # Assert the correct username is returned
            assert result == "test_player"

            # Verify that the reset_game function executed correctly
            # Ensure player's answers were deleted by the procedure
            with pg_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM player_answers WHERE player_id = %s;", (player_id,)
                )
                player_answers = cursor.fetchall()
                assert len(player_answers) == 0

            # Ensure reset_game action was logged in MongoDB
            reset_log = mongo_db.action_history.find_one({"username": "test_player"})
            assert reset_log['action'] == "Game Reset"
            assert reset_log['description'] == "The game has been reset."

            # Verify new questions are generated for the player
            with pg_connection.cursor() as cursor:
                cursor.execute("SELECT * FROM fn_get_unanswered_questions(%s);", (username,))
                unanswered_questions = cursor.fetchall()

            question_ids = [qid[0] for qid in unanswered_questions]
            assert len(question_ids) == 20

            # Ensure questions are fetched from MongoDB
            questions = fetch_questions_mongo(mongo_db, question_ids)
            assert len(questions) == 20

            # Ensure play_game was called with the new set of questions
            mock_play_game.assert_called_once_with(pg_connection, "test_player", mongo_db, questions)

            # Ensure start_game action was logged in MongoDB
            start_log = mongo_db.action_history.find_one({"username": "test_player", "action": "Game Start"})
            assert start_log['description'] == "The player has started the game."


def test_play_game_quit(pg_connection, mongo_db, reset_db_state):
    """
    Test that the player quits the game and the quit action is logged.
    """
    username = "test_player"

    # Add player
    add_existing_player(pg_connection, username=username, purpose="create_new_player")

    # Create a new session for the player
    create_session_for_player(pg_connection, username)

    # Simulate the player answering the first 5 questions
    add_player_answers(pg_connection, username, question_ids=list(range(1, 6)))

    # Fetch unanswered questions
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_unanswered_questions(%s);", (username,))
        unanswered_questions = cursor.fetchall()
    question_ids = [qid[0] for qid in unanswered_questions]

    # Fetch the corresponding questions from MongoDB
    questions = fetch_questions_mongo(mongo_db, question_ids)

    # Simulate player quitting immediately
    with patch("game_logic.get_valid_input", side_effect=["q"]):  # Quit immediately
        result = play_game(pg_connection, username, mongo_db, questions)

        # Assert that play_game returns None when the player quits
        assert result is None

    # Verify quit action logged in MongoDB
    quit_log = mongo_db.action_history.find_one({"username": username})
    assert quit_log['action'] == "Game Quitting"
    assert quit_log['description'] == "The player has quit the game."


def test_play_game_view_stats(pg_connection, mongo_db, reset_db_state):
    """
    Test that the player views statistics during the game.
    """
    username = "test_player"

    # Add player
    add_existing_player(pg_connection, username=username, purpose="create_new_player")

    # Create a new session for the player
    create_session_for_player(pg_connection, username)

    # Simulate the player answering the first 5 questions
    add_player_answers(pg_connection, username, question_ids=list(range(1, 6)))

    # Fetch unanswered questions
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_unanswered_questions(%s);", (username,))
        unanswered_questions = cursor.fetchall()
    question_ids = [qid[0] for qid in unanswered_questions]

    # Fetch the corresponding questions from MongoDB
    questions = fetch_questions_mongo(mongo_db, question_ids)

    # Mock stats response
    with patch("game_logic.get_valid_input", side_effect=["s", "q"]):
        result = play_game(pg_connection, username, mongo_db, questions)

        # Assert that play_game returns None when the player quits
        assert result is None

    # Verify stats action logged in MongoDB
    stats_log = mongo_db.action_history.find_one({"username": username})
    assert stats_log['action'] == "Questions Status"
    assert stats_log['description'] == "The player has seen his questions status."


def test_play_game_success(pg_connection, mongo_db, reset_db_state):
    """
    Test the completion of a game where the player answers all questions and finalizes the game.
    """
    username = "test_player"

    # Add player
    add_existing_player(pg_connection, username=username, purpose="create_new_player")

    # Create a new session for the player
    create_session_for_player(pg_connection, username)

    # Fetch unanswered questions from PostgreSQL
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_unanswered_questions(%s);", (username,))
        unanswered_questions = cursor.fetchall()

    question_ids = [qid[0] for qid in unanswered_questions]

    # Fetch the corresponding questions from MongoDB
    questions = fetch_questions_mongo(mongo_db, question_ids)

    # Dynamically generate player answers randomly
    player_answers = [random.choice(['a', 'b', 'c', 'd']) for _ in questions]

    with patch("game_logic.get_valid_input", side_effect=player_answers):
        # Mock finalize_game to ensure it is called
        with patch("game_logic.finalize_game") as mock_finalize_game:
            play_game(pg_connection, username, mongo_db, questions)

            # Verify finalize_game is called at the end of the game
            mock_finalize_game.assert_called_once_with(pg_connection, username, mongo_db)

    # Verify that the player's answers were recorded correctly in PostgreSQL
    with pg_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT question_id, selected_answer, is_correct
            FROM player_answers
            WHERE player_id = (SELECT player_id FROM players WHERE username = %s)
            ORDER BY question_id;
            """,
            (username,)
        )
        recorded_answers = cursor.fetchall()

    # Assert the number of recorded answers matches the total number of questions
    assert len(recorded_answers) == len(questions)

    # Verify correctness of recorded answers
    for recorded_answer, question, player_answer in zip(recorded_answers, questions, player_answers):
        question_id, selected_answer, is_correct = recorded_answer
        assert question_id == question["question_id"]
        expected_correctness = player_answer == "a"  # 'a' is the correct answer for all questions
        assert selected_answer == player_answer
        assert is_correct == expected_correctness

        # Fetch the answer text from the question using the selected_answer
        options_mapping = {
            'a': question['answer_a'],
            'b': question['answer_b'],
            'c': question['answer_c'],
            'd': question['answer_d']
        }
        answer_text = options_mapping[selected_answer]

        # Construct expected description
        expected_description = (
            f"The player has answered a question. question ID {question_id}"
            f" with answer '{answer_text}'. Correct: {is_correct}"
        )

        answer_log = mongo_db.action_history.find_one({
            "username": username,
            "action": "Answer Record",
            "description": expected_description
        })
        assert answer_log['description'] == expected_description


def test_finalize_game_success(pg_connection, mongo_db, reset_db_state):
    """
    Test the full flow of finalize_game, including:
    - Updating game session.
    - Retrieving correct answers.
    - Updating high scores.
    - Displaying high scores.
    - Verifying MongoDB logging.
    """
    username = "test_player"

    # Add player, answered questions, and create a game session
    player_id = add_existing_player(pg_connection, username=username, purpose="create_new_player")

    # Create a new session for the player
    create_session_for_player(pg_connection, username)

    # Simulate the player answering all 20 questions with correctness on even-indexed questions
    question_ids = list(range(1, 21))
    correct_indices = [index - 1 for index in question_ids if index % 2 == 0]  # Even question IDs are correct
    add_player_answers(pg_connection, username, question_ids=question_ids, correct_indices=correct_indices)

    # Expected results
    expected_correct_answers = len(correct_indices)

    # Verify game session update
    finalize_game(pg_connection, username, mongo_db)

    # Step 1: Check game session is completed
    with pg_connection.cursor() as cursor:
        cursor.execute(
            "SELECT is_completed, is_active FROM game_sessions WHERE player_id = %s;", (player_id,)
        )
        session_status = cursor.fetchone()
        assert session_status[0] is True
        assert session_status[1] is False

    # Step 2: Verify correct answer count
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_correct_answer_count(%s);", (username,))
        correct_answers = cursor.fetchone()[0]
        assert correct_answers == expected_correct_answers

    # Step 3: Verify record in high_scores
    with pg_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM high_scores 
            WHERE player_id = %s;
            """,
            (player_id,)
        )
        high_score_record = cursor.fetchone()
        assert high_score_record[0] == expected_correct_answers  # Score matches correct answers

    # Step 4: Verify high scores display
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_high_scores();")
        high_scores = cursor.fetchall()
        assert len(high_scores) > 0

    # Step 5: Verify MongoDB logs
    actions = [
        {"action": "Game Complete", "description": "The game session is completed."},
        {"action": "Update High Scores", "description": "The high scores table has been updated."},
        {"action": "Display High Scores", "description": "The high scores table has been displayed."}
    ]
    for action in actions:
        log = mongo_db.action_history.find_one({"username": username, "action": action["action"]})
        assert log['description'] == action['description']


# Tests for functions in statistics file
def test_execute_statistics_procedure_total_players(pg_connection, mongo_db, reset_db_state):
    """
    Test `execute_statistics_procedure` for viewing total players.
    """
    # Add multiple players
    usernames = [f"player_{i}" for i in range(1, 21)]  # Adding 20 players
    for username in usernames:
        add_existing_player(pg_connection, username=username, purpose="create_new_player")

    # Call the function with choice '1' (vw_total_players)
    execute_statistics_procedure(pg_connection, mongo_db, "1", "test_user")

    # Fetch the result from the view
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM vw_total_players;")
        result = cursor.fetchone()

    # Verify the result corresponds to the total number of players added
    assert result[0] == len(usernames)  # Expecting 20 total players

    # Verify MongoDB log
    logged_action = mongo_db.action_history.find_one({"username": "test_user"})
    assert logged_action["action"] == "Viewing Statistics 1"
    assert logged_action["description"] == "Viewed the total players that play the game."


def test_most_correctly_answered_question(pg_connection, mongo_db, reset_db_state):
    """
    Test the function `fn_get_most_correctly_answered_question` to verify it returns the question
    with the highest count of correct answers.
    """
    # Add questions to the database (1 to 20 assumed already added)
    question_ids = list(range(1, 21))

    # Add twenty players and assign correct answers to each question
    usernames = [f"player_{i}" for i in range(1, 21)]
    for i, username in enumerate(usernames, start=1):
        # Add player and create a session
        add_existing_player(pg_connection, username=username, purpose="create_new_player")
        create_session_for_player(pg_connection, username)

        # Assign correct answers based on the defined correct_answers_per_question
        correct_indices = list(range(i))
        add_player_answers(pg_connection, username, question_ids=question_ids, correct_indices=correct_indices)

    # Predetermined expected results
    expected_question_id = 1  # Hardcoded as we know question_id 1 has the most correct answers
    expected_highest_count = 20  # Hardcoded as we know question_id 20 has 20 correct answers

    # Call `execute_statistics_procedure` to log the action and invoke the procedure
    execute_statistics_procedure(pg_connection, mongo_db, "2", "test_user")

    # Execute the function `fn_get_most_correctly_answered_question`
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_most_correctly_answered_question();")
        most_correct_results = cursor.fetchall()

    # Assert that only one question ID is returned, and it matches the expected question ID
    assert most_correct_results[0][0] == expected_question_id
    assert most_correct_results[0][1] == expected_highest_count

    # Log verification in MongoDB
    logged_action = mongo_db.action_history.find_one({"username": "test_user"})
    assert logged_action["action"] == "Viewing Statistics 2"
    assert logged_action["description"] == "Viewed the most correctly answered question."


def test_least_correctly_answered_question(pg_connection, mongo_db, reset_db_state):
    """
    Test the function `fn_get_least_correctly_answered_question` to verify it returns the question(s)
    with the lowest count of correct answers, accounting for ties.
    """
    # Add questions to the database (1 to 20 assumed already added)
    question_ids = list(range(1, 21))

    # Add twenty players and assign correct answers to each question
    usernames = [f"player_{i}" for i in range(1, 21)]
    for i, username in enumerate(usernames, start=1):
        # Add player and create a session
        add_existing_player(pg_connection, username=username, purpose="create_new_player")
        create_session_for_player(pg_connection, username)

        # Assign correct answers based on the defined correct_answers_per_question
        correct_indices = list(range(i))
        add_player_answers(pg_connection, username, question_ids=question_ids, correct_indices=correct_indices)

    # Predetermined expected results
    expected_question_id = 20  # Hardcoded as we know question_id 20 has the least correct answers
    expected_least_count = 1  # Hardcoded as we know question_id 1 has one correct answer

    # Call `execute_statistics_procedure` to log the action and invoke the procedure
    execute_statistics_procedure(pg_connection, mongo_db, "3", "test_user")

    # Execute the function `fn_get_most_correctly_answered_question`
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_least_correctly_answered_question();")
        least_correct_results = cursor.fetchall()

    # Assert that only one question ID is returned, and it matches the expected question ID
    assert least_correct_results[0][0] == expected_question_id
    assert least_correct_results[0][1] == expected_least_count

    # Log verification in MongoDB
    logged_action = mongo_db.action_history.find_one({"username": "test_user"})
    assert logged_action["action"] == "Viewing Statistics 3"
    assert logged_action["description"] == "Viewed the least correctly answered question."


def test_view_players_by_correct_answers(pg_connection, mongo_db, reset_db_state):
    """
    Test the view `vw_players_by_correct_answers` to ensure it ranks players by the number of correct answers.
    """
    # Add questions to the database (1 to 20 assumed already added)
    question_ids = list(range(1, 21))

    # Add multiple players with increasing correct answers
    usernames = [f"player_{i}" for i in range(1, 11)]  # Create 10 players

    for idx, username in enumerate(usernames):
        add_existing_player(pg_connection, username=username, purpose="create_new_player")
        create_session_for_player(pg_connection, username)

        # Assign increasing correct answers (Player 1: 1 correct, Player 2: 2 correct, etc.)
        correct_indices = list(range(idx + 1))
        add_player_answers(pg_connection, username, question_ids, correct_indices=correct_indices)

    # Call `execute_statistics_procedure` to log the action and invoke the procedure
    execute_statistics_procedure(pg_connection, mongo_db, "4", "test_user")

    # Fetch data from the view
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM vw_players_by_correct_answers;")
        view_results = cursor.fetchall()

    # Define the expected results
    expected_results = [
        (f"player_{i}", i) for i in range(10, 0, -1)
    ]

    # Assert that the view results match the expected results
    assert view_results == expected_results

    # Verify the action was logged in MongoDB
    logged_action = mongo_db.action_history.find_one({"username": "test_user"})
    assert logged_action["action"] == "Viewing Statistics 4"
    assert logged_action["description"] == "Viewed the players ranked by correct answers."


def test_view_players_by_total_answers(pg_connection, mongo_db, reset_db_state):
    """
    Test the view `vw_players_by_total_answers` to ensure it ranks players by the total number of answers.
    """
    # Add questions to the database (1 to 20 assumed already added)
    question_ids = list(range(1, 21))

    # Define players with increasing sessions and answers
    players_sessions_answers = [
        ("player_1", 1, 20),  # Player 1 plays 1 session, answers 20 questions
        ("player_2", 2, 40),  # Player 2 plays 2 sessions, answers 40 questions
        ("player_3", 3, 60),  # Player 3 plays 3 sessions, answers 60 questions
        ("player_4", 4, 80),  # Player 4 plays 4 sessions, answers 80 questions
        ("player_5", 5, 100)  # Player 5 plays 5 sessions, answers 100 questions
    ]

    # Add players and assign sessions and answers
    for username, sessions, total_questions in players_sessions_answers:
        add_existing_player(pg_connection, username=username, purpose="create_new_player")
        for _ in range(sessions):
            create_session_for_player(pg_connection, username)
            add_player_answers(pg_connection, username, question_ids=question_ids)

    # Call `execute_statistics_procedure` to log the action and invoke the procedure
    execute_statistics_procedure(pg_connection, mongo_db, "5", "test_user")

    # Fetch data from the view
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM vw_players_by_total_answers;")
        view_results = cursor.fetchall()

    # Define expected results based on sessions and answers
    expected_results = [
        (username, total_questions) for username, _, total_questions in sorted(
            players_sessions_answers, key=lambda x: x[2], reverse=True
        )
    ]

    # Assert that the view matches the expected results
    assert view_results == expected_results

    # Verify the action was logged in MongoDB
    logged_action = mongo_db.action_history.find_one({"username": "test_user"})
    assert logged_action["action"] == "Viewing Statistics 5"
    assert logged_action["description"] == "Viewed the players ranked by total answers."


def test_view_player_answer_statistics(pg_connection, mongo_db, reset_db_state):
    """
    Test option 6: View player's answers statistics.
    This test ensures that the statistics for a specific player are retrieved correctly
    from PostgreSQL and that the action is logged in MongoDB.
    """
    # Add a test player
    username = "test_player"
    player_id = add_existing_player(pg_connection, username=username, purpose="create_new_player")

    # Define sessions and consistent correct indices (0, 2, 4, ...)
    num_sessions = 3
    questions_per_session = list(range(1, 21))  # Assuming 20 questions exist
    correct_indices = list(range(0, len(questions_per_session), 2))

    expected_results = []

    # Add multiple sessions for the player
    for session_idx in range(num_sessions):
        # Create a new session for the player
        create_session_for_player(pg_connection, username)

        # Add answers for the session
        add_player_answers(pg_connection, username, question_ids=questions_per_session, correct_indices=correct_indices)

        # Append expected results in the order of answering
        for idx, q_id in enumerate(questions_per_session):
            is_correct = idx in correct_indices
            expected_results.append((q_id, is_correct))

    expected_results = sorted(expected_results, key=lambda x: (x[0]))

    # Mock input for player ID in option 6
    with patch("statistics.get_valid_input", return_value=str(player_id)):
        # Execute the statistics procedure for option 6
        execute_statistics_procedure(pg_connection, mongo_db, "6", username)

    # Fetch results from the PostgreSQL function
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_player_answers_statistics(%s);", (player_id,))
        results = cursor.fetchall()
    sorted_results = sorted(results, key=lambda x: (x[0]))

    # Validate the results from the function
    assert sorted_results == expected_results

    # Validate MongoDB logging
    logged_action = mongo_db.action_history.find_one({"username": username})
    assert logged_action["action"] == "Viewing Statistics 6"
    assert logged_action["description"] == "Viewed specific player answers statistics."


def test_questions_statistics(pg_connection, mongo_db, reset_db_state):
    """
    Test the function `fn_get_questions_statistics` to verify it calculates and returns
    correct statistics for questions, including total answered, correct answers, and incorrect answers.
    """
    # Add questions to the database (1 to 20 assumed already added)
    question_ids = list(range(1, 21))

    # Define the hardcoded expected results
    expected_results = [
        (q_id, 20, 20 - (q_id - 1), (q_id - 1))  # (question_id, total_answered, correct_answers, incorrect_answers)
        for q_id in question_ids
    ]

    # Add multiple players and assign answers to questions
    usernames = [f"player_{i}" for i in range(1, 21)]  # Create 20 players
    for i, username in enumerate(usernames, start=1):
        # Add player and create a session
        add_existing_player(pg_connection, username=username, purpose="create_new_player")
        create_session_for_player(pg_connection, username)

        # Assign correct answers based on the desired pattern
        correct_indices = list(range(i))  # First `i` questions are correct for this player
        add_player_answers(pg_connection, username, question_ids=question_ids, correct_indices=correct_indices)

    # Call `execute_statistics_procedure` to log the action and invoke the function
    execute_statistics_procedure(pg_connection, mongo_db, "7", "test_user")

    # Execute the PostgreSQL function `fn_get_questions_statistics`
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_question_answers_statistics();")
        function_results = cursor.fetchall()

    # Sort results by question_id for comparison
    function_results_sorted = sorted(function_results, key=lambda x: x[0])
    expected_results_sorted = sorted(expected_results, key=lambda x: x[0])

    # Assert the function results match the expected results
    assert function_results_sorted == expected_results_sorted

    # Validate MongoDB logging
    logged_action = mongo_db.action_history.find_one({"username": "test_user"})
    assert logged_action["action"] == "Viewing Statistics 7"
    assert logged_action["description"] == "Viewed questions answers statistics."


# Tests for functions in statistical_graphs fileT
def test_generate_player_answered_vs_not_answered_pie_chart(pg_connection, reset_db_state):
    """
    Test the function generate_player_answered_vs_not_answered_pie_chart.
    Ensures correct data when 20 questions exist and only half are answered.
    """
    # Add test player and questions
    player_id = add_existing_player(pg_connection, username="test_player", purpose="create_new_player")
    create_session_for_player(pg_connection, username="test_player")

    # Answer only half of the questions
    question_ids = list(range(1, 21))  # 20 questions
    answered_question_ids = question_ids[:10]  # Answer only the first half
    add_player_answers(pg_connection, username="test_player", question_ids=answered_question_ids, correct_indices=[])

    # Execute the function
    generate_player_answered_vs_not_answered_pie_chart(pg_connection, player_id)

    # Verify the PostgreSQL function results
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_player_answered_vs_not_answered(%s);", (player_id,))
        results = cursor.fetchall()

    # Verify answered and unanswered counts
    assert results == [(10, 10)]  # 10 answered, 10 not answered


def test_generate_player_correct_incorrect_pie_chart(pg_connection, reset_db_state):
    """
    Test the function generate_player_correct_incorrect_pie_chart.
    Ensures correct data when 20 questions exist, all answered, but only half correct.
    """
    # Add test player and questions
    player_id = add_existing_player(pg_connection, username="test_player", purpose="create_new_player")
    create_session_for_player(pg_connection, username="test_player")

    # Answer all questions, but only half correctly
    question_ids = list(range(1, 21))  # 20 questions
    correct_indices = list(range(0, 20, 2))  # Answer every alternate question correctly
    add_player_answers(pg_connection, username="test_player", question_ids=question_ids,
                       correct_indices=correct_indices)

    # Execute the function
    generate_player_correct_incorrect_pie_chart(pg_connection, player_id)

    # Verify the PostgreSQL function results
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_player_correct_incorrect_answers(%s);", (player_id,))
        results = cursor.fetchall()

    # Verify correct and incorrect counts
    assert results == [(10, 10)]  # 10 correct, 10 incorrect


def test_generate_question_statistics_graph(pg_connection, mongo_db, reset_db_state):
    """
    Test the function generate_question_statistics_graph.
    Ensures correct data and behavior with 20 players answering questions with decremental correctness.
    """
    # Add questions to the database (1 to 20 assumed already added)
    question_ids = list(range(1, 21))

    # Define the hardcoded expected results
    expected_results = [
        (q_id, 20, 20 - (q_id - 1), (q_id - 1))  # (question_id, total_answered, correct_answers, incorrect_answers)
        for q_id in question_ids
    ]

    # Add multiple players and assign answers to questions
    usernames = [f"player_{i}" for i in range(1, 21)]  # Create 20 players
    for i, username in enumerate(usernames, start=1):
        # Add player and create a session
        add_existing_player(pg_connection, username=username, purpose="create_new_player")
        create_session_for_player(pg_connection, username)

        # Assign correct answers based on the desired pattern
        correct_indices = list(range(i))  # First `i` questions are correct for this player
        add_player_answers(pg_connection, username, question_ids=question_ids, correct_indices=correct_indices)

    # Call the `generate_question_statistics_graph` function
    mock_question_data = [
        {"question_id": qid, "question_text": f"Question {qid}"} for qid in question_ids
    ]
    with patch("mongodb_queries.fetch_questions_mongo", return_value=mock_question_data):
        generate_question_statistics_graph(pg_connection, mongo_db, top_n=20)

    # Execute the PostgreSQL function `fn_get_question_answer_statistics`
    with pg_connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fn_get_question_answers_statistics();")
        function_results = cursor.fetchall()

    # Sort results by question_id for comparison
    function_results_sorted = sorted(function_results, key=lambda x: x[0])
    expected_results_sorted = sorted(expected_results, key=lambda x: x[0])

    # Assert the function results match the expected results
    assert function_results_sorted == expected_results_sorted
