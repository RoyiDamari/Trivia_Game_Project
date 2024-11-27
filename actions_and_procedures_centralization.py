from typing import Tuple, Optional, Dict


def get_game_action_details(action_name: str) -> Tuple[Optional[str], str, str]:
    """
    Provide procedure name and description based on the action name.

    :param action_name: Specific action name (e.g., "create_player", "login").
    :return: Tuple containing procedure name, action_type, and log description.
    """
    actions: Dict[str, Tuple[Optional[str], str, str]] = {
        'check_unique_username': ("fn_check_unique_username", None, None),
        'check_unique_email': ("fn_check_unique_email", None, None),
        'create_player': ("sp_create_player", "User Register", "New player has been signed up."),
        'login': ("fn_login_player", "User Login", "Player successfully logged in."),
        'failed_login': (None, "Login Failed", "Failed login attempt."),
        'check_unanswered': ("fn_get_unanswered_questions", None, None),
        'start_game': (None, "Game Start", "The player has started the game."),
        'continue_game': (None, "Game Continue", "The player has continued the game."),
        'record_answer': ("sp_record_player_answers", "Answer Record", "The player has answered a question."),
        'get_answer_stats': ("fn_get_answer_stats", "Questions Status", "The player has seen his questions status."),
        'get_correct_answer_count': ("fn_get_correct_answer_count", None, None),
        'update_high_scores': ("sp_update_high_scores", "Update High Scores", "The high scores table has been updated."),
        'display_high_scores': ("fn_get_high_scores", "Display High Scores",
                                "The high scores table has been displayed."),
        'reset_game': ("sp_reset_player_answers", "Game Reset", "The game has been reset."),
        'quit_game': (None, "Game Quitting", "The player has quit the game."),
        'completing_session': ("sp_completing_session", "Game Complete", "The game session is completed.")
    }
    return actions.get(action_name, (None, "unknown_action", "Unknown action"))


def get_statistics_action_details(choice: str):
    """
    Get the details of the action based on the given choice for statistics.

    :param choice: The choice made by the user in the statistics menu.
    :return: Tuple containing the object name, action type, and description.
    """
    object_mapping = {
        '1': ("vw_total_players", "Viewing Statistics 1", "Viewed the total players that play the game."),
        '2': ("fn_get_most_correctly_answered_question", "Viewing Statistics 2",
              "Viewed the most correctly answered question."),
        '3': ("fn_get_least_correctly_answered_question", "Viewing Statistics 3",
              "Viewed the least correctly answered question."),
        '4': ("vw_players_by_correct_answers", "Viewing Statistics 4",
              "Viewed the players ranked by correct answers."),
        '5': ("vw_players_by_total_answers", "Viewing Statistics 5",
              "Viewed the players ranked by total answers."),
        '6': ("fn_get_player_answers_statistics", "Viewing Statistics 6", "Viewed specific player answers statistics."),
        '7': ("fn_get_question_answers_statistics", "Viewing Statistics 7", "Viewed questions answers statistics."),
        '8': (None, "Viewing Statistics 8", "Viewed action history from MongoDB."),
        '9': (None, "Viewing Statistics 9",
              "Viewed player's answered vs not answered questions (Pie Chart)."),
        '10': (None, "Viewing Statistics 10",
               "Viewed player's correct vs incorrect answers (Pie Chart)."),
        '11': (None, "Viewing Statistics 11",
               "Viewed question answers statistics (Bar Chart).")
    }

    return object_mapping.get(choice, (None, "unknown_choice", "Unknown choice."))
