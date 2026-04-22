import sqlite3
from dataclasses import dataclass


@dataclass
class WordRecord:
    word: str
    language: str
    stem: str
    context: str
    origin: SourceBook

    def __eq__(self, other):
        return self.word == other.word and self.language == other.language

@dataclass
class SourceBook:
    title: str
    author: str
