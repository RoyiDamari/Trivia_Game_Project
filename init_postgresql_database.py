from postgresql_queries import connect_to_pg, close_pg_connection, execute_pg_statement
from mongodb_queries import connect_to_mongo
from pymongo.errors import PyMongoError
from dotenv import load_dotenv
from typing import Any, List, Dict


def create_tables(connection):
    """
    Creates the necessary tables in PostgreSQL.
    """
    table_statements = [
        # Table: questions
        """
        CREATE TABLE IF NOT EXISTS questions (
            question_id SERIAL PRIMARY KEY,
            correct_answer CHAR(1) CHECK (correct_answer IN ('a', 'b', 'c', 'd')) NOT NULL
        );
        """,

        # Table: players
        """
        CREATE TABLE IF NOT EXISTS players (
            player_id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            age INTEGER NOT NULL
        );
        """,

        # Table: game_sessions
        """
        CREATE TABLE IF NOT EXISTS game_sessions (
            session_id SERIAL PRIMARY KEY,
            player_id INTEGER REFERENCES players(player_id) ON DELETE CASCADE,
            start_time TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp(),
            end_time TIMESTAMP WITH TIME ZONE,
            questions_solved INTEGER DEFAULT 0,
            is_completed BOOLEAN DEFAULT FALSE,  -- Indicates if the session was completed
            is_active BOOLEAN DEFAULT TRUE       -- Indicates if the session is currently active
        );
        """,

        # Table: player_answers
        """
        CREATE TABLE IF NOT EXISTS player_answers (
            player_id INTEGER REFERENCES players(player_id) ON DELETE CASCADE,
            question_id INTEGER REFERENCES questions(question_id) ON DELETE CASCADE,
            session_id INTEGER REFERENCES game_sessions(session_id) ON DELETE CASCADE,
            selected_answer CHAR(1) CHECK (selected_answer IN ('a', 'b', 'c', 'd')) NOT NULL,
            is_correct BOOLEAN NOT NULL,
            answered_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp(),
            PRIMARY KEY (player_id, question_id, session_id)  -- Ties answer to a specific session
        );
        """,

        # Table: high_scores
        """
        CREATE TABLE IF NOT EXISTS high_scores (
            score_id INTEGER PRIMARY KEY CHECK (score_id >= 1 AND score_id <= 20), -- representing scores from 1 to 20
            player_id INTEGER REFERENCES players(player_id) ON DELETE CASCADE,
            total_time INTERVAL NOT NULL, -- Total time taken by the player to complete the game
            achieved_at TIMESTAMP WITH TIME ZONE NOT NULL
        );
        """
    ]

    try:
        for idx, statement in enumerate(table_statements, start=1):
            execute_pg_statement(connection, statement)
            print(f"Table creation statement {idx} executed successfully.")
    except Exception as e:
        print(f"Error creating tables: {e}")


def insert_initial_data(connection):
    """
    Inserts initial data into the database tables by fetching questions from MongoDB.
    """
    # Connect to MongoDB
    client, db = connect_to_mongo()
    try:
        # Fetch questions from MongoDB
        questions: List[Dict[str, Any]] = list(db.questions.find({}))

        if not questions:
            print("No questions found in MongoDB. Please initialize MongoDB first.")
            return

        # Insert questions into PostgreSQL
        for question in questions:
            statement = """
                INSERT INTO questions (question_id, correct_answer)
                VALUES (%s, %s)
            """
            params = (question["question_id"], question["correct_answer"])

            execute_pg_statement(connection, statement, params)
            print(f"Inserted question {question['question_id']} into PostgreSQL successfully.")

    except PyMongoError as e:
        print(f"Error fetching questions from MongoDB: {e}")
    except Exception as e:
        print(f"Error inserting initial data into PostgreSQL: {e}")
    finally:
        client.close()


