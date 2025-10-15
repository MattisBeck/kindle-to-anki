#!/usr/bin/env python3
"""
Kindle to Anki Converter - Legacy Entry Point

This file is now a thin wrapper for the modular package.
The actual implementation is in the kindle_to_anki/ package.

Usage:
    python kindle-to-anki.py
    
Or directly:
    python -m kindle_to_anki.main
"""

from kindle_to_anki.main import main

if __name__ == "__main__":
    main()
