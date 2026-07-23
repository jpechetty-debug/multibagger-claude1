import argparse
import hashlib
import os
import secrets
import sys

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db.db_core import execute_sql


def generate_api_key():
    """Generates a new secure API key with 'sov_' prefix."""
    return "sov_" + secrets.token_hex(24)

def hash_api_key(key: str) -> str:
    """Hashes the API key using SHA-256 for secure storage."""
    # usedforsecurity=False required for FIPS compliance per previous guidelines
    return hashlib.sha256(key.encode(), usedforsecurity=False).hexdigest()

def create_key(consumer_name: str, rate_limit: int):
    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key)

    query = """
    INSERT INTO api_keys (key_hash, consumer_name, is_active, rate_limit_rpm, total_usage, created_at, updated_at)
    VALUES (:key_hash, :consumer_name, 1, :rate_limit, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """
    execute_sql(query, {
        "key_hash": key_hash,
        "consumer_name": consumer_name,
        "rate_limit": rate_limit
    })

    print(f"Successfully created API key for consumer '{consumer_name}'.")
    print(f"API Key: {raw_key}")
    print("Store this key safely! It will not be shown again.")

def list_keys():
    query = "SELECT key_hash, consumer_name, is_active, rate_limit_rpm, total_usage, created_at FROM api_keys"
    results = execute_sql(query, fetch_all=True)

    if not results:
        print("No API keys found in the database.")
        return

    print(f"{'Consumer':<25} | {'Active':<6} | {'RPM Limit':<9} | {'Usage':<8} | {'Hash Prefix':<12}")
    print("-" * 70)
    for r in results:
        status = "Yes" if r["is_active"] else "No"
        hash_prefix = r["key_hash"][:8] + "..."
        print(f"{r['consumer_name']:<25} | {status:<6} | {r['rate_limit_rpm']:<9} | {r['total_usage']:<8} | {hash_prefix:<12}")

def set_status(consumer_name: str, active: bool):
    is_active = 1 if active else 0
    query = "UPDATE api_keys SET is_active = :is_active, updated_at = CURRENT_TIMESTAMP WHERE consumer_name = :consumer_name"
    rows_affected = execute_sql(query, {"is_active": is_active, "consumer_name": consumer_name})

    if rows_affected:
        status_str = "activated" if active else "revoked"
        print(f"Successfully {status_str} key(s) for consumer '{consumer_name}'.")
    else:
        print(f"No key found for consumer '{consumer_name}'.")

def main():
    parser = argparse.ArgumentParser(description="Manage Sovereign API Keys")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new API key")
    create_parser.add_argument("consumer_name", help="Name of the API consumer (e.g. 'frontend_app', 'alice')")
    create_parser.add_argument("--rate-limit", type=int, default=60, help="Rate limit in requests per minute (default: 60)")

    # List command
    subparsers.add_parser("list", help="List all API keys")

    # Revoke command
    revoke_parser = subparsers.add_parser("revoke", help="Revoke an API key by consumer name")
    revoke_parser.add_argument("consumer_name", help="Name of the API consumer to revoke")

    # Activate command
    activate_parser = subparsers.add_parser("activate", help="Re-activate an API key by consumer name")
    activate_parser.add_argument("consumer_name", help="Name of the API consumer to activate")

    args = parser.parse_args()

    if args.command == "create":
        create_key(args.consumer_name, args.rate_limit)
    elif args.command == "list":
        list_keys()
    elif args.command == "revoke":
        set_status(args.consumer_name, False)
    elif args.command == "activate":
        set_status(args.consumer_name, True)

if __name__ == "__main__":
    main()
