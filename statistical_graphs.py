import matplotlib.pyplot as plt
from typing import Any
from postgresql_queries import execute_pg_procedure
from mongodb_queries import fetch_questions_mongo


def generate_player_answered_vs_not_answered_pie_chart(pg_connection: Any, player_id: int) -> None:
    """
    Generates a pie chart showing the percentage of questions answered vs not answered by the player.

    :param pg_connection: PostgreSQL connection object.
    :param player_id: The player's ID.
    """
    try:
        # Assuming a stored procedure: fn_get_player_answered_not_answered(p_player_id INT)
        results = execute_pg_procedure(pg_connection, "fn_get_player_answered_vs_not_answered",
                                       [player_id])
        if results[0][0] == 0 or results[0][1] == 0:
            print("No data found for the player.")
            return

        answered, not_answered = results[0]

        labels = ['Answered Questions', 'Unanswered Questions']
        sizes = [answered, not_answered]
        colors = ['#66b3ff', '#ff9999']
        explode = (0.1, 0)  # explode first slice

        plt.figure(figsize=(10, 10))
        plt.pie(sizes, explode=explode, labels=labels, colors=colors, autopct='%1.1f%%',
                shadow=True, startangle=140)
        plt.title(f"Questions Answered vs Not Answered by Player ID {player_id}")
        plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
        plt.show()

    except Exception as e:
        print(f"Error generating pie chart: {e}")


def generate_player_correct_incorrect_pie_chart(pg_connection: Any, player_id: int) -> None:
    """
    Generates a pie chart showing the percentage of correct vs incorrect answers by the player.

    :param pg_connection: PostgreSQL connection object.
    :param player_id: The player's ID.
    """
    try:
        # Assuming a stored procedure: fn_get_player_correct_incorrect(p_player_id INT)
        results = execute_pg_procedure(pg_connection, "fn_get_player_correct_incorrect_answers",
                                       [player_id])
        if results[0][0] == 0 or results[0][1] == 0:
            print("No data found for the player.")
            return

        correct, incorrect = results[0]

        labels = ['Correct Answers', 'Incorrect Answers']
        sizes = [correct, incorrect]
        colors = ['#99ff99', '#ff6666']
        explode = (0.1, 0)  # explode first slice

        plt.figure(figsize=(10, 10))
        plt.pie(sizes, explode=explode, labels=labels, colors=colors, autopct='%1.1f%%',
                shadow=True, startangle=140)
        plt.title(f"Correct vs Incorrect Answers by Player ID {player_id}")
        plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
        plt.show()

    except Exception as e:
        print(f"Error generating pie chart: {e}")


def generate_question_statistics_graph(pg_connection: Any, mongo_db: Any, top_n: int) -> None:
    """
    Generates a bar chart showing top N questions based on total answered, correct, and incorrect counts.

    :param pg_connection: PostgreSQL connection object.
    :param mongo_db: MongoDB database object.
    :param top_n: Number of top questions to display.
    """
    try:
        # Assuming a stored procedure: fn_get_questions_statistics()
        results = execute_pg_procedure(pg_connection, "fn_get_question_answers_statistics", [])
        if not results:
            print("No data found for questions statistics.")
            return

        # Sort by total_answered descending and take top_n
        sorted_results = sorted(results, key=lambda item: item[2], reverse=True)[:top_n]
        question_ids = [row[0] for row in sorted_results]
        total_answered = [row[1] for row in sorted_results]
        correct_answers = [row[2] for row in sorted_results]
        incorrect_answers = [row[3] for row in sorted_results]

        # Fetch question_texts from MongoDB
        try:
            questions = fetch_questions_mongo(mongo_db, question_ids)
            question_text_map = {q['question_id']: q['question_text'] for q in questions}
        except Exception as e:
            print(f"Error fetching question texts from MongoDB: {e}")
            question_text_map = {qid: "No Text Available" for qid in question_ids}

        question_labels = [f"Q{qid}" for qid in question_ids]
        question_legend = {f"Q{qid}": question_text_map.get(qid, "No Text Available") for qid in question_ids}

        x = range(len(question_ids))
        width = 0.25  # the width of the bars

        plt.figure(figsize=(13, 8))
        plt.bar([p - width for p in x], total_answered, width, label='Total Answered')
        plt.bar(x, correct_answers, width, label='Correct Answers')
        plt.bar([p + width for p in x], incorrect_answers, width, label='Incorrect Answers')

        plt.xlabel('Questions')
        plt.ylabel('Number of Answers')
        plt.title(f'Top {top_n} Questions Answer Statistics')
        plt.xticks(x, question_labels, rotation=0, ha='center')
        plt.legend()
        plt.tight_layout(rect=(0, 0, 1, 0.7))

        # Add legend for question texts in two columns
        legend_texts = [f"{key}: {value}" for key, value in question_legend.items()]
        plt.figtext(0.02, 0.76, "\n".join(legend_texts[:len(legend_texts) // 2]), horizontalalignment='left',
                    fontsize=10)
        plt.figtext(0.55, 0.76, "\n".join(legend_texts[len(legend_texts) // 2:]), horizontalalignment='left',
                    fontsize=10)

        plt.show()

    except Exception as e:
        print(f"Error generating bar chart: {e}")
