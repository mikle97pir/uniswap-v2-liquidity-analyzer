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

TOKEN_OVERRIDES = {
    "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2": {"symbol": "MKR"},
    "0x0Ba45A8b5d5575935B8158a88C631E9F9C95a2e5": {"symbol": "TRB", "decimals": 18},
    "0x9469D013805bFfB7D3DEBe5E7839237e535ec483": {"symbol": "RING"},
    "0x9F284E1337A815fe77D2Ff4aE46544645B20c5ff": {"symbol": "KTON"},
    "0x431ad2ff6a9C365805eBaD47Ee021148d6f7DBe0": {"symbol": "DF"},
    "0x89d24A6b4CcB1B6fAA2625fE562bDD9a23260359": {"symbol": "SAI"},
}

DEFAULT_RPC_PROVIDER = "https://eth.llamarpc.com"

DEFAULT_PRINT_COLOR = "green"