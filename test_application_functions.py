from main import main
import pytest
from unittest.mock import patch
from login_and_registration import create_new_player, hash_password
from statistics import show_statistics
import bcrypt
import base64
from validation import (
    get_valid_input,
    is_valid_username,
    is_valid_password,
    is_valid_email,
    is_valid_age,
    is_valid_choice,
)


# Test main function
@pytest.mark.parametrize("inputs, expected_calls", [
    (['1', '4'], [("create_new_player", 1), ("player_login", 0), ("show_statistics", 0)]),
    (['2', '4'], [("create_new_player", 0), ("player_login", 1), ("show_statistics", 0)]),
    (['3', '4'], [("create_new_player", 0), ("player_login", 0), ("show_statistics", 1)]),
    (['invalid', '4'], [("create_new_player", 0), ("player_login", 0), ("show_statistics", 0)]),
])
@patch('main.create_new_player', return_value="test_username")
@patch('main.player_login', return_value="test_username")
@patch('main.show_statistics')
@patch('main.connect_to_pg', return_value="pg_connection_mock")
@patch('main.connect_to_mongo', return_value=("mongo_client_mock", "mongo_db_mock"))
@patch('main.close_pg_connection')
@patch('main.close_mongo_connection')
@patch('builtins.input')
def test_main(mock_input, mock_close_mongo, mock_close_pg, mock_connect_mongo, mock_connect_pg,
              mock_show_statistics, mock_player_login, mock_create_new_player, inputs, expected_calls):
    """
    Test the main function by mocking `create_new_player` to return the username directly.
    """

    # Mock user inputs for the main menu
    mock_input.side_effect = inputs

    # Run the main function
    main()

    # Verify the calls to create_new_player, player_login, and show_statistics
    assert mock_create_new_player.call_count == expected_calls[0][1]
    assert mock_player_login.call_count == expected_calls[1][1]
    assert mock_show_statistics.call_count == expected_calls[2][1]

    # Verify the database connections were opened and closed
    mock_connect_pg.assert_called_once()
    mock_connect_mongo.assert_called_once()
    mock_close_pg.assert_called_once_with("pg_connection_mock")
    mock_close_mongo.assert_called_once_with("mongo_client_mock")


# Test connection failing
@pytest.mark.parametrize("db_error, expected_output", [
    (Exception("PostgreSQL connection failed"), "Failed to connect to databases: PostgreSQL connection failed"),
    (Exception("MongoDB connection failed"), "Failed to connect to databases: MongoDB connection failed"),
])
@patch('main.connect_to_pg')
@patch('main.connect_to_mongo')
@patch('builtins.print')
def test_main_database_connection_failure(mock_print, mock_connect_mongo, mock_connect_pg, db_error, expected_output):
    """
    Test the main function to handle database connection failures.
    """
    # Simulate database connection failure
    if "PostgreSQL" in str(db_error):
        mock_connect_pg.side_effect = db_error
    elif "MongoDB" in str(db_error):
        mock_connect_mongo.side_effect = db_error

    # Import and run the main function
    from main import main
    main()

    # Verify the error message is printed
    assert any(expected_output in call[0][0] for call in mock_print.call_args_list)


# Test cases for is_valid_username function
def test_get_valid_input_with_is_valid_username():
    """
    Test get_valid_input with is_valid_username to ensure it validates and returns correct input.
    """
    with patch("validation.input", side_effect=["invalid username", "invalid_user!", "", "invaliduser@name",
                                                "valid_username123", "q"]):
        result = get_valid_input(
            "Enter username: ",
            validation_func=is_valid_username,
            error_message="Invalid username, try again.",
            exit_keyword="q"
        )
        assert result == "valid_username123"  # Valid input is returned


# Test cases for is_valid_password function
def test_get_valid_input_with_is_valid_password():
    """
    Test get_valid_input with is_valid_password to ensure it validates and returns correct input.
    """
    with patch("validation.input", side_effect=["short", "NoNumber!", "no1uppercase2letter",
                                                "No1special2character", "", "Valid123!", "q"]):
        result = get_valid_input(
            "Enter password: ",
            validation_func=is_valid_password,
            error_message="Invalid password, try again.",
            exit_keyword="q"
        )
        assert result == "Valid123!"  # Valid input is returned


# Test cases for is_valid_email function
def test_get_valid_input_with_is_valid_email():
    """
    Test get_valid_input with is_valid_email to ensure it validates and returns correct input.
    """
    with patch("validation.input", side_effect=["invalid-email.com", "invalid-email@", "",
                                                "test+alias@domain.com", "q"]):
        result = get_valid_input(
            "Enter email: ",
            validation_func=is_valid_email,
            error_message="Invalid email, try again.",
            exit_keyword="q"
        )
        assert result == "test+alias@domain.com"  # Valid input is returned


# Test cases for is_valid_age function
def test_get_valid_input_with_is_valid_age():
    """
    Test get_valid_input with is_valid_age to ensure it validates and returns correct input.
    """
    with patch("validation.input", side_effect=["-1", "0", "105", "abc", "", "25", "q"]):
        result = get_valid_input(
            "Enter age: ",
            validation_func=is_valid_age,
            error_message="Invalid age, try again.",
            exit_keyword="q"
        )
        assert result == "25"  # Valid input is returned


# Test for valid player statistic menu option choice
def test_get_valid_input_with_is_valid_choice_show_statistics():
    """
    Test get_valid_input with is_valid_choice to ensure it validates and returns correct input.
    """
    valid_choices = [str(i) for i in range(1, 13)]
    with patch("validation.input", side_effect=["abc", "-10", "abc123", "", "0", "2", "q"]):
        result = get_valid_input(
            "Enter choice: ",
            validation_func=lambda x: is_valid_choice(x, valid_choices),
            error_message="Invalid choice, try again.",
            exit_keyword="q"
        )
        assert result == "2"  # Valid input is returned


