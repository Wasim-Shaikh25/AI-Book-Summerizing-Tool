import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from src.config import PDF_FOLDER, OUTPUT_FOLDER
from src.interaction.command_loop import CommandLoop

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """
    Entry point for the AI Knowledge Engine.
    """
    logger.info("Initializing AI Knowledge Engine...")
    
    # Start Command Loop immediately. Ingestion will be handled via terminal input.
    loop = CommandLoop()
    loop.start()

if __name__ == "__main__":
    main()
