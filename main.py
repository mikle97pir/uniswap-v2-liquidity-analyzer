# --- Imports ---

# Standard library imports for JSON handling and file path manipulation
import json
from pathlib import Path

# Web3 library for Ethereum blockchain interaction
from web3 import Web3

# Rich library for enhanced command-line printing, progress tracking, and logging
from rich.progress import track
from rich.logging import RichHandler
from rich import print
from rich.table import Table

# Python's built-in serialization and logging libraries
import pickle
import logging

# Mathematical operations and constants
import math

# Igraph library for graph data structures and algorithms
import igraph as ig

# Typer library for building CLI applications
import typer
from typing_extensions import Annotated

# --- Logging Configuration ---

# Configuring rich logger for enhanced visual feedback in the command-line interface
logging.basicConfig(
    level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler()]
)
log = logging.getLogger("rich")

# --- Constants ---

# Names of Ethereum contracts which this script is dependent upon
DEPENDENCY_CONTRACT_NAMES = ["ERC20", "UniswapV2Factory", "UniswapV2Pair"]

# Path where the contract ABIs (Application Binary Interfaces) are stored
DEPENDENCY_CONTRACTS_PATH = "abi"

# Path where persistent data like caches might be stored
DATA_PATH = "data"

# Address of the Uniswap V2 Factory contract on the Ethereum network
UNISWAP_FACTORY = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"

# Address of the USDC (USD Coin) token on the Ethereum network
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


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
        log.error(f"Could not find ABI file for contract: {contract_name} at path: {abi_path}")
        raise
    except json.JSONDecodeError:
        log.error(f"Error decoding JSON for contract: {contract_name}")
        raise


@using_cache("pairs")
def get_pairs(w3, ABIs):
    try:
        uniswap_factory_contract = w3.eth.contract(
            address=UNISWAP_FACTORY, abi=ABIs["UniswapV2Factory"]
        )

        all_pairs_length = uniswap_factory_contract.functions.allPairsLength().call()

        pairs = [
            uniswap_factory_contract.functions.allPairs(i).call()
            for i in track(
                range(all_pairs_length),
                description="Fetching pairs from Uniswap Factory",
            )
        ]

        log.info(f"Successfully fetched {len(pairs)} pairs from Uniswap Factory.")
        return pairs

    except Exception as e:
        log.error(f"Failed to fetch pairs from Uniswap Factory. Error: {str(e)}")
        raise


@using_cache("blocks")
def get_recent_blocks(w3, nblocks):
    try:
        blocks = [
            w3.eth.get_block(block_number)
            for block_number in track(
                range(
                    w3.eth.block_number,
                    w3.eth.block_number - nblocks,
                    -1,
                ),
                description="Fetching recent blocks",
            )
        ]

        log.info(f"Successfully fetched {len(blocks)} recent blocks.")
        return blocks

    except Exception as e:
        log.error(f"Failed to fetch recent blocks. Error: {str(e)}")
        raise


@using_cache("tx_receipts")
def get_recent_tx_receipts(w3, nblocks):
    try:
        blocks = get_recent_blocks(w3, nblocks, refresh=True)
        tx_hashes = [tx_hash for block in blocks for tx_hash in block.transactions]
        
        tx_receipts = [
            w3.eth.get_transaction_receipt(tx_hash)
            for tx_hash in track(
                tx_hashes, description="Fetching receipts of recent transactions"
            )
        ]

        log.info(f"Successfully fetched {len(tx_receipts)} transaction receipts from the last {nblocks} blocks.")
        return tx_receipts

    except Exception as e:
        log.error(f"Failed to fetch recent transaction receipts. Error: {str(e)}")
        raise


def get_recent_contracts(tx_receipts):
    recent_contracts = set()
    
    for receipt in tx_receipts:
        for log in receipt.logs:
            recent_contracts.add(log["address"])

    log.info(f"Successfully extracted {len(recent_contracts)} unique contract addresses from transaction receipts.")
        
    return recent_contracts


