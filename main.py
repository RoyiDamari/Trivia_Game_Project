from postgresql_queries import connect_to_pg, close_pg_connection
from mongodb_queries import connect_to_mongo, close_mongo_connection
from login_and_registration import player_login, create_new_player
from statistics import show_statistics
from validation import is_valid_choice
from typing import Any


def display_main_menu() -> None:
    """
    Display the main menu options.
    """
    print("\nGame Menu:")
    print("1. Create New Player")
    print("2. Login")
    print("3. Show Statistics")
    print("4. Exit")


def main() -> None:
    """
    Main function that handles the game flow and connections.
    """
    # Connect to PostgreSQL and MongoDB
    try:
        pg_connection: Any = connect_to_pg()
        mongo_client, mongo_db = connect_to_mongo()
        print("Connected to PostgreSQL and MongoDB successfully.")
    except Exception as e:
        print(f"Failed to connect to databases: {e}")
        return

    username = None

    try:
        while True:
            display_main_menu()

            choice: str = input("Enter your choice: ")
            if not is_valid_choice(choice, ['1', '2', '3', '4']):
                print("Invalid choice, please enter a valid number.")
                continue
            if choice == '1':
                username = create_new_player(pg_connection, mongo_db)
            elif choice == '2':
                username = player_login(pg_connection, mongo_db)
            elif choice == '3':
                if username:
                    show_statistics(pg_connection, mongo_db, username)
                else:
                    show_statistics(pg_connection, mongo_db, None)
            elif choice == '4':
                print("Goodbye!")
                break

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        # Cleanup connections
        try:
            close_pg_connection(pg_connection)
        except Exception as e:
            print(f"Error closing PostgreSQL connection: {e}")

        try:
            close_mongo_connection(mongo_client)
        except Exception as e:
            print(f"Error closing MongoDB connection: {e}")


if __name__ == "__main__":
    main()