def create_stored_procedures_and_functions(connection):
    """
    Creates or replaces stored procedures and functions in PostgreSQL.
    """
    sql_statements = [

        # functions for game logic
        # Stored Function: Checks if the provided username is unique.
        """
        CREATE OR REPLACE FUNCTION fn_check_unique_username(p_username VARCHAR)
        RETURNS BOOLEAN AS
        $$
        BEGIN
            RETURN NOT EXISTS (
                SELECT 1 FROM players WHERE username = p_username
            );
        END;
        $$ LANGUAGE plpgsql;
        """,

        # Stored Function: Checks if the provided email is unique.
        """
        CREATE OR REPLACE FUNCTION fn_check_unique_email(p_email VARCHAR)
        RETURNS BOOLEAN AS
        $$
        BEGIN
            RETURN NOT EXISTS (
                SELECT 1 FROM players WHERE email = p_email
            );
        END;
        $$ LANGUAGE plpgsql;
        """,

        # Stored Procedure: Creates a new player in the database.
        """
        CREATE OR REPLACE PROCEDURE sp_create_player(
         p_username VARCHAR,
         p_hashed_password_encoded VARCHAR,
         p_email VARCHAR,
         p_age INTEGER
        )
        LANGUAGE plpgsql AS 
        $$
        BEGIN
            INSERT INTO players (username, password, email, age)
            VALUES (p_username, p_hashed_password_encoded, p_email, p_age);
        END;
        $$;
        """,

        # Stored Function: Validates the player's login credentials.
        """
        CREATE OR REPLACE FUNCTION fn_login_player(
        p_username VARCHAR
        )
        RETURNS TEXT
        LANGUAGE plpgsql AS 
        $$
        DECLARE
            stored_password VARCHAR;
        BEGIN
            SELECT password 
            INTO stored_password 
            FROM players 
            WHERE username = p_username;
        
            RETURN stored_password;
        END;
        $$;
        """,

        # Stored Function: Retrieves unanswered questions for the player in the current active session.
        """
        CREATE OR REPLACE FUNCTION fn_get_unanswered_questions(p_username VARCHAR)
        RETURNS TABLE(question_id INT, correct_answer CHAR(1))
        LANGUAGE plpgsql AS 
        $$
        DECLARE
            v_player_id INT;
            v_session_id INT;
            questions_answered_count INT;
        BEGIN
            -- Get player ID
            SELECT p.player_id 
            INTO v_player_id
            FROM players p
            WHERE p.username = p_username;

            -- Check if there is an active session for the player
            SELECT gs.session_id 
            INTO v_session_id
            FROM game_sessions gs
            WHERE gs.player_id = v_player_id AND gs.is_completed = FALSE AND is_active = TRUE;

            -- If no active session found, create a new session
            IF NOT FOUND THEN
                -- Create a new session with incremented session_id
                INSERT INTO game_sessions (player_id) 
                VALUES (v_player_id)
                RETURNING session_id INTO v_session_id;
            END IF;

            -- Count the number of questions the player has answered in the current session
            SELECT COUNT(*)
            INTO questions_answered_count
            FROM player_answers pa
            WHERE pa.player_id = v_player_id AND pa.session_id = v_session_id;

            -- Return unanswered questions for the current session
            RETURN QUERY
            SELECT q.question_id, q.correct_answer
            FROM questions q
            WHERE q.question_id NOT IN (
                SELECT pa.question_id
                FROM player_answers pa
                WHERE pa.player_id = v_player_id AND pa.session_id = v_session_id
            )
            ORDER BY RANDOM()
            LIMIT (20 - questions_answered_count); -- Limit based on the number of remaining questions
        END;
        $$;
        """,

        # Stored Procedure: Records the player's answer to a question in the current active session.
        """
        CREATE OR REPLACE PROCEDURE sp_record_player_answers(
            p_username VARCHAR,
            p_question_id INT,
            p_selected_answer CHAR(1)
        )
        LANGUAGE plpgsql AS 
        $$
        DECLARE
            correct CHAR(1);
            v_player_id INT;
            v_session_id INT;
        BEGIN
            -- Get player ID
            SELECT p.player_id 
            INTO v_player_id 
            FROM players p
            WHERE p.username = p_username;

            -- Select the active session for this player
            SELECT gs.session_id 
            INTO v_session_id 
            FROM game_sessions gs
            WHERE gs.player_id = v_player_id AND gs.is_completed = FALSE AND is_active = TRUE;

            -- Get the correct answer for the question
            SELECT q.correct_answer 
            INTO correct 
            FROM questions q
            WHERE q.question_id = p_question_id;

            -- Insert the player's answer and check if it's correct
            INSERT INTO player_answers (player_id, question_id, session_id, selected_answer, is_correct)
            VALUES (v_player_id, p_question_id, v_session_id, p_selected_answer, (p_selected_answer = correct));
        END;
        $$;
        """,

        # Stored Procedure: Marks the player's current session as completed, inactive, and sets the end time.
        """
        CREATE OR REPLACE PROCEDURE sp_completing_session(p_username VARCHAR)
        LANGUAGE plpgsql AS 
        $$
        DECLARE
            v_player_id INT;
            v_session_id INT;
            v_end_time TIMESTAMP WITH TIME ZONE;
        BEGIN
            -- Get player ID
            SELECT p.player_id 
            INTO v_player_id 
            FROM players p
            WHERE p.username = p_username;

            -- Get the active session ID
            SELECT gs.session_id 
            INTO v_session_id 
            FROM game_sessions gs
            WHERE gs.player_id = v_player_id AND gs.is_completed = FALSE AND is_active = TRUE;

            -- Get time answered of last question
            SELECT max(pa.answered_at)
            INTO v_end_time
            FROM player_answers pa
            WHERE pa.session_id = v_session_id;

            -- Update current active session
            UPDATE game_sessions
            SET is_completed = TRUE, is_active = FALSE, end_time = v_end_time
            WHERE session_id = v_session_id;
            RAISE NOTICE 'Session completed for player %.', p_username;
        END;
        $$;
        """,

        # Stored Procedure: Resets the player's game progress, marks the current session as inactive,
        # and starts a new session.
        """
        CREATE OR REPLACE PROCEDURE sp_reset_player_answers(p_username VARCHAR)
        LANGUAGE plpgsql AS 
        $$
        DECLARE
            v_player_id INT;
            v_session_id INT;
        BEGIN
            -- Get player ID and the active session ID
            SELECT p.player_id 
            INTO v_player_id 
            FROM players p
            WHERE p.username = p_username;

            SELECT gs.session_id 
            INTO v_session_id
            FROM game_sessions gs
            WHERE gs.player_id = v_player_id AND gs.is_completed = FALSE AND is_active = TRUE;

            -- Delete the player's answers for the current session
            DELETE FROM player_answers 
            WHERE player_id = v_player_id AND session_id = v_session_id;

            -- Mark the current session as inactive
            UPDATE game_sessions
            SET is_active = FALSE
            WHERE session_id = v_session_id;

            RAISE NOTICE 'Player % has reset their current game session.', p_username;
        END;
        $$;
        """,

        # Stored Function: Retrieves the count of correct and incorrect answers for the player in the current
        # active session.
        """
        CREATE OR REPLACE FUNCTION fn_get_answer_stats(p_username VARCHAR)
        RETURNS TABLE(correct_count BIGINT, incorrect_count BIGINT) AS 
        $$
        DECLARE
            v_player_id INT;
            v_session_id INT;    
        BEGIN
            -- Get player ID and the current session ID
            SELECT p.player_id 
            INTO v_player_id 
            FROM players p
            WHERE p.username = p_username;

            SELECT gs.session_id 
            INTO v_session_id
            FROM game_sessions gs
            WHERE gs.player_id = v_player_id AND gs.is_completed = FALSE AND is_active = TRUE;

            -- Return counts of correct and incorrect answers for the current session
            RETURN QUERY
            SELECT 
                COUNT(CASE WHEN pa.is_correct THEN 1 END) AS correct_count,
                COUNT(CASE WHEN NOT pa.is_correct THEN 1 END) AS incorrect_count
            FROM player_answers pa
            WHERE pa.player_id = v_player_id AND pa.session_id = v_session_id;
        END;
        $$ LANGUAGE plpgsql;
        """,

        # Stored Procedure: Retrieves the number of correct answers for the player in the current session.
        """
        CREATE OR REPLACE FUNCTION fn_get_correct_answer_count(p_username VARCHAR)
        RETURNS INT AS 
        $$
        DECLARE
            v_player_id INT;
            v_session_id INT;
            correct_count INT;
        BEGIN
            -- Get player ID and the active session ID
            SELECT p.player_id 
            INTO v_player_id 
            FROM players p
            WHERE p.username = p_username;
            
            SELECT gs.session_id 
            INTO v_session_id 
            FROM game_sessions gs
            WHERE gs.player_id = v_player_id AND gs.is_completed = TRUE
            ORDER BY end_time DESC
            LIMIT 1;
        
            -- Count the number of correct answers in the current session
            SELECT COUNT(*)
            INTO correct_count
            FROM player_answers pa
            WHERE pa.player_id = v_player_id AND pa.session_id = v_session_id AND pa.is_correct = TRUE;
        
            RETURN correct_count;
        END;
        $$ LANGUAGE plpgsql;
        """,

        # Stored Procedure: Updates the high_scores table with the player's score and time if applicable.
        """
        CREATE OR REPLACE PROCEDURE sp_update_high_scores(p_username VARCHAR)
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_player_id INT;
            correct_answers INT;
            v_total_time INTERVAL;
            v_session_id INT;
            v_end_time TIMESTAMP WITH TIME ZONE;
        BEGIN
            -- Get player ID and the active session ID
            SELECT p.player_id 
            INTO v_player_id 
            FROM players p
            WHERE p.username = p_username;

            SELECT gs.session_id, gs.end_time 
            INTO v_session_id, v_end_time 
            FROM game_sessions gs
            WHERE gs.player_id = v_player_id AND gs.is_completed = TRUE
            ORDER BY gs.start_time DESC
            LIMIT 1;

            -- Count correct answers for the session
            SELECT COUNT(*) 
            INTO correct_answers 
            FROM player_answers pa
            WHERE pa.player_id = v_player_id AND pa.session_id = v_session_id AND pa.is_correct = TRUE;

            -- Calculate total time taken by the player for the session
            SELECT gs.end_time - gs.start_time 
            INTO v_total_time
            FROM game_sessions gs
            WHERE gs.session_id = v_session_id;

            -- Proceed if the player answered at least one question and has answered exactly 20 questions
            IF correct_answers > 0 AND (SELECT COUNT(*) 
                                        FROM player_answers pa 
                                        WHERE pa.player_id = v_player_id AND pa.session_id = v_session_id) = 20 THEN

                -- Update or insert a high score based on time
                IF EXISTS (SELECT 1 
                           FROM high_scores 
                           WHERE score_id = correct_answers) THEN
                    -- Update if current player's time is shorter
                    UPDATE high_scores 
                    SET player_id = v_player_id, total_time = v_total_time, achieved_at = v_end_time
                    WHERE score_id = correct_answers
                    AND total_time > v_total_time;
                ELSE
                    -- Insert new high score entry
                    INSERT INTO high_scores (score_id, player_id, total_time, achieved_at)
                    VALUES (correct_answers, v_player_id, v_total_time, v_end_time);
                END IF;
            END IF;
        END;
        $$;
        """,

        # Stored Function: Retrieves the high scores to display the player when the session end.
        """
        CREATE OR REPLACE FUNCTION fn_get_high_scores()
        RETURNS TABLE(
            player_id INT,
            username VARCHAR,
            email VARCHAR,
            score INT,
            total_time INTERVAL,
            achieved_at TIMESTAMP WITH TIME ZONE
        )
        LANGUAGE plpgsql AS
        $$
        BEGIN
            RETURN QUERY
            SELECT p.player_id, p.username, p.email, hs.score_id AS score, hs.total_time, hs.achieved_at
            FROM high_scores hs
            JOIN players p ON hs.player_id = p.player_id
            ORDER BY score DESC;
        END;
        $$;
        """,

        # Trigger Function: Trigger Fires after INSERT on player_answers to update the questions_solved
        # in game_sessions.
        """
        CREATE OR REPLACE FUNCTION fn_update_game_sessions()
        RETURNS TRIGGER AS
        $$
        BEGIN
            -- Update the questions_solved count based on the current number of entries in player_answers
            UPDATE game_sessions
            SET questions_solved = (
                SELECT COUNT(*)
                FROM player_answers
                WHERE session_id = NEW.session_id
            )
            WHERE session_id = NEW.session_id;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """,

        # Trigger: trg_update_game_sessions
        """
        CREATE TRIGGER trg_update_game_sessions
        AFTER INSERT ON player_answers
        FOR EACH ROW EXECUTE FUNCTION fn_update_game_sessions();
        """,
        # functions for statistics menu
        # Stored Function: Retrieves the question most frequently answered correctly.
        """
        CREATE OR REPLACE FUNCTION fn_get_most_correctly_answered_question()
        RETURNS TABLE(question_id INT, correct_count BIGINT)
        LANGUAGE plpgsql AS 
        $$
        BEGIN
            RETURN QUERY
            SELECT ps.question_id, COUNT(ps.player_id) AS correct_count
            FROM player_answers ps 
            WHERE ps.is_correct = TRUE
            GROUP BY ps.question_id
            HAVING COUNT(ps.player_id) = (
                SELECT MAX(m.correct_count)
                FROM (
                    SELECT COUNT(pa.player_id) AS correct_count
                    FROM player_answers pa
                    WHERE pa.is_correct = TRUE
                    GROUP BY pa.question_id
                ) m
            );
        END;
        $$;
        """,

        # Stored Function: Retrieves the question least frequently answered correctly.
        """
        CREATE OR REPLACE FUNCTION fn_get_least_correctly_answered_question()
        RETURNS TABLE(question_id INT, correct_count BIGINT)
        LANGUAGE plpgsql AS 
        $$
        BEGIN
            RETURN QUERY
            SELECT ps.question_id, COUNT(ps.player_id) AS correct_count
            FROM player_answers ps
            WHERE ps.is_correct = TRUE
            GROUP BY ps.question_id
            HAVING COUNT(ps.player_id) = (
                SELECT MIN(m.correct_count)
                FROM (
                    SELECT COUNT(pa.player_id) AS correct_count
                    FROM player_answers pa
                    WHERE pa.is_correct = TRUE
                    GROUP BY pa.question_id
                ) m
            );
        END;
        $$;
        """,

        # Stored Function: Retrieves answer statistics for a specific player.
        """
        CREATE OR REPLACE FUNCTION fn_get_player_answers_statistics(p_player_id INT)
        RETURNS TABLE(
            question_id INT,
            is_correct BOOLEAN
        ) AS
        $$
        BEGIN
            RETURN QUERY
            SELECT pa.question_id, pa.is_correct
            FROM player_answers pa
            WHERE pa.player_id = p_player_id
            ORDER BY pa.answered_at;
        END;
        $$ LANGUAGE plpgsql;
        """,

        # Stored Function: Retrieves statistics for each question: total answered, correct answers, incorrect answers.
        """
        CREATE OR REPLACE FUNCTION fn_get_question_answers_statistics()
        RETURNS TABLE(
            question_id INT,
            total_answered BIGINT,
            correct_answers BIGINT,
            incorrect_answers BIGINT
        ) AS
        $$
        BEGIN
            RETURN QUERY
            SELECT
                pa.question_id,
                COUNT(*) AS total_answered,
                SUM(CASE WHEN pa.is_correct THEN 1 ELSE 0 END) AS correct_answers,
                SUM(CASE WHEN NOT pa.is_correct THEN 1 ELSE 0 END) AS incorrect_answers
            FROM player_answers pa
            GROUP BY pa.question_id
            ORDER BY total_answered DESC;
        END;
        $$ LANGUAGE plpgsql;
        """,

        # Stored Function: Retrieves the counts of answered and not answered questions for the player.
        """
        CREATE OR REPLACE FUNCTION fn_get_player_answered_vs_not_answered(p_player_id INT)
        RETURNS TABLE(
            answered_count BIGINT,
            not_answered_count BIGINT
        ) AS
        $$
        DECLARE
            total_questions BIGINT;
        BEGIN
            -- Get total number of questions
            SELECT COUNT(*) INTO total_questions FROM questions;

            -- Get number of unique questions the player has answered
            SELECT COUNT(DISTINCT question_id) INTO answered_count
            FROM player_answers
            WHERE player_id = p_player_id;

            -- Calculate not answered count
            not_answered_count := total_questions - answered_count;

            RETURN QUERY SELECT answered_count, not_answered_count;
        END;
        $$ LANGUAGE plpgsql;
        """,

        # Stored Function: Retrieves the counts of correct and incorrect answers for the player.
        """
        CREATE OR REPLACE FUNCTION fn_get_player_correct_incorrect_answers(p_player_id INT)
        RETURNS TABLE(
            correct_count BIGINT,
            incorrect_count BIGINT
        ) AS
        $$
        DECLARE
            correct_count BIGINT;
            incorrect_count BIGINT;
        BEGIN
            -- Get number of correct answers
            SELECT COUNT(*) INTO correct_count
            FROM player_answers
            WHERE player_id = p_player_id AND is_correct = TRUE;
        
            -- Get number of incorrect answers
            SELECT COUNT(*) INTO incorrect_count
            FROM player_answers
            WHERE player_id = p_player_id AND is_correct = FALSE;
        
            RETURN QUERY SELECT correct_count, incorrect_count;
        END;
        $$ LANGUAGE plpgsql;
        """,
    ]

    for idx, statement in enumerate(sql_statements, start=1):
        try:
            execute_pg_statement(connection, statement)
            print(f"Successfully executed stored procedure/function {idx}/{len(sql_statements)}.")
        except Exception as e:
            print(f"Error executing stored procedure/function {idx}/{len(sql_statements)}: {e}")