@using_cache("active_pairs")
def filter_inactive_pairs(w3, uniswap_pairs, nblocks):
    tx_receipts = get_recent_tx_receipts(w3, nblocks, refresh=True)
    recent_contracts = get_recent_contracts(tx_receipts, refresh=True)
    active_pairs = [pair for pair in uniswap_pairs if pair in recent_contracts]

    return active_pairs


def get_pair_info(w3, ABIs, pair):
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


def get_token_info(w3, ABIs, token):
    token_contract = w3.eth.contract(address=token, abi=ABIs["ERC20"])

    try:
        symbol = token_contract.functions.symbol().call()
    except:
        print("bad symbol", token)
        symbol = "__BAD_SYMBOL__"

    try:
        decimals = token_contract.functions.decimals().call()
    except:
        print("bad decimals", token)
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


@using_cache("active_pairs_info")
def get_active_pairs_info(w3, ABIs, active_pairs):
    active_pairs_info = get_pairs_info(w3, ABIs, active_pairs)
    return active_pairs_info


@using_cache("active_tokens_info")
def get_active_tokens_info(w3, ABIs, active_tokens):
    active_tokens_info = get_tokens_info(w3, ABIs, active_tokens)

    active_tokens_info["0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2"]["symbol"] = "MKR"
    active_tokens_info["0x0Ba45A8b5d5575935B8158a88C631E9F9C95a2e5"]["symbol"] = "TRB"
    active_tokens_info["0x0Ba45A8b5d5575935B8158a88C631E9F9C95a2e5"]["decimals"] = 18
    active_tokens_info["0x9469D013805bFfB7D3DEBe5E7839237e535ec483"]["symbol"] = "RING"
    active_tokens_info["0x9F284E1337A815fe77D2Ff4aE46544645B20c5ff"]["symbol"] = "KTON"
    active_tokens_info["0x431ad2ff6a9C365805eBaD47Ee021148d6f7DBe0"]["symbol"] = "DF"
    active_tokens_info["0x89d24A6b4CcB1B6fAA2625fE562bDD9a23260359"]["symbol"] = "SAI"

    return active_tokens_info


def get_tokens_from_pairs(pairs_info):
    tokens = set()
    for pair in pairs_info:
        tokens.add(pairs_info[pair]["token0"])
        tokens.add(pairs_info[pair]["token1"])
    return tokens


def create_token_graph(vertex_to_token, token_to_vertex, pairs, pairs_info):
    token_graph = ig.Graph(n=len(vertex_to_token))
    for pair in pairs:
        info = pairs_info[pair]
        vertice0 = token_to_vertex[info["token0"]]
        vertice1 = token_to_vertex[info["token1"]]
        token_graph.add_edges([(vertice0, vertice1)])
    return token_graph


def find_token_price_by_path(
    path_edges, path_vertices, pairs, vertex_to_token, pairs_info, tokens_info
):
    price = 1
    token = vertex_to_token[path_vertices[-1]]

    for i, edge in enumerate(path_edges):
        start_token, end_token = (
            vertex_to_token[path_vertices[i]],
            vertex_to_token[path_vertices[i + 1]],
        )
        start_decimals, end_decimals = (
            tokens_info[start_token]["decimals"],
            tokens_info[end_token]["decimals"],
        )

        pair_info = pairs_info[pairs[edge]]

        if (start_token, end_token) == (pair_info["token0"], pair_info["token1"]):
            start_reserves, end_reserves = pair_info["reserves"][:2]
        else:
            end_reserves, start_reserves = pair_info["reserves"][:2]

        if end_reserves == 0:
            if start_reserves == 0:
                return token, math.nan
            else:
                return token, math.inf

        price *= (start_reserves / end_reserves) * 10 ** (end_decimals - start_decimals)

    return token, price


def find_token_prices(
    paths_edges,
    paths_vertices,
    pairs,
    vertex_to_token,
    pairs_info,
    tokens_info,
):
    token_prices = {}
    for i in range(len(paths_edges)):
        path_edges = paths_edges[i]
        path_vertices = paths_vertices[i]
        token, price = find_token_price_by_path(
            path_edges,
            path_vertices,
            pairs,
            vertex_to_token,
            pairs_info,
            tokens_info,
        )
        token_prices[token] = price
    return token_prices