# Test for valid continue game choice
def test_get_valid_input_with_is_valid_choice_player_login_game_status():
    """
    Test get_valid_input with is_valid_choice to ensure it validates and returns correct input.
    """
    valid_choices = ['y', 'n']
    with patch("validation.input", side_effect=["abc", "10", "", "yes", "maybe", "n", "y"]):
        result = get_valid_input(
            "Enter choice: ",
            validation_func=lambda x: is_valid_choice(x.lower(), valid_choices),
            error_message="Invalid choice, try again.",
        ).lower()
        # Assert that the returned value matches the first valid input in the sequence
        assert result == "n"  # Valid input returned


# Test for valid player answer choice
def test_get_valid_input_with_is_valid_choice_play_game():
    """
    Test get_valid_input with is_valid_choice to ensure it validates and returns correct input.
    """
    valid_choices = ['a', 'b', 'c', 'd', 'q', 's']
    with patch("validation.input", side_effect=["abc", "10", "", "yes", "maybe", "n", "a"]):
        result = get_valid_input(
            "Enter choice: ",
            validation_func=lambda x: is_valid_choice(x.lower(), valid_choices),
            error_message="Invalid choice, try again.",
        ).lower()
        # Assert that the returned value matches the first valid input in the sequence
        assert result == "a"  # Valid input returned


# Test for failed confirmation password
@patch("login_and_registration.get_valid_input")
@patch("login_and_registration.execute_pg_procedure")
def test_create_new_player_passwords_do_not_match(mock_execute_pg, mock_get_input):
    """
    Test for creating a new player when confirm password does not match the original password.
    """
    # Use simple strings to represent connections for PostgreSQL and MongoDB
    pg_connection = "pg_connection_mock"
    mongo_db = "mongo_db_mock"

    # Define expected behaviors of mocked functions
    mock_get_input.side_effect = [
        "test_user",       # Simulates the user entering a username
        "ValidPass@123",   # Simulates the user entering a password
        "DifferentPass@123",  # Simulates the user entering confirm password that doesn't match
        "q"  # Simulates the user deciding to quit after failed confirm password match
    ]

    # Simulate the database recognizing the username and email as unique
    mock_execute_pg.side_effect = [
        [(True,)],  # Username is unique
        [(True,)],  # Email is unique
    ]

    # Run the create_new_player function
    result = create_new_player(pg_connection, mongo_db)

    # Assert that the function returns None (because passwords did not match)
    assert result is None


# Test for successfully hashing function
def test_password_hashing():
    """
    Test the hash_password function to ensure it correctly hashes the password.
    """
    password = "ValidPass@123"

    # Hash the password using the hash_password function
    hashed_password = hash_password(password)

    # Decode the Base64 hashed password to its original form
    hashed_password_bytes = base64.b64decode(hashed_password)

    # Verify that bcrypt can correctly match the original password with the hashed version
    assert bcrypt.checkpw(password.encode(), hashed_password_bytes)


# Test for checking execute_statistics_procedure function has been successfully called
@patch("statistics.get_valid_input")
@patch("statistics.execute_statistics_procedure")
def test_show_statistics_valid_navigation(mock_execute_statistics, mock_get_valid_input):
    """
    Test navigation through the statistics menu for all valid options.
    """
    # Generate input sequence for all valid options, followed by 12 to exit
    all_options = [str(i) for i in range(1, 13)]  # Options 1 to 12
    mock_get_valid_input.side_effect = all_options  # Simulate user selecting each option

    # Mock connections
    pg_connection = "pg_connection_mock"
    mongo_db = "mongo_db_mock"

    # Call the function
    show_statistics(pg_connection, mongo_db, username="test_user")

    # Verify execute_statistics_procedure is called for all options except 12 (exit)
    for option in all_options[:-1]:  # Skip the last option (exit)
        mock_execute_statistics.assert_any_call(pg_connection, mongo_db, option, "test_user")

    # Ensure the number of calls matches the number of valid options minus the exit option
    assert mock_execute_statistics.call_count == len(all_options) - 1


# Test for successfully exit from show_statistics function
@patch("statistics.get_valid_input")
@patch("statistics.execute_statistics_procedure")
def test_show_statistics_exit(mock_execute_statistics, mock_get_valid_input):
    """
    Test that show_statistics returns None when the user chooses to exit (option 12),
    regardless of whether the username parameter is provided.
    """
    # Simulate user input to exit directly
    mock_get_valid_input.side_effect = iter(["12", "12"])

    # Mock connections
    pg_connection = "pg_connection_mock"
    mongo_db = "mongo_db_mock"

    # Call the function with username as None
    assert show_statistics(pg_connection, mongo_db, username=None) is None
    mock_execute_statistics.assert_not_called()

    # Call the function with a username
    assert show_statistics(pg_connection, mongo_db, username="test_user") is None
    mock_execute_statistics.assert_not_called()


# Test for valid player id choice
def test_get_valid_input_for_player_id():
    """
    Test the `get_valid_input` function to ensure it correctly validates numeric player IDs.
    """
    # Mock user input: first three are invalid, then a valid input
    user_inputs = ["abc", "123abc", "", "42"]  # Invalid inputs followed by a valid one
    expected_result = "42"  # Valid player ID as a string

    with patch("builtins.input", side_effect=user_inputs):
        player_id_str = get_valid_input(
            "Enter player ID: ",
            lambda x: x.isdigit(),
            "Invalid player ID. Please enter a valid number."
        )

    # Assert that the returned player ID is the expected valid one
    assert player_id_str == expected_result
