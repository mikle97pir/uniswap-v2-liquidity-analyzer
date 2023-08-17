# --- Imports ---

# Standard library imports

# For logging application processes and errors
import logging

# Mathematical operations and constants for internal computations
import math

# System-specific parameters and functions for script exits and more
import sys

# Path manipulation utilities for file and directory operations
from pathlib import Path

# Third-party libraries

# igraph: Library for creating and analyzing network graphs
import igraph as ig

# rich: Library for enhanced command-line printing, progress tracking, and logging
from rich import print
from rich.progress import track
from rich.table import Table

# typer: Library for building command-line interface (CLI) applications
import typer

# typing_extensions: Library to provide additional utilities related to Python's typing module
from typing_extensions import Annotated

# web3: Python library for Ethereum blockchain interaction
from web3 import Web3

# Internal or project-specific imports

# Constants for application settings and parameters
import constants

# utils: Utility functions for data retrieval, logging, caching, and more
from utils import (
    connect_to_rpc_provider,
    get_abi_from_json,
    get_pairs_info,
    get_recent_contracts,
    get_tokens_from_pairs,
    get_tokens_info,
    log,
    print_colored,
    using_cache,
)


@using_cache("pairs")
def get_pairs(w3: Web3, ABIs: dict[str, any]) -> list[str]:
    """
    Retrieve all the pair addresses from the Uniswap Factory.

    This function attempts to get all the pair addresses from the Uniswap V2 Factory contract.
    The result can be cached, and can be retrieved from cache if it exists and if the refresh flag isn't set.

    Parameters:
    - w3 (Web3): The Web3 instance used for Ethereum blockchain interactions.
    - ABIs (dict): Dictionary containing the Application Binary Interfaces (ABIs) for the necessary Ethereum contracts.

    Returns:
    - list[str]: A list of Ethereum addresses representing the pairs from the Uniswap Factory.

    Raises:
    - Exception: If there's an issue accessing the Uniswap Factory contract or fetching the pairs.
    """

    try:
        uniswap_factory_contract = w3.eth.contract(
            address=constants.UNISWAP_FACTORY, abi=ABIs["UniswapV2Factory"]
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
        log.error(f"Failed to fetch pairs from Uniswap Factory.")
        raise


@using_cache("blocks")
def get_recent_blocks(w3: Web3, nblocks: int) -> list[dict]:
    """
    Retrieve the most recent blocks from the Ethereum blockchain.

    This function fetches the specified number of recent blocks from the Ethereum blockchain.
    The result can be cached, and can be retrieved from cache if it exists and if the refresh flag isn't set.

    Parameters:
    - w3 (Web3): The Web3 instance used for Ethereum blockchain interactions.
    - nblocks (int): The number of most recent blocks to retrieve.

    Returns:
    - list[dict]: A list of block details in dictionary format.

    Raises:
    - Exception: If there's an issue accessing the Ethereum blockchain or fetching the blocks.
    """

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
        log.error(f"Failed to fetch recent blocks.")
        raise


@using_cache("tx_receipts")
def get_recent_tx_receipts(w3: Web3, nblocks: int) -> list[dict]:
    """
    Retrieve the transaction receipts of the most recent transactions from the Ethereum blockchain.

    This function fetches the transaction receipts of the transactions that are part of the most recent blocks in
    the Ethereum blockchain. The result can be cached, and can be retrieved from cache if it exists
    and if the refresh flag isn't set.

    Parameters:
    - w3 (Web3): The Web3 instance used for Ethereum blockchain interactions.
    - nblocks (int): The number of most recent blocks to consider.

    Returns:
    - list[dict]: A list of transaction receipts in dictionary format.

    Raises:
    - Exception: If there's an issue accessing the Ethereum blockchain or fetching the transaction receipts.
    """

    try:
        blocks = get_recent_blocks(w3, nblocks, refresh=True)
        tx_hashes = [tx_hash for block in blocks for tx_hash in block.transactions]

        tx_receipts = [
            w3.eth.get_transaction_receipt(tx_hash)
            for tx_hash in track(
                tx_hashes, description="Fetching receipts of recent transactions"
            )
        ]

        log.info(
            f"Successfully fetched {len(tx_receipts)} transaction receipts from the last {nblocks} blocks."
        )
        return tx_receipts

    except Exception as e:
        log.error(f"Failed to fetch recent transaction receipts.")
        raise


@using_cache("active_pairs")
def filter_inactive_pairs(
    w3: Web3, uniswap_pairs: list[str], nblocks: int
) -> list[str]:
    """
    Filter out inactive pairs from the provided Uniswap pairs based on recent transaction activity.

    This function checks which of the provided Uniswap pairs have been involved in transactions in the
    most recent blocks and returns those pairs. The result can be cached and can be retrieved from cache if it exists
    and if the refresh flag isn't set.

    Parameters:
    - w3 (Web3): The Web3 instance used for Ethereum blockchain interactions.
    - uniswap_pairs (list[str]): The list of Uniswap pairs to be filtered.
    - nblocks (int): The number of most recent blocks to consider.

    Returns:
    - list[str]: A list of active Uniswap pairs based on recent transaction activity.
    """

    tx_receipts = get_recent_tx_receipts(w3, nblocks, refresh=True)
    recent_contracts = get_recent_contracts(tx_receipts)
    active_pairs = [pair for pair in uniswap_pairs if pair in recent_contracts]

    log.info(
        f"Successfully filtered {len(active_pairs)} active pairs out of {len(uniswap_pairs)} total pairs."
    )

    return active_pairs


@using_cache("active_pairs_info")
def get_active_pairs_info(w3: Web3, ABIs: dict, active_pairs: list[str]) -> dict:
    """
    Retrieve detailed information for the given active pairs.

    This function uses the `get_pairs_info` function to fetch details about each active pair.
    The result can be cached and can be retrieved from cache if it exists and if the refresh flag isn't set.

    Parameters:
    - w3 (Web3): The Web3 instance used for Ethereum blockchain interactions.
    - ABIs (dict): Dictionary containing ABIs needed for Ethereum contract interactions.
    - active_pairs (list[str]): List of active Uniswap pairs for which information is to be retrieved.

    Returns:
    - dict: A dictionary containing information about each active pair.
    """

    active_pairs_info = get_pairs_info(w3, ABIs, active_pairs)
    log.info(
        f"Successfully retrieved information for {len(active_pairs_info)} active pairs."
    )
    return active_pairs_info


@using_cache("active_tokens_info")
def get_active_tokens_info(w3: Web3, ABIs: dict, active_tokens: list[str]) -> dict:
    """
    Retrieve detailed information for the given active tokens and update based on constants.

    This function uses the `get_tokens_info` function to fetch details about each active token.
    The result can be cached and can be retrieved from cache if it exists and if the refresh flag isn't set.
    It also updates the token information with any overrides specified in the constants.

    Parameters:
    - w3 (Web3): The Web3 instance used for Ethereum blockchain interactions.
    - ABIs (dict): Dictionary containing ABIs needed for Ethereum contract interactions.
    - active_tokens (list[str]): List of active tokens for which information is to be retrieved.

    Returns:
    - dict: A dictionary containing information about each active token.
    """

    active_tokens_info = get_tokens_info(w3, ABIs, active_tokens)

    # Update token info with overrides from constants, if they exist
    for address, details in constants.TOKEN_OVERRIDES.items():
        active_tokens_info[address].update(details)

    log.info(
        f"Successfully retrieved and modified information for {len(active_tokens_info)} active tokens."
    )
    return active_tokens_info


def create_token_graph(
    vertex_to_token: list[str],
    token_to_vertex: dict[str, int],
    pairs: list[str],
    pairs_info: dict[str, dict],
) -> ig.Graph:
    """
    Creates a graph representation of token pairs where each vertex represents a token and
    each edge represents a token pair.

    Parameters:
    - vertex_to_token (list[str]): A list where indices represent vertex IDs and values are their corresponding token addresses.
    - token_to_vertex (dict[str, int]): A mapping from token addresses to their corresponding vertex IDs.
    - pairs (list[str]): A list of token pairs.
    - pairs_info (dict[str, dict]): Detailed information about each pair.

    Returns:
    - ig.Graph: A graph where vertices are tokens and edges represent pairs.
    """

    # Initializing the graph with the number of tokens
    token_graph = ig.Graph(n=len(vertex_to_token))

    # Loop through pairs to populate the graph with edges based on the pairs info
    for pair in pairs:
        info = pairs_info[pair]
        vertice0 = token_to_vertex[info["token0"]]
        vertice1 = token_to_vertex[info["token1"]]
        token_graph.add_edges([(vertice0, vertice1)])

    log.info(
        "Token graph successfully created with {0} vertices and {1} edges.".format(
            token_graph.vcount(), token_graph.ecount()
        )
    )
    return token_graph


def find_token_price_by_path(
    path_edges: list[int],
    path_vertices: list[int],
    pairs: list[str],
    vertex_to_token: list[str],
    pairs_info: dict[str, dict],
    tokens_info: dict[str, dict],
) -> tuple[str, float]:
    """
    Calculates the token price along a given path in the token graph.

    Parameters:
    - path_edges (list[int]): List of edge indices along the path.
    - path_vertices (list[int]): List of vertex indices along the path.
    - pairs (list[str]): List of token pair addresses.
    - vertex_to_token (list[str]): List where indices represent vertex IDs and values are token addresses.
    - pairs_info (dict[str, dict]): Detailed information about each pair.
    - tokens_info (dict[str, dict]): Detailed information about each token.

    Returns:
    - tuple[str, float]: A tuple containing the token symbol and its calculated price.

    Warnings:
    - If both reserves are zero for a pair, the price for the token will be set to zero.
    - If the end reserve is zero for a pair, the price for the token will be set to zero.
    """

    price = 1
    token = vertex_to_token[path_vertices[-1]]
    target_symbol = tokens_info[token]["symbol"]

    for i, edge in enumerate(path_edges):
        pair_address = pairs[edge]
        start_token, end_token = (
            vertex_to_token[path_vertices[i]],
            vertex_to_token[path_vertices[i + 1]],
        )
        start_symbol, end_symbol = (
            tokens_info[start_token]["symbol"],
            tokens_info[end_token]["symbol"],
        )
        start_decimals, end_decimals = (
            tokens_info[start_token]["decimals"],
            tokens_info[end_token]["decimals"],
        )

        pair_info = pairs_info[pair_address]

        # Determine which token's reserves correspond to the start and end of the pair
        if (start_token, end_token) == (pair_info["token0"], pair_info["token1"]):
            start_reserves, end_reserves = pair_info["reserves"][:2]
        else:
            end_reserves, start_reserves = pair_info["reserves"][:2]

        if end_reserves == 0:
            if start_reserves == 0:
                log.warning(
                    "Both reserves are zero for pair: {} ({}-{} / {}-{}). Setting price for token '{}' to zero.".format(
                        pair_address,
                        start_token,
                        end_token,
                        start_symbol,
                        end_symbol,
                        target_symbol,
                    )
                )
                return token, 0
            else:
                log.warning(
                    "End reserve ({} / {}) is zero for pair: {} ({}-{} / {}-{}). Setting price for token '{}' to zero.".format(
                        end_token,
                        end_symbol,
                        pair_address,
                        start_token,
                        end_token,
                        start_symbol,
                        end_symbol,
                        target_symbol,
                    )
                )
                return token, 0

        # Calculate the price based on reserves and decimals
        price *= (start_reserves / end_reserves) * 10 ** (end_decimals - start_decimals)

    return token, price


def find_token_prices(
    paths_edges: list[list[int]],
    paths_vertices: list[list[int]],
    pairs: list[str],
    vertex_to_token: list[str],
    pairs_info: dict[str, dict],
    tokens_info: dict[str, dict],
) -> dict[str, float]:
    """
    Calculates token prices along multiple paths in the token graph.

    Args:
    - paths_edges (list[list[int]]): List of edge paths for each token.
    - paths_vertices (list[list[int]]): List of vertex paths for each token.
    - pairs (list[str]): List of pair addresses.
    - vertex_to_token (list[str]): Mapping of vertex indices to token symbols.
    - pairs_info (dict[str, dict]): Information about pairs.
    - tokens_info (dict[str, dict]): Information about tokens.

    Returns:
    - dict[str, float]: A dictionary mapping token symbols to their calculated prices.
    """
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

    log.info("Successfully found prices for {} tokens.".format(len(token_prices)))
    return token_prices


def find_pair_TVLs(
    pairs: list[str],
    token_prices: dict[str, float],
    token_to_vertex: dict[str, int],
    main_component: list[int],
    pairs_info: dict[str, dict],
    tokens_info: dict[str, dict],
) -> dict[str, tuple[str, float]]:
    """
    Calculate Total Value Locked (TVL) for pairs.

    Args:
        pairs (list[str]): List of pair addresses.
        token_prices (dict[str, float]): Token prices mapping.
        token_to_vertex (dict[str, int]): Token address to graph vertex mapping.
        main_component (list[int]): List of vertices in the main component of the token graph.
        pairs_info (dict[str, dict]): Information about pairs.
        tokens_info (dict[str, dict]): Information about tokens.

    Returns:
        dict[str, tuple[str, float]]: Mapping of pair addresses to a tuple containing pair symbol and TVL.
    """
    TVLs = {}
    for pair in pairs:
        pair_info = pairs_info[pair]
        token0, token1 = pair_info["token0"], pair_info["token1"]

        # Check if both tokens in the pair are part of the main component
        if token_to_vertex[token0] in main_component:
            reserve0, reserve1 = pair_info["reserves"][:2]
            price0, price1 = token_prices[token0], token_prices[token1]
            token0_info, token1_info = (
                tokens_info[token0],
                tokens_info[token1],
            )
            symbol0, symbol1 = token0_info["symbol"], token1_info["symbol"]
            decimals0, decimals1 = token0_info["decimals"], token1_info["decimals"]

            # Calculate TVL using token prices and reserves
            TVL = (price0 * reserve0 * 10 ** (-decimals0)) + (
                price1 * reserve1 * 10 ** (-decimals1)
            )

            # Check for NaN and infinity values
            if math.isnan(TVL) or TVL == math.inf:
                previous_value = TVL  # to indicate whether it was NaN or infinity
                TVL = 0
                logging.warning(
                    f"Calculated TVL for pair {pair} ({symbol0}-{symbol1}) resulted in {previous_value}. Replaced with 0."
                )

            TVLs[pair] = f"{symbol0}-{symbol1}", TVL

    logging.info("Successfully calculated TVL for {} pairs.".format(len(TVLs)))
    return TVLs


def main(
    refresh_pairs: bool = False,
    refresh_blocks: bool = False,
    refresh_pairs_info: bool = typer.Option(False, "--refresh-pairs-info", "-r"),
    refresh_tokens_info: bool = False,
    refresh_all: bool = typer.Option(False, "--refresh-all", "-R"),
    rpc: str = constants.DEFAULT_RPC_PROVIDER,
    recent_blocks_number: int = 10000,
    n: int = typer.Option(25, "--number-of-pairs", "-n"),
):
    try:
        # If the 'refresh_all' option is set, update all refresh flags
        if refresh_all:
            refresh_pairs = True
            refresh_blocks = True
            refresh_pairs_info = True
            refresh_tokens_info = True

        # Attempt to connect to the provided RPC provider
        w3 = connect_to_rpc_provider(rpc)

        # Load Ethereum contract ABIs for later use
        print_colored("Loading contract ABIs...")
        ABIs = {
            contract_name: get_abi_from_json(contract_name)
            for contract_name in constants.DEPENDENCY_CONTRACT_NAMES
        }

        # Retrieve pairs, either from cache or directly
        print_colored("\nRetrieving pairs...")
        pairs = get_pairs(w3, ABIs, refresh=refresh_pairs)

        # Filter to only include active pairs based on recent activity
        print_colored("\nFiltering active pairs...")
        active_pairs = filter_inactive_pairs(
            w3,
            pairs,
            recent_blocks_number,
            refresh=refresh_blocks,
        )

        # Gather detailed information about the active pairs
        print_colored("\nGathering info about active pairs...")
        active_pairs_info = get_active_pairs_info(
            w3, ABIs, active_pairs, refresh=refresh_pairs_info
        )

        # Extract tokens involved in the active pairs
        print_colored("\nExtracting active tokens from pairs...")
        active_tokens = get_tokens_from_pairs(active_pairs_info)

        # Gather detailed information about the active tokens
        print_colored("\nGathering info about active tokens...")
        active_tokens_info = get_active_tokens_info(
            w3, ABIs, active_tokens, refresh=refresh_tokens_info
        )

        # Map tokens to vertices (and vice versa) for graph representation
        vertex_to_token = list(active_tokens)
        token_to_vertex = {vertex_to_token[i]: i for i in range(len(vertex_to_token))}

        # Construct a graph representing token relationships and liquidity
        print_colored("\nCreating token graph...")
        token_graph = create_token_graph(
            vertex_to_token, token_to_vertex, active_pairs, active_pairs_info
        )

        # Identify connected components in the token graph
        print_colored("\nFinding main component in the graph...")
        components = token_graph.connected_components(mode="weak")
        main_component = components[0]

        # Find shortest paths in the token graph to the main component from USDC
        print_colored("\nCalculating shortest paths...")
        paths_edges = token_graph.get_shortest_paths(
            token_to_vertex[constants.USDC],
            to=main_component,
            mode="all",
            output="epath",
        )

        paths_vertices = token_graph.get_shortest_paths(
            token_to_vertex[constants.USDC],
            to=main_component,
            mode="all",
            output="vpath",
        )

        # Calculate token prices based on the found paths
        print_colored("\nCalculating token prices...")
        token_prices = find_token_prices(
            paths_edges,
            paths_vertices,
            active_pairs,
            vertex_to_token,
            active_pairs_info,
            active_tokens_info,
        )

        # Calculate Total Value Locked (TVL) for each active pair
        print_colored("\nCalculating Total Value Locked (TVL) for pairs...")
        TVLs = find_pair_TVLs(
            active_pairs,
            token_prices,
            token_to_vertex,
            main_component,
            active_pairs_info,
            active_tokens_info,
        )

        # Sort and display the top pairs based on their TVL
        TVLs_list = list(TVLs.items())
        TVLs_list.sort(key=lambda x: x[1][1], reverse=True)
        print_colored("\nDisplaying top pairs based on TVL:")

        # Create and populate a table for visualization
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Rank", style="dim", width=5)
        table.add_column("Pair", style="bold", width=20)
        table.add_column("TVL (USDC)", style="bold", justify="right", width=20)
        table.add_column("Address", style="dim", width=42)

        for i, (pair, (symbol_pair, value)) in enumerate(TVLs_list[:n], 1):
            formatted_value = f"{value:,.2f} USDC"
            table.add_row(str(i), symbol_pair, formatted_value, pair)

        print(table)

        # Final message to indicate successful execution
        print_colored(
            f"\nSuccessfully retrieved and displayed the top {n} pairs based on TVL!"
        )
    except Exception as e:
        # Log the error message
        log.error(f"An error occurred: {str(e)[:1024]}")

        # Print the error message for the user
        print_colored(
            "An unexpected error occurred. Please check the logs for more details.",
            "red",
        )

        # Exit the program with error code 1
        sys.exit(1)


if __name__ == "__main__":
    typer.run(main)
