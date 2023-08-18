# --- Imports ---

# Standard library imports

# For reading and writing JSON files
import json

# For logging application processes and errors
import logging

# Python's built-in serialization module for storing python objects on disk
import pickle

# Path manipulation utilities for file and directory operations
from pathlib import Path

# Third-party libraries

# web3: Python library for Ethereum blockchain interaction
import web3
from web3 import Web3

# rich: Library for enhanced command-line printing, progress tracking, and logging
from rich import print
from rich.logging import RichHandler
from rich.progress import track

# Internal or project-specific imports

# Constants for paths and default settings
from constants import DATA_PATH, DEPENDENCY_CONTRACTS_PATH, DEFAULT_PRINT_COLOR

# --- Logging Configuration ---

# Configuring rich logger for enhanced visual feedback in the command-line interface
logging.basicConfig(
    level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler()]
)
log = logging.getLogger("rich")


def connect_to_rpc_provider(rpc: str) -> Web3:
    """
    Establishes a connection to an RPC provider and returns a Web3 instance.

    This function intelligently selects the appropriate provider (HTTP, WebSocket, or IPC)
    based on the structure of the given RPC URL:
    - HTTP: For URLs starting with 'http://' or 'https://'
    - WebSocket: For URLs starting with 'ws://' or 'wss://'
    - IPC: For URLs ending with '.ipc'

    Args:
        rpc (str): The RPC provider URL to connect to.

    Returns:
        Web3: An instance of Web3 connected to the RPC provider.

    Raises:
        ValueError: If the RPC URL format is unrecognized.
        ConnectionError: If unable to connect to the given RPC provider.
    """

    if rpc.startswith(("http://", "https://")):
        w3 = Web3(Web3.HTTPProvider(rpc))
    elif rpc.startswith(("ws://", "wss://")):
        w3 = Web3(Web3.WebsocketProvider(rpc))
    elif rpc.endswith(".ipc"):
        w3 = Web3(Web3.IPCProvider(rpc))
    else:
        log.error("Invalid RPC URL format.")
        raise ValueError("Invalid RPC URL format.")

    if not w3.is_connected():
        log.error("Unable to connect to RPC provider.")
        raise ConnectionError("Unable to connect to RPC provider.")

    return w3


def using_cache(data_filename: str):
    """
    Decorator to manage caching and retrieval of data.

    This function checks if cached data exists and is still valid (not needing a refresh).
    If the cached data is not present or outdated, it fetches fresh data, caches it,
    and then returns it.

    Args:
        data_filename (str): The filename of the data to check for in the cache.

    Returns:
        function: A wrapped function that manages the caching behavior.
    """

    # Create the full path to the cache file with a .pkl suffix
    path = (Path(DATA_PATH) / data_filename).with_suffix(".pkl")

    def using_cache_with_path(get_data):
        def get_data_with_cache(*args, refresh=False):
            # Check if cache file exists and if refresh is not requested
            if path.is_file() and not refresh:
                try:
                    # Try to load data from the cache
                    with path.open("rb") as f:
                        data = pickle.load(f)
                    log.info(f"Loaded data from cache: {path}")
                except Exception as e:
                    log.error(f"Error loading data from cache.")
                    # Fallback to get fresh data if there's an error loading from cache
                    data = get_data(*args)
            else:
                data = get_data(*args)

                try:
                    # Cache the fresh data for future use
                    with path.open("wb") as f:
                        pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)
                    log.info(f"Saved data to cache: {path}")
                except Exception as e:
                    log.error(f"Error saving data to cache.")

            return data

        return get_data_with_cache

    return using_cache_with_path


def get_abi_from_json(contract_name: str) -> dict:
    """
    Retrieve the ABI (Application Binary Interface) for a given Ethereum contract
    from a JSON file.

    Parameters:
    - contract_name (str): The name of the Ethereum contract whose ABI is to be loaded.

    Returns:
    - dict: The ABI for the given contract.

    Raises:
    - FileNotFoundError: If the ABI JSON file for the contract is not found.
    - json.JSONDecodeError: If there's an error decoding the JSON file.
    """

    # Construct the path to the ABI JSON file for the specified contract
    abi_path = (Path(DEPENDENCY_CONTRACTS_PATH) / contract_name).with_suffix(".json")

    try:
        # Load the ABI from the JSON file
        with abi_path.open("r") as f:
            abi = json.load(f)
            log.info(f"Successfully loaded ABI for contract: {contract_name}")
            return abi

    # Handle exceptions related to missing files and JSON decoding errors
    except FileNotFoundError:
        log.error(
            f"Could not find ABI file for contract: {contract_name} at path: {abi_path}"
        )
        raise
    except json.JSONDecodeError:
        log.error(f"Error decoding JSON for contract: {contract_name}")
        raise


