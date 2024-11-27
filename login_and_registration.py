import bcrypt
import base64
from game_logic import game_status
from actions_and_procedures_centralization import get_game_action_details
from postgresql_queries import execute_pg_procedure
from mongodb_queries import log_action_mongo
from validation import (
    get_valid_input,
    is_valid_username,
    is_valid_password,
    is_valid_email,
    is_valid_age,
    is_valid_choice
)
from typing import Any, List, Tuple


def create_new_player(pg_connection: Any, mongo_db: Any) -> str | None:
    """
    Create a new player by collecting user details and saving them to the database.
    Ensures the username and email are unique.

    :param pg_connection: PostgreSQL connection object.
    :param mongo_db: MongoDB database object.
    """
    while True:
        # Collect and validate username
        username: str = get_valid_input(
            "Enter username (letters, digits, underscores, hyphens allowed, or type 'q' to quit): ",
            is_valid_username,
            "Invalid username. Please use only letters, digits, underscores, or hyphens."
        )

        if username.lower() == 'q':
            print("Exiting the login process. Returning to main menu.")
            return  # Exit the register process

        # Check if username is unique
        check_username_proc, _, _ = get_game_action_details("check_unique_username")
        try:
            username_unique: List[Tuple[bool]] = execute_pg_procedure(pg_connection, check_username_proc,
                                                                      [username])
        except Exception as e:
            print(f"Error checking username uniqueness: {e}")
            return

        if not username_unique[0][0]:
            print("The username is already in use. Please choose a different username.")
            continue

        # Collect and validate password
        password: str = get_valid_input(
            "Enter password (must contain at least 6 characters, one uppercase letter, one number, "
            "one special character, or type 'q' to quit): ",
            is_valid_password
        )

        if password.lower() == 'q':
            print("Exiting the login process. Returning to main menu.")
            return  # Exit the register process

        # Confirm password
        confirm_password: str = get_valid_input(
            "Confirm password (or type 'q' to quit): ",
            lambda x: x == password,
            "Passwords do not match. Please try again."
        )

        # Hash the password using bcrypt
        try:
            hashed_password_encoded = hash_password(password)
        except Exception as e:
            print(f"Error hashing password: {e}")
            return

        if confirm_password.lower() == 'q':
            print("Exiting the login process. Returning to main menu.")
            return  # Exit the register process

        # Collect and validate email
        email: str = get_valid_input(
            "Enter email (must follow a valid email pattern, or type 'q' to quit): ",
            is_valid_email,
            "Invalid email format. Please try again."
        )

        if email.lower() == 'q':
            print("Exiting the login process. Returning to main menu.")
            return  # Exit the login function

        # Check if email is unique
        check_email_proc, _, _ = get_game_action_details("check_unique_email")
        try:
            email_unique: List[Tuple[bool]] = execute_pg_procedure(pg_connection, check_email_proc, [email])
        except Exception as e:
            print(f"Error checking email uniqueness: {e}")
            return

        if not email_unique[0][0]:
            print("The email is already in use. Please choose a different email.")
            continue

        # Collect and validate age
        age_str: str = get_valid_input("Enter age: ", is_valid_age,
                                       "Invalid age. Please enter a positive reasonable age, "
                                       "or type 'q' to quit.")

        if age_str.lower() == 'q':
            print("Exiting the login process. Returning to main menu.")
            return  # Exit the register process

        age: int = int(age_str)

        # Get procedure details for creating player
        procedure_name, action_type, description = get_game_action_details("create_player")

        # Create new player in PostgreSQL
        try:
            execute_pg_procedure(pg_connection, procedure_name, [username, hashed_password_encoded, email, age])
        except Exception as e:
            print(f"Error creating new player: {e}")
            return

        # Log the action to MongoDB
        try:
            log_action_mongo(mongo_db, action_type, username, description, email)
        except Exception as e:
            print(f"Player created but failed to log the action: {e}")

        print(f"Player {username} created successfully!")
        return username


def player_login(pg_connection: Any, mongo_db: Any) -> str | None:
    """
    Handle player login by validating credentials.

    :param pg_connection: PostgreSQL connection object.
    :param mongo_db: MongoDB database object.
    """
    while True:
        # Collect and validate username
        username: str = get_valid_input(
            "Enter username (or type 'q' to quit): ",
            is_valid_username,
            "Invalid username. Please use only letters, digits, underscores, or hyphens."
        )

        if username.lower() == 'q':
            print("Exiting the login process. Returning to main menu.")
            return  # Exit the login process

        # Collect and validate password
        password: str = get_valid_input(
            "Enter password (or type 'q' to quit): ",
            is_valid_password
        )

        if password.lower() == 'q':
            print("Exiting the login process. Returning to main menu.")
            return  # Exit the login process

        # Get procedure details for login
        procedure_name, action_type, description = get_game_action_details("login")

        # Attempt to get the hashed password from the database
        try:
            hashed_password_result: List[Tuple[str]] = execute_pg_procedure(pg_connection, procedure_name,
                                                                            [username])
        except Exception as e:
            print(f"Error during login: {e}")
            return

        # Handle scenarios where username doesn't exist or password is incorrect
        if hashed_password_result[0][0] is None:
            print("Incorrect username or password.")
        else:
            hashed_password_encoded = hashed_password_result[0][0]  # Retrieve the hashed password from the result
            hashed_password = base64.b64decode(hashed_password_encoded)

            # Compare the provided password with the hashed password from the database
            if bcrypt.checkpw(password.encode(), hashed_password):
                print("Login successful!")

                try:
                    log_action_mongo(mongo_db, action_type, username, description)
                except Exception as e:
                    print(f"Login successful but failed to log the action: {e}")

                # Pass control to game_status for fetching questions
                return game_status(pg_connection, mongo_db, username)

            else:
                print("Incorrect username or password.")

        # Log failed login attempt
        _, action_type, description = get_game_action_details("failed_login")
        try:
            log_action_mongo(mongo_db, action_type, username, description)
        except Exception as e:
            print(f"Failed login but couldn't log the action: {e}")

        # Ask if the player wants to retry
        retry_choice: str = get_valid_input(
            "Do you want to try again? (y/n): ",
            lambda x: is_valid_choice(x.lower(), ['y', 'n']),
            "Invalid choice. Please enter 'y' or 'n'."
        ).lower()

        if retry_choice != 'y':
            print("Returning to the main menu.")
            return


def hash_password(password: str) -> str:
    """
    Hashes the given password using bcrypt and encodes it in base64.
    :param password: The password to hash.
    :return: The hashed and base64-encoded password.
    """
    # Convert password to bytes
    password_bytes = password.encode('utf-8')

    # Generate salt and hash the password
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt)

    # Encode the hashed password in base64
    encoded_password = base64.b64encode(hashed_password).decode('utf-8')
    return encoded_password