def create_views(connection):
    """
    Creates or replaces views in PostgreSQL.
    """
    view_statements = [

        # views for statistics menu
        # View: Retrieves the total number of players.
        """
        CREATE OR REPLACE VIEW vw_total_players AS
        SELECT COUNT(*) AS total_players
        FROM players;
        """,

        # View: Retrieves players ordered by the number of their correct answers.
        """
        CREATE OR REPLACE VIEW vw_players_by_correct_answers AS
        SELECT p.username, COUNT(pa.player_id) AS correct_answers
        FROM player_answers pa
        JOIN players p ON pa.player_id = p.player_id
        WHERE pa.is_correct = TRUE
        GROUP BY p.username
        ORDER BY correct_answers DESC;
        """,

        # View: Retrieves players ordered by the total number of their answers.
        """
        CREATE OR REPLACE VIEW vw_players_by_total_answers AS
        SELECT p.username, COUNT(pa.player_id) AS total_answers
        FROM player_answers pa
        JOIN players p ON pa.player_id = p.player_id
        GROUP BY p.username
        ORDER BY total_answers DESC;
        """
    ]

    for idx, statement in enumerate(view_statements, start=1):
        try:
            execute_pg_statement(connection, statement)
            print(f"View creation statement {idx} executed successfully.")

        except Exception as e:
            print(f"Error creating view {idx}: {e}")


def main():
    """
    Main function to initialize the PostgreSQL database.
    """
    # Load environment variables
    load_dotenv()

    # Connect to PostgreSQL
    try:
        connection = connect_to_pg()
        print("Connected to PostgreSQL successfully.")
    except Exception as e:
        print(f"Failed to connect to PostgreSQL: {e}")
        return

    try:
        print("Creating tables...")
        create_tables(connection)

        print("Inserting initial data...")
        insert_initial_data(connection)

        print("Creating stored procedures and functions...")
        create_stored_procedures_and_functions(connection)

        print("Creating views...")
        create_views(connection)

        print("Database initialization completed successfully.")
    except Exception as e:
        print(f"Error during database initialization: {e}")
    finally:
        close_pg_connection(connection)
        print("PostgreSQL connection closed.")


if __name__ == "__main__":
    main()
