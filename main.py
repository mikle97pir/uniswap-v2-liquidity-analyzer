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
def get_pairs(w3, ABIs):
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

        log.info(
            f"Successfully fetched {len(tx_receipts)} transaction receipts from the last {nblocks} blocks."
        )
        return tx_receipts

    except Exception as e:
        log.error(f"Failed to fetch recent transaction receipts. Error: {str(e)}")
        raise


@using_cache("active_pairs")
def filter_inactive_pairs(w3, uniswap_pairs, nblocks):
    tx_receipts = get_recent_tx_receipts(w3, nblocks, refresh=True)
    recent_contracts = get_recent_contracts(tx_receipts)
    active_pairs = [pair for pair in uniswap_pairs if pair in recent_contracts]

    log.info(
        f"Successfully filtered {len(active_pairs)} active pairs out of {len(uniswap_pairs)} total pairs."
    )

    return active_pairs


@using_cache("active_pairs_info")
def get_active_pairs_info(w3, ABIs, active_pairs):
    active_pairs_info = get_pairs_info(w3, ABIs, active_pairs)
    log.info(
        f"Successfully retrieved information for {len(active_pairs_info)} active pairs."
    )
    return active_pairs_info


@using_cache("active_tokens_info")
def get_active_tokens_info(w3, ABIs, active_tokens):
    active_tokens_info = get_tokens_info(w3, ABIs, active_tokens)

    for address, details in constants.TOKEN_OVERRIDES.items():
        active_tokens_info[address].update(details)

    log.info(
        f"Successfully retrieved and modified information for {len(active_tokens_info)} active tokens."
    )
    return active_tokens_info


def create_token_graph(vertex_to_token, token_to_vertex, pairs, pairs_info):
    token_graph = ig.Graph(n=len(vertex_to_token))
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
    path_edges, path_vertices, pairs, vertex_to_token, pairs_info, tokens_info
):
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

    log.info("Successfully found prices for {} tokens.".format(len(token_prices)))
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

            TVL = (price0 * reserve0 * 10 ** (-decimals0)) + (
                price1 * reserve1 * 10 ** (-decimals1)
            )

            # Check for NaN and infinity values
            if math.isnan(TVL) or TVL == math.inf:
                previous_value = TVL  # to indicate whether it was NaN or infinity
                TVL = 0
                log.warning(
                    f"Calculated TVL for pair {pair} ({symbol0}-{symbol1}) resulted in {previous_value}. Replaced with 0."
                )

            TVLs[pair] = f"{symbol0}-{symbol1}", TVL

    log.info("Successfully calculated TVL for {} pairs.".format(len(TVLs)))
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

    # If the 'refresh_all' option is set, update all refresh flags
    if refresh_all:
        refresh_pairs = True
        refresh_blocks = True
        refresh_pairs_info = True
        refresh_tokens_info = True

    # Attempt to connect to the provided RPC provider
    try:
        w3 = connect_to_rpc_provider(rpc)
    except ConnectionError as e:
        log.error(f"Error: {e}")
        sys.exit(1)

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
        token_to_vertex[constants.USDC], to=main_component, mode="all", output="epath"
    )

    paths_vertices = token_graph.get_shortest_paths(
        token_to_vertex[constants.USDC], to=main_component, mode="all", output="vpath"
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


if __name__ == "__main__":
    typer.run(main)
