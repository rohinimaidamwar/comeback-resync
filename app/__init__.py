"""hercomeback app package. Loads .env before any module reads configuration from the environment."""

from dotenv import load_dotenv

load_dotenv()
