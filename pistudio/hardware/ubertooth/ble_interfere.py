"""BLE connection interference via ubertooth-btle."""

import logging
import subprocess

logger = logging.getLogger(__name__)


def interfere_new_connections(duration_secs: int = 30) -> subprocess.Popen:
    """Interfere with newly established BLE connections (-f -i)."""
    cmd = ["ubertooth-btle", "-f", "-i"]
    logger.info("BLE interference (new connections) for %ds", duration_secs)
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def interfere_existing_connections(duration_secs: int = 30) -> subprocess.Popen:
    """Interfere with existing BLE connections (-p -I)."""
    cmd = ["ubertooth-btle", "-p", "-I"]
    logger.info("BLE interference (existing connections) for %ds", duration_secs)
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
