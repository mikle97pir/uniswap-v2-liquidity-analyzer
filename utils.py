# --- Imports ---

# Standard library imports for JSON handling and file path manipulation
import json
from pathlib import Path

# Python's built-in serialization and logging libraries
import pickle
import logging

# Rich library for enhanced command-line printing, progress tracking, and logging
from rich.progress import track
from rich.logging import RichHandler

from constants import DATA_PATH, DEPENDENCY_CONTRACTS_PATH

# --- Logging Configuration ---

# Configuring rich logger for enhanced visual feedback in the command-line interface
logging.basicConfig(
    level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler()]
)
log = logging.getLogger("rich")


def using_cache(data_filename: str):
    path = (Path(DATA_PATH) / data_filename).with_suffix(".pkl")

    def using_cache_with_path(get_data):
        def get_data_with_cache(*args, refresh=False):
            if path.is_file() and not refresh:
                try:
                    with path.open("rb") as f:
                        data = pickle.load(f)
                    log.info(f"Loaded data from cache: {path}")
                except Exception as e:
                    log.error(f"Error loading data from cache: {e}")
                    data = get_data(*args)  # Fallback to get fresh data
            else:
                data = get_data(*args)
                try:
                    with path.open("wb") as f:
                        pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)
                    log.info(f"Saved data to cache: {path}")
                except Exception as e:
                    log.error(f"Error saving data to cache: {e}")

            return data

        return get_data_with_cache

    return using_cache_with_path


def get_abi_from_json(contract_name: str) -> dict:
    abi_path = (Path(DEPENDENCY_CONTRACTS_PATH) / contract_name).with_suffix(".json")

    try:
        with abi_path.open("r") as f:
            abi = json.load(f)
            log.info(f"Successfully loaded ABI for contract: {contract_name}")
            return abi
    except FileNotFoundError:
        log.error(
            f"Could not find ABI file for contract: {contract_name} at path: {abi_path}"
        )
        raise
    except json.JSONDecodeError:
        log.error(f"Error decoding JSON for contract: {contract_name}")
        raise


def get_pair_info(w3, ABIs, pair):
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
        log.error(
            f"Error retrieving pair info for pair address: {pair}. Error: {str(e)}"
        )
        raise


def get_token_info(w3, ABIs, token):
    token_contract = w3.eth.contract(address=token, abi=ABIs["ERC20"])

    # Handle symbol retrieval
    try:
        symbol = token_contract.functions.symbol().call()
    except Exception as e:
        log.warning(
            f"Error retrieving symbol for token address: {token}. Error: {str(e)}. Defaulting to '__BAD_SYMBOL__'"
        )
        symbol = "__BAD_SYMBOL__"

    # Handle decimals retrieval
    try:
        decimals = token_contract.functions.decimals().call()
    except Exception as e:
        log.warning(
            f"Error retrieving decimals for token address: {token}. Error: {str(e)}. Defaulting to -1"
        )
        decimals = -1

    token_info = {
        "symbol": symbol,
        "decimals": decimals,
    }

    return token_info


def get_pairs_info(w3, ABIs, pairs):
    pairs_info = {
        pair: get_pair_info(w3, ABIs, pair)
        for pair in track(pairs, description="Fetching information about pairs")
    }
    return pairs_info


def get_tokens_info(w3, ABIs, tokens):
    tokens_info = {
        token: get_token_info(w3, ABIs, token)
        for token in track(tokens, description="Fetching information about tokens")
    }
    return tokens_info


def get_tokens_from_pairs(pairs_info):
    tokens = set()
    for pair in pairs_info:
        tokens.add(pairs_info[pair]["token0"])
        tokens.add(pairs_info[pair]["token1"])
    return tokens


def get_recent_contracts(tx_receipts):
    recent_contracts = set()

    for receipt in tx_receipts:
        for log in receipt.logs:
            recent_contracts.add(log["address"])

    log.info(
        f"Successfully extracted {len(recent_contracts)} unique contract addresses from transaction receipts."
    )

    return recent_contracts
