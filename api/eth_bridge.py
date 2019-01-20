import logging
import os
import time

from solc import compile_source, compile_files
from web3 import Web3, HTTPProvider, EthereumTesterProvider
from web3.contract import Contract as WContract
from web3.middleware import geth_poa_middleware

DEFAULT_GAS = int(os.getenv("DEFAULT_GAS", 4712388))
GAS_PAYER = Web3.toChecksumAddress(
    os.getenv("GAS_PAYER", "0x1413862c2b7054cdbfdc181b83962cb0fc11fd92"))
GAS_PAYER_PRIV = os.getenv(
    "GAS_PAYER_PRIV",
    "28e516f1e2f99e96a48a23cea1f94ee5f073403a1c68e818263f0eb898f1c8e5")

LOG = logging.getLogger("api.eth_bridge")
WAIT_TIME = 3
EIP20ADDR = os.getenv("EIP20ADDR",
                      '0x9b0ff099c4e8df24ec077e0ccd46571f915afb25')
try:
    EIP20ADDR = Web3.toChecksumAddress(EIP20ADDR)
except Exception as e:
    LOG.error("EIP20ADDR:{}".format(EIP20ADDR))
    raise e

COUNTER = int(os.getenv("TIMEOUT_COUNTER", "10"))

CONTRACT_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'contracts')
CONTRACTS = compile_files(["{}/Escrow.sol".format(CONTRACT_FOLDER), "{}/EscrowFactory.sol".format(CONTRACT_FOLDER), "{}/HMToken.sol".format(CONTRACT_FOLDER), "{}/HMTokenInterface.sol".format(CONTRACT_FOLDER), "{}/SafeMath.sol".format(CONTRACT_FOLDER)])


def _get_w3():
    endpoint = os.getenv("HET_ETH_SERVER", 'http://localhost:8545')
    if not endpoint:
        LOG.error("Using EthereumTesterProvider as we have no HET_ETH_SERVER")
    provider = HTTPProvider(endpoint) if endpoint else EthereumTesterProvider
    w3 = Web3(provider)
    w3.middleware_stack.inject(geth_poa_middleware, layer=0)
    return w3


W3 = _get_w3()


def get_w3():
    return W3


def wait_on_transaction(tx_hash: str) -> bool:
    LOG.debug("Waiting to get transaction recipt")
    return W3.eth.waitForTransactionReceipt(tx_hash, timeout=240)


def sign_and_send_transaction(tx_hash: str, private_key: str) -> str:
    signed_txn = W3.eth.account.signTransaction(
        tx_hash, private_key=private_key)
    return W3.eth.sendRawTransaction(signed_txn.rawTransaction)


def get_contract_interface(contract_entrypoint):
    compiled_sol = CONTRACTS
    contract_interface = compiled_sol[contract_entrypoint]
    return contract_interface


def get_eip20():
    contract_interface = get_contract_interface('{}/HMTokenInterface.sol:HMTokenInterface'.format(CONTRACT_FOLDER))
    contract = W3.eth.contract(
        address=EIP20ADDR, abi=contract_interface['abi'])
    return contract


def get_escrow(escrow_address, gas=DEFAULT_GAS) -> WContract:
    contract_interface = get_contract_interface('{}/Escrow.sol:Escrow'.format(CONTRACT_FOLDER))
    escrow = get_w3().eth.contract(
        address=escrow_address, abi=contract_interface['abi'])
    return escrow


def get_factory(factory_address, gas=DEFAULT_GAS) -> WContract:
    contract_interface = get_contract_interface('{}/EscrowFactory.sol:EscrowFactory'.format(CONTRACT_FOLDER))
    escrow_factory = get_w3().eth.contract(
        address=factory_address, abi=contract_interface['abi'])
    return escrow_factory

def deploy_contract(contract_interface, gas, args=[]):
    contract = W3.eth.contract(
        abi=contract_interface['abi'], bytecode=contract_interface['bin'])
    nonce = W3.eth.getTransactionCount(GAS_PAYER)

    # Get transaction hash from deployed contract
    LOG.debug("Deploying contract with gas:{}".format(gas))

    tx_dict = contract.constructor(*args).buildTransaction({
        'from': GAS_PAYER,
        'gas': gas,
        'nonce': nonce
    })
    tx_hash = sign_and_send_transaction(tx_dict, GAS_PAYER_PRIV)
    wait_on_transaction(tx_hash)

    tx_receipt = W3.eth.getTransactionReceipt(tx_hash)
    contract_address = tx_receipt.contractAddress

    contract = W3.eth.contract(
        address=contract_address,
        abi=contract_interface['abi'],
    )

    LOG.info("New contract at:{} ".format(contract_address))
    return contract, contract_address


def deploy_factory(gas=DEFAULT_GAS) -> WContract:
    """
    Returns success
    sol: solidity code
    gas: how much gas to use for the contract
    contract = input path into sol contract
    """

    contract_interface = get_contract_interface('{}/EscrowFactory.sol:EscrowFactory'.format(CONTRACT_FOLDER))
    (contract, contract_address) = deploy_contract(
        contract_interface, gas, args=[EIP20ADDR])
    return contract
