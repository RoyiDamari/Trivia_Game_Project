from mongodb_queries import connect_to_mongo
from pymongo.errors import PyMongoError
import random
import requests
import time
from typing import Any, List, Dict

# Define global parameters for trivia questions
TRIVIA_QUESTION_AMOUNT: int = 300
TRIVIA_QUESTION_DIFFICULTY: str = "easy"
MAX_QUESTION_LENGTH: int = 60  # You can change this value to filter question length
# (this length corresponds to the bar chart)


def fetch_trivia_questions() -> List[Dict[str, Any]]:
    """
    Fetch trivia questions from Open Trivia Database API.
    :return: A list of trivia questions.
    """

    # Use global variables
    amount = TRIVIA_QUESTION_AMOUNT
    difficulty = TRIVIA_QUESTION_DIFFICULTY

    questions: List[Dict[str, Any]] = []

    try:
        # Make multiple requests if amount exceeds 50 (API limit)
        while amount > 0:
            fetch_amount = min(amount, 50)
            url = f"https://opentdb.com/api.php?amount={fetch_amount}&difficulty={difficulty}&type=multiple"
            response = requests.get(url)

            # Retry mechanism if rate limit is hit
            if response.status_code == 429:
                print("Rate limit reached. Waiting for 10 seconds before retrying...")
                time.sleep(10)
                continue

            response.raise_for_status()
            data = response.json()

            if data["response_code"] == 0:
                for item in data["results"]:
                    question_text = item["question"]

                    # Filter out questions that are too long
                    if len(question_text) <= MAX_QUESTION_LENGTH:

                        # Insert the correct answer into a random position among the available answers
                        all_answers = item["incorrect_answers"] + [item["correct_answer"]]
                        correct_answer = item["correct_answer"]
                        random.shuffle(all_answers)
                        correct_index = all_answers.index(correct_answer)
                        question = {
                            "question_id": len(questions) + 1,
                            "question_text": question_text,
                            "answer_a": all_answers[0],
                            "answer_b": all_answers[1],
                            "answer_c": all_answers[2],
                            "answer_d": all_answers[3],
                            "correct_answer": chr(97 + correct_index)  # Convert index to letter ('a', 'b', 'c', 'd')
                        }
                        questions.append(question)
            amount -= fetch_amount

        return questions
    except requests.RequestException as e:
        print(f"Error fetching trivia questions: {e}")
        return []


def initialize_questions():
    """
    Fetch trivia questions from an online source and upload them to MongoDB.
    """

    # Fetch trivia questions
    questions = fetch_trivia_questions()

    # Ensure that we have questions to upload
    if not questions:
        print("No questions to upload. Please try fetching trivia questions again later.")
        return

    # Connect to MongoDB
    client, db = connect_to_mongo()

    try:
        # Clear existing questions to avoid duplicates
        db.questions.delete_many({})

        # Insert new questions
        db.questions.insert_many(questions)
        print("Questions uploaded successfully to MongoDB.")
    except PyMongoError as e:
        print(f"Error uploading questions to MongoDB: {e}")
    finally:
        # Close the MongoDB connection
        client.close()


if __name__ == "__main__":
    initialize_questions()
