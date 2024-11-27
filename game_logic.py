import pytz
from postgresql_queries import execute_pg_procedure
from mongodb_queries import log_action_mongo, fetch_questions_mongo
from actions_and_procedures_centralization import get_game_action_details
from validation import (
    get_valid_input,
    is_valid_choice
)
from typing import Any, Tuple, Optional, List, Dict


def game_status(pg_connection: Any, mongo_db: Any, username: str) -> str | None:
    """
    Handle game status after successful login (continue or reset game).

    :param pg_connection: PostgreSQL connection object.
    :param mongo_db: MongoDB database object.
    :param username: Username of the logged-in player.
    """
    # Fetch unanswered questions (20 random)
    check_procedure_name, _, _ = get_game_action_details("check_unanswered")
    try:
        unanswered_questions_data: List[Tuple[int]] = execute_pg_procedure(pg_connection, check_procedure_name,
                                                                           [username])
    except Exception as e:
        print(f"Error fetching unanswered questions: {e}")
        return

    question_ids = [qid[0] for qid in unanswered_questions_data]

    if len(question_ids) == 20:
        print("Starting a new game!")
        _, action_type, description = get_game_action_details("start_game")
        try:
            log_action_mongo(mongo_db, action_type, username, description)
        except Exception as e:
            print(f"Started game but failed to log the action: {e}")
        # Fetch full question details from MongoDB
        try:
            questions = fetch_questions_mongo(mongo_db, question_ids)
        except Exception as e:
            print(f"Error fetching questions from MongoDB: {e}")
            return
        play_game(pg_connection, username, mongo_db, questions)
    else:
        # Ask the player if they want to continue the previous game
        continue_choice: str = get_valid_input(
            "Do you want to continue your game? (y/n): ",
            lambda x: is_valid_choice(x.lower(), ['y', 'n']),
            "Invalid choice. Please enter 'y' or 'n'."
        ).lower()

        if continue_choice == 'y':
            try:
                _, action_type, description = get_game_action_details("continue_game")
                log_action_mongo(mongo_db, action_type, username, description)
            except Exception as e:
                print(f"Continued game but failed to log the action: {e}")
            # Fetch full question details from MongoDB
            try:
                questions = fetch_questions_mongo(mongo_db, question_ids)
            except Exception as e:
                print(f"Error fetching questions from MongoDB: {e}")
                return
            play_game(pg_connection, username, mongo_db, questions)
        else:
            reset_game(pg_connection, username, mongo_db)
            # Start a new game with fresh questions
            try:
                unanswered_questions_data_new: List[Tuple[int]] = execute_pg_procedure(pg_connection,
                                                                                       check_procedure_name,
                                                                                       [username])
                question_ids_new = [qid[0] for qid in unanswered_questions_data_new]
                questions_new = fetch_questions_mongo(mongo_db, question_ids_new)
                print("Starting a new game!")
                _, action_type, description = get_game_action_details("start_game")
                log_action_mongo(mongo_db, action_type, username, description)
                play_game(pg_connection, username, mongo_db, questions_new)
            except Exception as e:
                print(f"Error starting a new game: {e}")
                return

    return username


def play_game(pg_connection: Any, username: str, mongo_db: Any, questions: List[Dict[str, Any]]) -> None:
    """
    Manage the gameplay by presenting questions and handling user responses.

    :param pg_connection: PostgreSQL connection object.
    :param username: The username of the player.
    :param mongo_db: MongoDB database object.
    :param questions: A list of question documents to present to the player.
    """

    total_questions: int = 20
    index: int = total_questions - len(questions) + 1

    for idx, question in enumerate(questions, index):
        question_id = question['question_id']
        question_text = question['question_text']
        answer_a = question.get('answer_a')
        answer_b = question.get('answer_b')
        answer_c = question.get('answer_c')
        answer_d = question.get('answer_d')
        correct_answer = question.get('correct_answer')

        print(f"\nQuestion {idx}: {question_text}")
        print(f"a) {answer_a}")
        print(f"b) {answer_b}")
        print(f"c) {answer_c}")
        print(f"d) {answer_d}")

        # Map the answer letter to the answer text
        options_mapping = {
            'a': answer_a,
            'b': answer_b,
            'c': answer_c,
            'd': answer_d
        }

        while True:
            # Get the player's answer
            answer: str = get_valid_input(
                "Enter your answer (a, b, c, d), 's' to view stats, or 'q' to quit: ",
                lambda x: is_valid_choice(x.lower(), ['a', 'b', 'c', 'd', 'q', 's']),
                "Invalid input. Please select 'a', 'b', 'c', 'd', 's', or 'q'."
            ).lower()

            if answer == 'q':
                # Handle quitting the game
                _, quit_action_type, quit_description = get_game_action_details("quit_game")
                try:
                    log_action_mongo(mongo_db, quit_action_type, username, quit_description)
                except Exception as e:
                    print(f"Quitting game but failed to log the action: {e}")
                print(f"Player {username} quit the game.")
                return
            elif answer == 's':
                # Display answer statistics
                try:
                    stats_procedure, stats_action_type, stats_description = get_game_action_details("get_answer_stats")
                    answer_stats: Optional[List[Tuple[Any, Any]]] = execute_pg_procedure(pg_connection, stats_procedure,
                                                                                         [username])
                except Exception as e:
                    print(f"Error fetching answer statistics: {e}")
                    continue

                if answer_stats:
                    correct_count, incorrect_count = answer_stats[0]
                    try:
                        log_action_mongo(mongo_db, stats_action_type, username, stats_description)
                    except Exception as e:
                        print(f"Viewed stats but failed to log the action: {e}")
                    print(f"Correct answers: {correct_count}, Incorrect answers: {incorrect_count}")
                else:
                    print("No statistics available.")
                continue
            else:
                # Record the player's answer
                record_answer_procedure, action_type, description = get_game_action_details("record_answer")
                try:
                    execute_pg_procedure(pg_connection, record_answer_procedure, [username, question_id, answer])
                except Exception as e:
                    print(f"Error recording answer: {e}")
                    continue

                # Get the answer text based on the player's selection and correct_answer_text
                answer_text = options_mapping.get(answer)
                correct_answer_text = options_mapping.get(correct_answer)

                # Check if the answer was correct
                is_correct = (answer == correct_answer)
                if is_correct:
                    print(f"'{answer_text}' is the correct answer!")
                else:
                    print(f"'{answer_text}' is not the correct answer."
                          f" Correct answer was '{correct_answer_text}'.")

                # Log the action
                try:
                    log_action_mongo(mongo_db, action_type, username, f"{description}"
                                                                      f" question ID {question_id}"
                                                                      f" with answer '{answer_text}'."
                                                                      f" Correct: {is_correct}")
                except Exception as e:
                    print(f"Answer recorded but failed to log the action: {e}")
                break

    finalize_game(pg_connection, username, mongo_db)
    return


