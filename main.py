# --- Imports ---

# Standard library imports for JSON handling and file path manipulation
from pathlib import Path

# Web3 library for Ethereum blockchain interaction
from web3 import Web3

# Rich library for enhanced command-line printing, progress tracking, and logging
from rich.progress import track
from rich import print
from rich.table import Table

# Python's built-in serialization and logging libraries
import logging

# Mathematical operations and constants
import math

# Igraph library for graph data structures and algorithms
import igraph as ig

# Typer library for building CLI applications
import typer
from typing_extensions import Annotated


import constants
from utils import (
    log,
    using_cache,
    get_abi_from_json,
    get_pairs_info,
    get_tokens_info,
    get_tokens_from_pairs,
    get_recent_contracts,
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
    refresh_pairs_info: bool = False,
    refresh_tokens_info: bool = False,
    rpc_provider: str = constants.DEFAULT_RPC_PROVIDER,
    recent_blocks_number: int = 10000,
    n: Annotated[int, typer.Option("--number-of-pairs", "-n")] = 25,
):
    w3 = Web3(Web3.HTTPProvider(rpc_provider))

    print("[cornsilk1]Loading contract ABIs...[/cornsilk1]")
    ABIs = {
        contract_name: get_abi_from_json(contract_name)
        for contract_name in constants.DEPENDENCY_CONTRACT_NAMES
    }

    print("\n[cornsilk1]Retrieving pairs...[/cornsilk1]")
    pairs = get_pairs(w3, ABIs, refresh=refresh_pairs)

    print("\n[cornsilk1]Filtering active pairs...[/cornsilk1]")
    active_pairs = filter_inactive_pairs(
        w3,
        pairs,
        recent_blocks_number,
        refresh=refresh_blocks,
    )

    print("\n[cornsilk1]Gathering info about active pairs...[/cornsilk1]")
    active_pairs_info = get_active_pairs_info(
        w3, ABIs, active_pairs, refresh=refresh_pairs_info
    )

    print("\n[cornsilk1]Extracting active tokens from pairs...[/cornsilk1]")
    active_tokens = get_tokens_from_pairs(active_pairs_info)

    print("\n[cornsilk1]Gathering info about active tokens...[/cornsilk1]")
    active_tokens_info = get_active_tokens_info(
        w3, ABIs, active_tokens, refresh=refresh_tokens_info
    )

    vertex_to_token = list(active_tokens)
    token_to_vertex = {vertex_to_token[i]: i for i in range(len(vertex_to_token))}

    print("\n[cornsilk1]Creating token graph...[/cornsilk1]")
    token_graph = create_token_graph(
        vertex_to_token, token_to_vertex, active_pairs, active_pairs_info
    )

    print("\n[cornsilk1]Finding main component in the graph...[/cornsilk1]")
    components = token_graph.connected_components(mode="weak")
    main_component = components[0]

    print("\n[cornsilk1]Calculating shortest paths and token prices...[/cornsilk1]")
    paths_edges = token_graph.get_shortest_paths(
        token_to_vertex[constants.USDC], to=main_component, mode="all", output="epath"
    )

    paths_vertices = token_graph.get_shortest_paths(
        token_to_vertex[constants.USDC], to=main_component, mode="all", output="vpath"
    )

    token_prices = find_token_prices(
        paths_edges,
        paths_vertices,
        active_pairs,
        vertex_to_token,
        active_pairs_info,
        active_tokens_info,
    )

    print("\n[cornsilk1]Calculating Total Value Locked (TVL) for pairs...[/cornsilk1]")
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

    print("\n[cornsilk1]Displaying top pairs based on TVL:[/cornsilk1]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Rank", style="dim", width=5)
    table.add_column("Pair", style="bold", width=20)
    table.add_column("TVL (USDC)", style="bold", justify="right", width=20)
    table.add_column("Address", style="dim", width=42)

    for i, (pair, (symbol_pair, value)) in enumerate(TVLs_list[:n], 1):
        formatted_value = f"{value:,.2f} USDC"
        table.add_row(str(i), symbol_pair, formatted_value, pair)

    print(table)

    print(
        f"\n[cornsilk1]Successfully retrieved and displayed the top {n} pairs based on TVL![/cornsilk1]"
    )


if __name__ == "__main__":
    typer.run(main)
