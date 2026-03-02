#!/usr/bin/env python3
"""Entry point for the LLM worker."""
from dotenv import load_dotenv
load_dotenv()

from src.main import run

if __name__ == "__main__":
    run()
