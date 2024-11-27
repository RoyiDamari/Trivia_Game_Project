from postgresql_queries import execute_pg_procedure
from mongodb_queries import log_action_mongo, fetch_action_history, fetch_questions_mongo
from validation import is_valid_choice, get_valid_input
from actions_and_procedures_centralization import get_statistics_action_details
from statistical_graphs import (
    generate_player_answered_vs_not_answered_pie_chart,
    generate_player_correct_incorrect_pie_chart,
    generate_question_statistics_graph
)
from typing import List, Any, Optional


def show_statistics(pg_connection: Any, mongo_db: Any, username: Optional[str] = None) -> None:
    """
    Displays the statistics menu for users to select from and calls the appropriate stored procedure or view query.

    :param pg_connection: PostgreSQL connection object.
    :param mongo_db: MongoDB connection object.
    :param username: The username performing the action (optional).
    :return: None
    """
    while True:
        print("\nStatistics Menu:")
        print("1. View total players")
        print("2. View most correctly answered question")
        print("3. View least correctly answered question")
        print("4. View players by correct answers")
        print("5. View players by total answers")
        print("6. View player's answers statistics")
        print("7. View question statistics")
        print("8. View action history")
        print("9. Show player's answered vs not answered questions (Pie Chart)")
        print("10. Show player's correct vs incorrect answers (Pie Chart)")
        print("11. Show question answer statistics (Bar Chart)")
        print("12. Return to main menu")

        statistics_choice: str = get_valid_input(
            "Enter your choice: ",
            lambda x: is_valid_choice(x, [str(i) for i in range(1, 13)]),
            "Invalid choice, please enter a valid number."
        )

        if statistics_choice != '12':
            execute_statistics_procedure(pg_connection, mongo_db, statistics_choice, username)
        else:
            print("Returning to main menu.")
            return


def execute_statistics_procedure(pg_connection: Any, mongo_db: Any, choice: str, username: Optional[str]) -> None:
    """
    Executes the corresponding stored procedure or SELECT query on a view for the selected statistics option
    and logs the action to MongoDB.

    :param pg_connection: PostgreSQL connection object.
    :param mongo_db: MongoDB connection object.
    :param choice: The choice made by the admin/user in the statistics menu.
    :param username: The username performing the action (optional).
    :return: None
    """

    # Get the object details from the mapping
    object_name, action_type, description = get_statistics_action_details(choice)

    # Log the action to MongoDB
    user = username if username else "Guest"
    try:
        log_action_mongo(mongo_db, action_type, user, description)
    except Exception as e:
        print(f"Failed to log the action: {e}")

    # Handle specific choices
    if choice == '8':
        show_action_history(mongo_db)

    elif choice in ['9', '10', '11']:
        # These options are handled by graph functions in statistical_graphs.py
        if choice == '9':
            # Generate player's answer distribution pie chart
            player_id_str: str = get_valid_input(
                "Enter player ID: ",
                lambda x: x.isdigit(),
                "Invalid player ID. Please enter a valid number."
            )
            player_id: int = int(player_id_str)
            generate_player_answered_vs_not_answered_pie_chart(pg_connection, player_id)

        elif choice == '10':
            # Generate player's correct vs incorrect answers pie chart
            player_id_str: str = get_valid_input(
                "Enter player ID: ",
                lambda x: x.isdigit(),
                "Invalid player ID. Please enter a valid number."
            )
            player_id: int = int(player_id_str)
            generate_player_correct_incorrect_pie_chart(pg_connection, player_id)

        elif choice == '11':
            # Generate question answer statistics bar chart
            top_n_str: str = get_valid_input(
                "Enter the number of top questions to display (up to 20): ",
                lambda x: x.isdigit() and (0 < int(x) <= 20),
                "Invalid number. Please enter a positive integer up to 20."
            )
            top_n: int = int(top_n_str)
            generate_question_statistics_graph(pg_connection, mongo_db, top_n)

    else:
        # Handle options that use stored procedures/functions or views
        try:
            if choice == '6':
                # View specific player's answer statistics
                player_id_str: str = get_valid_input(
                    "Enter player ID: ",
                    lambda x: x.isdigit(),
                    "Invalid player ID. Please enter a valid number."
                )
                player_id: int = int(player_id_str)
                results = execute_pg_procedure(pg_connection, object_name, [player_id])
            else:
                results = execute_pg_procedure(pg_connection, object_name, None)
        except Exception as e:
            print(f"Error executing query on {object_name}: {e}")
            return

        # Display the results
        if results:
            # For procedures that return question_ids, fetch question_texts from MongoDB
            if choice in ['2', '3', '6', '7']:
                question_id_field_index = 0
                question_ids = [result[question_id_field_index] for result in results]
                try:
                    questions = fetch_questions_mongo(mongo_db, question_ids)
                    question_text_map = {q['question_id']: q['question_text'] for q in questions}
                except Exception as e:
                    print(f"Error fetching question texts from MongoDB: {e}")
                    question_text_map = {qid: "No Text Available" for qid in question_ids}

                # Display enhanced results with question_text
                for result in results:
                    question_id = result[question_id_field_index]
                    question_text = question_text_map.get(question_id)
                    if choice in ['2', '3', '6']:
                        print(f"Question {question_id}: {question_text}, Correct Answers: {result[1]}")
                    else:
                        print(f"Question {question_id}: {question_text}, total_answered: {result[1]}, "
                              f"correct_answers: {result[2]}, incorrect_answers: {result[3]}")

            else:
                # Option 1: Total Players
                if choice == '1':
                    total_players = results[0][0]
                    print(f"\nTotal Players")
                    print("-" * 13)
                    print(f"\t {total_players}")

                elif choice in ['4', '5']:
                    # Options 4 and 5: Players by Correct Answers / Total Answers
                    print("\nUsername\t\tCount")
                    print("-" * 21)
                    for row in results:
                        username, count = row
                        print(f"{username:<15}\t{count}")
        else:
            print("No results found.")


def show_action_history(mongo_db: Any) -> None:
    """
    Fetches and displays the action history from MongoDB.

    :param mongo_db: MongoDB connection object.
    :return: None
    """

    actions: List[dict] = fetch_action_history(mongo_db)
    if actions:
        print("\nAction History:\n")
        print(f"{'Action':<30} {'Username':<20} {'Description':<65} {'Timestamp':<25}")
        print("-" * 137)

        for action in actions:
            # Check if the timestamp is a datetime object and format it
            timestamp = action['timestamp']
            timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

            # Extract only the part of the description before the dot
            description = action['description'].split('.')[0]

            print(f"{action['action']:<30} {action['username']:<20} {description:<65} {timestamp_str:<25}")
    else:
        print("No actions found.")