def get_pair_info(w3: Web3, ABIs: dict, pair) -> dict:
    """
    Retrieve information about a specific Uniswap V2 pair contract.

    Parameters:
    - w3 (Web3): The Web3 instance to interact with the Ethereum network.
    - ABIs (dict): A dictionary of contract names to their ABIs.
    - pair (str): The Ethereum address of the Uniswap V2 pair contract.

    Returns:
    - dict: A dictionary containing details of the pair, specifically the
            tokens involved and their reserves.

    Raises:
    - Exception: Any errors encountered while retrieving pair information.
    """

    try:
        pair_contract = w3.eth.contract(address=pair, abi=ABIs["UniswapV2Pair"])

        token0 = pair_contract.functions.token0().call()
        token1 = pair_contract.functions.token1().call()

        reserves = pair_contract.functions.getReserves().call()

        pair_info = {
            "token0": token0,
            "token1": token1,
            "reserves": reserves,
        }

        return pair_info

    except Exception as e:
        log.error(f"Error retrieving pair info for pair address: {pair}")
        raise


def get_token_info(w3: Web3, ABIs: dict, token) -> dict:
    """
    Retrieve basic information (symbol and decimals) about a specific ERC20 token contract.

    Parameters:
    - w3 (Web3): The Web3 instance to interact with the Ethereum network.
    - ABIs (dict): A dictionary of contract names to their ABIs.
    - token (str): The Ethereum address of the ERC20 token contract.

    Returns:
    - dict: A dictionary containing the symbol and decimals of the token.

    Note:
    - In cases where the token contract does not provide a symbol or decimals correctly,
      default values of '__BAD_SYMBOL__' for symbol and 18 for decimals are returned.
    """

    token_contract = w3.eth.contract(address=token, abi=ABIs["ERC20"])

    try:
        symbol = token_contract.functions.symbol().call()
    except Exception as e:
        log.warning(
            f"Error retrieving symbol for token address: {token}. Defaulting to '__BAD_SYMBOL__'"
        )
        symbol = "__BAD_SYMBOL__"

    try:
        decimals = token_contract.functions.decimals().call()
    except Exception as e:
        log.warning(
            f"Error retrieving decimals for token address: {token}. Defaulting to 18"
        )
        decimals = 18

    token_info = {
        "symbol": symbol,
        "decimals": decimals,
    }

    return token_info


def get_pairs_info(w3: Web3, ABIs: dict, pairs: list[str]) -> dict[str, dict]:
    """
    Retrieve information about a list of UniswapV2 pairs.

    Parameters:
    - w3 (Web3): The Web3 instance to interact with the Ethereum network.
    - ABIs (dict): A dictionary of contract names to their ABIs.
    - pairs (list[str]): A list of Ethereum addresses representing UniswapV2 pairs.

    Returns:
    - dict[str, dict]: A dictionary where the keys are pair addresses and the values are
      dictionaries containing information about each pair.

    Uses:
    - The function leverages the `get_pair_info` function for each pair in the list.
    - It also uses `track` to provide a progress bar while fetching the pair information.
    """

    pairs_info = {
        pair: get_pair_info(w3, ABIs, pair)
        for pair in track(pairs, description="Fetching information about pairs")
    }
    return pairs_info


def get_tokens_info(w3: Web3, ABIs: dict, tokens: list[str]) -> dict[str, dict]:
    """
    Retrieve information about a list of ERC20 tokens.

    Parameters:
    - w3 (Web3): The Web3 instance to interact with the Ethereum network.
    - ABIs (dict): A dictionary of contract names to their ABIs.
    - tokens (list[str]): A list of Ethereum addresses representing ERC20 tokens.

    Returns:
    - dict[str, dict]: A dictionary where the keys are token addresses and the values are
      dictionaries containing information about each token.

    Uses:
    - The function leverages the `get_token_info` function for each token in the list.
    - It also uses `track` to provide a progress bar while fetching the token information.
    """

    tokens_info = {
        token: get_token_info(w3, ABIs, token)
        for token in track(tokens, description="Fetching information about tokens")
    }
    return tokens_info


def get_tokens_from_pairs(pairs_info: dict) -> set:
    """
    Extract unique token addresses from pair information.

    Parameters:
    - pairs_info (dict): A dictionary containing information about pairs. Each key
      is a pair address, and the associated value is another dictionary containing
      details of the pair, particularly the addresses of "token0" and "token1".

    Returns:
    - set: A set containing unique Ethereum addresses of the tokens found in the pairs.
    """

    tokens = set()
    for pair in pairs_info:
        tokens.add(pairs_info[pair]["token0"])
        tokens.add(pairs_info[pair]["token1"])
    return tokens


def get_recent_contracts(tx_receipts: list) -> set:
    """
    Extract unique contract addresses from a list of transaction receipts.

    Parameters:
    - tx_receipts (list): A list containing transaction receipts. Each receipt
      has logs, and each log entry contains an "address" field.

    Returns:
    - set: A set containing unique Ethereum contract addresses extracted from
      the logs in the transaction receipts.
    """

    recent_contracts = set()

    for receipt in tx_receipts:
        for receipt_log in receipt.logs:
            recent_contracts.add(receipt_log["address"])

    log.info(
        f"Successfully extracted {len(recent_contracts)} unique contract addresses from transaction receipts."
    )

    return recent_contracts


def print_colored(text: str, color: str = DEFAULT_PRINT_COLOR):
    """
    Print a given text with a specified color using the rich library.

    Parameters:
    - text (str): The text to be printed.
    - color (str, optional): The color in which the text should be printed. Defaults to DEFAULT_PRINT_COLOR.

    Example:
    >>> print_colored("Hello, World!", "red")
    [red]Hello, World![/red]
    """

    print(f"[{color}]{text}[/{color}]")
