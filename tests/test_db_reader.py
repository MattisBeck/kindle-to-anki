import pytest
import sqlite3

from kindle_to_anki.db_reader import *

@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:")
    with open("data/mock_vocab.sql", "r") as f:
        connection.executescript(f.read())

    yield connection

    connection.close()