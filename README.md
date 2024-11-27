# Trivia Game Project

This is a trivia game where players answer questions, accumulate points, and track their progress. The backend is powered by PostgreSQL and MongoDB, and Docker is used to manage the databases.

## Prerequisites

To run this project, you need:

- Python 3.10+
- Docker
- PostgreSQL and MongoDB Docker containers
- Python libraries listed in `requirements.txt`

## Installation

1. **Clone the Repository**:

   Clone this repository to your local machine by running the following command:
   ```sh
   git clone https://github.com/your-username/trivia_game_project.git
   ```

   Navigate to the project directory:
   ```sh
   cd trivia_game_project
   ```

2. **Create a Virtual Environment (Optional but Recommended)**:

   It is recommended to create a virtual environment to manage your dependencies:
   ```sh
   python -m venv venv
   ```
   
   Activate the virtual environment:

   - On Windows:
     ```sh
     venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```sh
     source venv/bin/activate
     ```

3. **Install Dependencies**:

   Install all the necessary Python libraries using the `requirements.txt` file:
   ```sh
   pip install -r requirements.txt
   ```

4. **Set Up Environment Variables**:

   Copy the `.env.example` file to create your own `.env` file:
   ```sh
   cp .env.example .env
   ```
   Then, fill in the correct values for your database configuration (e.g., database name, username, password). The `.env.example` file provides guidance on which values are required.

## Running the Project

1. **Run Docker Containers for PostgreSQL and MongoDB**:

   Make sure Docker is running, and use Docker Compose to start the database containers:
   ```sh
   docker-compose up -d
   ```
   Ensure that the Docker containers for PostgreSQL and MongoDB are successfully running.

2. **Initialize Databases**:

    Initialize MongoDB by uploading the questions:
    ```sh
    python init_mongodb_database.py
    ```

   To update the number and difficulty of trivia questions fetched from the Open Trivia Database, you can modify the following parameters in the `init_mongodb_database.py` file:

   - `TRIVIA_QUESTION_AMOUNT`: Specifies the number of trivia questions to fetch (default is 300).
   - `TRIVIA_QUESTION_DIFFICULTY`: Specifies the difficulty level of the trivia questions ('easy', 'medium', 'hard'; default is 'easy').
   - `MAX_QUESTION_LENGTH`: You can change this value to filter question length (default is 60 from design considerations).

   For example, open `init_mongodb_database.py` and update the values:
   ```python
   # Define global parameters for trivia questions
   TRIVIA_QUESTION_AMOUNT: int = 300
   TRIVIA_QUESTION_DIFFICULTY: str = "easy"
   MAX_QUESTION_LENGTH: int = 60 
   ```

   These parameters will control how many questions are fetched and their difficulty level
   ```
   
   By default, the API only allows a maximum of 50 questions per request, therefore there are multiple requests.
   ```

   Initialize PostgreSQL tables, views, and procedures by running the appropriate Python script:
   ```sh
   python init_postgresql_database.py
   ```

3. **Run the Game**:

   To start the trivia game, run the main script:
   ```sh
   python main.py
   ```

## Project Structure

- **init_postgresql_database.py**: Sets up PostgreSQL tables, views, and procedures.
- **init_mongodb_database.py**: Initializes MongoDB with question data.
- **main.py**: The main entry point for the game.
- **actions_and_procedures_centralization.py**: Centralizes mappings for log actions and procedure details.
- **login_and_registration.py**: Manages player login and registration logic.
- **game_logic.py**: Contains functions related to game functionality.
- **postgresql_queries.py**: Handles PostgreSQL connections and procedures.
- **mongodb_queries.py**: Handles MongoDB operations.
- **validation.py**: Contains functions for validating user inputs.
- **statistics.py**: Manages displaying and executing game statistics.
- **statistical_graphs.py**: Generates graphs for different player and questions statistics.
- **test_application_functions.py**: Performing tests on the various functions of the game interface.
- **test_database_functions.py**: Performing tests on the various database functions (postgresql, mongodb).
- **.env**: Contains environment variables for database configuration.
- **requirements.txt**: Lists all dependencies required for the project.

## How to Play

- **Create New Player**: Create a new account to start playing.
- **Login**: Login with your username and password to continue your previous game or start a new one.
- **Show Statistics**: View your game statistics, including correct answers, unanswered questions, etc.
- **Exit**: Quit the game at any point.

## Troubleshooting

- **Connection Issues**: Make sure that Docker is running and the containers are properly set up.
- **Dependencies Not Installing**: Make sure to activate the virtual environment before running `pip install`.
- **Environment Variables Not Working**: Verify that the `.env` file is properly configured with valid database credentials and that the `python-dotenv` library is installed.
```

This version is formatted consistently with your request, and it provides all the necessary information in a clear and concise manner that you can copy directly into your `README.md` file.