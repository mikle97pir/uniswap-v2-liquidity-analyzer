# --- Constants ---

# List of Ethereum contract names which are essential for the operation of the script.
# These contracts define the necessary interaction patterns and functionalities.
DEPENDENCY_CONTRACT_NAMES = ["ERC20", "UniswapV2Factory", "UniswapV2Pair"]

# Directory path indicating where the contract ABIs
# (Application Binary Interfaces) can be found.
# ABIs define how to call functions in a smart contract.
DEPENDENCY_CONTRACTS_PATH = "abi"

# Directory path for storing persistent data.
# This might include caches, intermediary results, etc.
DATA_PATH = "data"

# Ethereum address for the Uniswap V2 Factory contract.
# The factory is a central piece of the Uniswap infrastructure
# which is responsible for creating new exchange pairs.
UNISWAP_FACTORY = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"

# Ethereum address for the USDC (USD Coin) token.
# USDC is a popular stablecoin which is pegged to the US dollar.
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

# Dictionary containing overrides for certain token addresses.
# This is useful in cases where the token's contract might not
# provide all the necessary details or has known discrepancies.
TOKEN_OVERRIDES = {
    "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2": {"symbol": "MKR"},
    "0x0Ba45A8b5d5575935B8158a88C631E9F9C95a2e5": {"symbol": "TRB", "decimals": 18},
    "0x9469D013805bFfB7D3DEBe5E7839237e535ec483": {"symbol": "RING"},
    "0x9F284E1337A815fe77D2Ff4aE46544645B20c5ff": {"symbol": "KTON"},
    "0x431ad2ff6a9C365805eBaD47Ee021148d6f7DBe0": {"symbol": "DF"},
    "0x89d24A6b4CcB1B6fAA2625fE562bDD9a23260359": {"symbol": "SAI"},
}

# Default Ethereum RPC provider URL.
# This is used to connect and interact with the Ethereum blockchain.
DEFAULT_RPC_PROVIDER = "wss://eth.llamarpc.com"

# Default color for the print messages in the terminal.
# This helps to provide a consistent visual feedback.
DEFAULT_PRINT_COLOR = "green"

# Default number of recent blocks to consider when filtering for active pairs.
# If this value is altered during runtime using the --recent-blocks-number option,
# it will trigger a complete data refresh to ensure consistency.
DEFAULT_RECENT_BLOCKS_NUMBER = 10000
