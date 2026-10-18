"""Keep pytest's temporary files inside this review directory on restricted PCs."""
from pathlib import Path


def pytest_configure(config):
    if config.option.basetemp is None:
        config.option.basetemp = str(Path(__file__).resolve().parent / ".pytest_tmp")