def find_pair_TVLs(
    pairs,
    token_prices,
    token_to_vertex,
    main_component,
    pairs_info,
    tokens_info,
):
    TVLs = {}
    for pair in pairs:
        pair_info = pairs_info[pair]
        token0, token1 = pair_info["token0"], pair_info["token1"]
        if token_to_vertex[token0] in main_component:
            reserve0, reserve1 = pair_info["reserves"][:2]
            price0, price1 = token_prices[token0], token_prices[token1]
            token0_info, token1_info = (
                tokens_info[token0],
                tokens_info[token1],
            )
            symbol0, symbol1 = token0_info["symbol"], token1_info["symbol"]
            decimals0, decimals1 = token0_info["decimals"], token1_info["decimals"]
            TVL = price0 * reserve0 * 10 ** (-decimals0) + price1 * reserve1 * 10 ** (
                -decimals1
            )
            if math.isnan(TVL):
                TVL = 0
            TVLs[pair] = f"{symbol0}-{symbol1}", TVL
    return TVLs


def main(
    refresh_pairs: bool = False,
    refresh_blocks: bool = False,
    refresh_pairs_info: bool = False,
    refresh_tokens_info: bool = False,
    rpc_provider: str = "https://eth.llamarpc.com/rpc/01H7QXYGC7M60A31YJQSAHVFHK",
    recent_blocks_number: int = 10000,
    n: Annotated[int, typer.Option("--number-of-pairs", "-n")] = 25,
):
    w3 = Web3(Web3.HTTPProvider(rpc_provider))

    ABIs = {
        contract_name: get_abi_from_json(contract_name)
        for contract_name in DEPENDENCY_CONTRACT_NAMES
    }

    pairs = get_pairs(w3, ABIs, refresh=refresh_pairs)
    active_pairs = filter_inactive_pairs(
        w3,
        pairs,
        recent_blocks_number,
        refresh=refresh_blocks,
    )
    active_pairs_info = get_active_pairs_info(
        w3, ABIs, active_pairs, refresh=refresh_pairs_info
    )
    active_tokens = get_tokens_from_pairs(active_pairs_info)
    active_tokens_info = get_active_tokens_info(
        w3, ABIs, active_tokens, refresh=refresh_tokens_info
    )

    vertex_to_token = list(active_tokens)
    token_to_vertex = {vertex_to_token[i]: i for i in range(len(vertex_to_token))}

    token_graph = create_token_graph(
        vertex_to_token, token_to_vertex, active_pairs, active_pairs_info
    )

    components = token_graph.connected_components(mode="weak")
    main_component = components[0]

    paths_edges = token_graph.get_shortest_paths(
        token_to_vertex[USDC], to=main_component, mode="all", output="epath"
    )

    paths_vertices = token_graph.get_shortest_paths(
        token_to_vertex[USDC], to=main_component, mode="all", output="vpath"
    )

    token_prices = find_token_prices(
        paths_edges,
        paths_vertices,
        active_pairs,
        vertex_to_token,
        active_pairs_info,
        active_tokens_info,
    )

    TVLs = find_pair_TVLs(
        active_pairs,
        token_prices,
        token_to_vertex,
        main_component,
        active_pairs_info,
        active_tokens_info,
    )

    TVLs_list = list(TVLs.items())
    TVLs_list.sort(key=lambda x: x[1][1], reverse=True)

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Rank", style="dim", width=5)
    table.add_column("Pair", style="bold", width=20)
    table.add_column("TVL (USDC)", style="bold", justify="right")

    for i, (pair, (symbol_pair, value)) in enumerate(TVLs_list[:n], 1):
        formatted_value = f"{value:,.2f} USDC"
        table.add_row(str(i), symbol_pair, formatted_value)

    print(table)


if __name__ == "__main__":
    typer.run(main)
