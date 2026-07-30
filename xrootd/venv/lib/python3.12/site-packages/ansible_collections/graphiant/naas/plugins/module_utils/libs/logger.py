import logging
from datetime import datetime
from pathlib import Path as path


def setup_logger(level=logging.INFO):
    """
    Sets up a logger for the Graphiant Playbook with both file and console logging.

    Args:
        level (int): The logging level. Default is logging.INFO.

    Returns:
        logging.Logger: Configured logger instance.
    """

    logger = logging.getLogger("Graphiant_playbook")
    logger.setLevel(level)

    # Prevent duplicate handlers in Jupyter/IDE environments
    if not logger.handlers:
        cwd = path.cwd()
        logs_dir = cwd / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp_str = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        log_file = logs_dir / f"log_{timestamp_str}.log"

        # File handler
        fh = logging.FileHandler(log_file)
        fh.setLevel(level)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(level)

        # Formatter
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        # Add handlers
        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger
