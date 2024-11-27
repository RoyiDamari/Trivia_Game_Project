import re
from typing import Callable, List


def get_valid_input(prompt: str, validation_func: Callable[[str], bool], error_message: str = "",
                    exit_keyword: str = 'q') -> str:
    """
    Prompt the user for input and validate it using the provided validation function.
    Allows user to type a specific keyword to exit.

    :param prompt: The message displayed to the user when asking for input.
    :param validation_func: A function that takes a string input and returns a boolean indicating validity.
    :param error_message: The error message to display if validation fails.
    :param exit_keyword: The keyword that the user can type to exit.
    :return: The valid user input or the exit keyword.
    """
    while True:
        user_input: str = input(prompt)
        if user_input.lower() == exit_keyword:
            return exit_keyword
        if validation_func(user_input):
            return user_input
        if error_message:
            print(error_message)


def is_valid_username(username: str) -> bool:
    """
    Validate that the username contains only allowed characters (letters, digits, underscores, hyphens).

    :param username: The username to validate.
    :return: True if valid, False otherwise.
    """
    return bool(re.match(r"^[A-Za-z0-9_-]+$", username))


def is_valid_password(password: str) -> bool:
    """
    Validate that the password meets complexity requirements.

    :param password: The password to validate.
    :return: True if valid, False otherwise.
    """
    if len(password) < 6:
        print("Password must be at least 6 characters long.")
        return False
    if not re.search(r"[A-Z]", password):
        print("Password must contain at least one uppercase letter.")
        return False
    if not re.search(r"\d", password):
        print("Password must contain at least one number.")
        return False
    if not re.search(r"\W", password):
        print("Password must contain at least one special character.")
        return False
    return True


def is_valid_email(email: str) -> bool:
    """
    Validate that the email address is in a valid format.

    :param email: The email address to validate.
    :return: True if valid, False otherwise.
    """
    email_regex: str = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    return bool(re.match(email_regex, email))


def is_valid_age(age: str) -> bool:
    """
    Validate that the age input is a positive integer.

    :param age: The age input to validate.
    :return: True if valid, False otherwise.
    """
    return age.isdigit() and 0 < int(age) < 100


def is_valid_choice(user_input: str, valid_choices: List[str]) -> bool:
    """
    Validate if the user_input is within a set of valid choices.

    :param user_input: The input provided by the user.
    :param valid_choices: List of valid options.
    :return: True if the input is valid, False otherwise.
    """
    return user_input.lower() in valid_choices