def finalize_game(pg_connection: Any, username: str, mongo_db: Any) -> None:
    """
    Finalize the game, update high scores, and display results.

    :param pg_connection: PostgreSQL connection object.
    :param username: The username of the player.
    :param mongo_db: MongoDB database object.
    """
    # Update session after completion
    update_session_complete, action_type, description = get_game_action_details("completing_session")
    try:
        execute_pg_procedure(pg_connection, update_session_complete, [username])
    except Exception as e:
        print(f"Error completing session: {e}")
        return

    # Log the completing session action
    try:
        log_action_mongo(mongo_db, action_type, username, description)
    except Exception as e:
        print(f"Completed session but failed to log the action: {e}")

    # Get the number of correct answers
    correct_answers_procedure, _, _ = get_game_action_details("get_correct_answer_count")
    try:
        correct_answers_result: List[Tuple[int]] = execute_pg_procedure(
            pg_connection, correct_answers_procedure, [username])
    except Exception as e:
        print(f"Error counting the correct answers: {e}")
        return

    correct_answers: int = correct_answers_result[0][0]

    # Update high scores if applicable
    if correct_answers > 0:
        update_score_procedure, action_type, description = get_game_action_details("update_high_scores")
        try:
            execute_pg_procedure(pg_connection, update_score_procedure, [username])
            log_action_mongo(mongo_db, action_type, username, description)
        except Exception as e:
            print(f"Error updating high scores: {e}")
            return

    # Display high scores
    high_scores_procedure, action_type, description = get_game_action_details("display_high_scores")
    try:
        high_scores: Optional[List[Tuple[int, str, str, int, Any, Any]]] = execute_pg_procedure(pg_connection,
                                                                                                high_scores_procedure,
                                                                                                [])
        log_action_mongo(mongo_db, action_type, username, description)
    except Exception as e:
        print(f"Error fetching high scores: {e}")
        return

    print("\nGame Results:\n")
    print(f"{'Player':<10} {'Player Name':<20} {'Email':<30} {'Score':<10} {'Total Time':<15} {'Achieved At':<20}")
    print("-" * 105)

    # Define your desired timezone
    desired_timezone = pytz.timezone('Asia/Jerusalem')

    for result in high_scores:
        player_id, username_high, email, score_high, total_time, achieved_at = result
        # Format the total_time without microseconds
        total_seconds = int(total_time.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        total_time_str = f"{hours:02}:{minutes:02}:{seconds:02}"
        achieved_at_local = achieved_at.astimezone(desired_timezone)
        achieved_at_str = achieved_at_local.strftime('%Y-%m-%d %H:%M:%S')

        print(f"{player_id:<10} {username_high:<20} {email:<30} {score_high:<10} {total_time_str:<15} "
              f"{achieved_at_str:<20}")


def reset_game(pg_connection: Any, username: str, mongo_db: Any) -> None:
    """
    Reset the player's game progress.

    :param pg_connection: PostgreSQL connection object.
    :param username: The username of the player.
    :param mongo_db: MongoDB database object.
    """
    reset_game_procedure, action_type, description = get_game_action_details("reset_game")
    try:
        execute_pg_procedure(pg_connection, reset_game_procedure, [username])
        log_action_mongo(mongo_db, action_type, username, description)
        print(f"Player {username}'s game has been reset.")
    except Exception as e:
        print(f"Error resetting game: {e}")
