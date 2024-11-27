import psycopg2
from psycopg2.extensions import connection
from typing import Any, List, Tuple
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def connect_to_pg() -> connection:
    """
    Connect to PostgreSQL.
    :return: PostgreSQL connection object.
    """
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        port=os.getenv("POSTGRES_PORT")
    )


def execute_pg_procedure(
    db_connection: connection,
    object_name: str,
    params: List[Any] | None = None
) -> List[Tuple] | None:
    """
    Executes a stored procedure, function, or SELECT query on a view in PostgreSQL.

    :param db_connection: The PostgreSQL connection object.
    :param object_name: The name of the stored procedure, function, or view to execute/query.
    :param params: Parameters for the stored procedure or function (optional).
    :return: The result of the query (if any), otherwise None.
    """
    cursor = db_connection.cursor()

    try:
        if object_name.startswith("sp_"):  # Stored Procedures
            if params:
                param_placeholders = ', '.join(['%s'] * len(params))
                cursor.execute(f"CALL {object_name}({param_placeholders});", params)
            else:
                cursor.execute(f"CALL {object_name}();")
            db_connection.commit()
            results = None

        elif object_name.startswith("fn_"):  # Stored Functions
            if params:
                param_placeholders = ', '.join(['%s'] * len(params))
                cursor.execute(f"SELECT * FROM {object_name}({param_placeholders});", params)
            else:
                cursor.execute(f"SELECT * FROM {object_name}();")
            results = cursor.fetchall()

        elif object_name.startswith("vw_"):  # Views
            if params:
                # Assuming views don't require parameters. If they do, adjust accordingly.
                print("Views do not accept parameters. Ignoring provided parameters.")
            cursor.execute(f"SELECT * FROM {object_name};")
            results = cursor.fetchall()

        else:
            raise ValueError(f"Unknown object type for '{object_name}'. Please prefix with 'sp_', 'fn_', or 'vw_'.")

        return results

    except psycopg2.DatabaseError as e:
        print(f"Database error occurred while executing '{object_name}': {e}")
        db_connection.rollback()
        raise

    finally:
        cursor.close()


def execute_pg_statement(db_connection, statement, params=None):
    """
    Executes a PostgreSQL statement with optional parameters.

    :param db_connection: PostgreSQL connection object.
    :param statement: SQL statement to be executed.
    :param params: Optional tuple of parameters for the statement.
    """
    try:
        with db_connection.cursor() as cursor:
            if params:
                cursor.execute(statement, params)
            else:
                cursor.execute(statement)
            db_connection.commit()
            print("SQL statement executed successfully.")
    except psycopg2.Error as e:
        db_connection.rollback()
        print(f"Error executing statement: {e}")


def close_pg_connection(db_connection: connection) -> None:
    """
    Close the PostgreSQL connection.
    """
    db_connection.close()
