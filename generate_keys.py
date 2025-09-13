#!/usr/bin/env python
"""
Generate RSA keys for JWT signing.

This script generates a pair of RSA keys (private and public) for JWT token signing.
The keys are saved to the specified directory.
"""

import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

def generate_rsa_keys(key_dir="./keys", key_size=2048):
    """Generate RSA keys for JWT signing"""
    # Create directory if it doesn't exist
    os.makedirs(key_dir, exist_ok=True)
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend()
    )
    
    # Get public key
    public_key = private_key.public_key()
    
    # Save private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    with open(os.path.join(key_dir, "private_key.pem"), "wb") as f:
        f.write(private_pem)
    
    # Save public key
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    with open(os.path.join(key_dir, "public_key.pem"), "wb") as f:
        f.write(public_pem)
    
    print(f"RSA keys generated successfully in {key_dir}")
    print(f"Private key: {os.path.join(key_dir, 'private_key.pem')}")
    print(f"Public key: {os.path.join(key_dir, 'public_key.pem')}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate RSA keys for JWT signing")
    parser.add_argument("--key-dir", default="./keys", help="Directory to save keys")
    parser.add_argument("--key-size", type=int, default=2048, help="Key size in bits")
    
    args = parser.parse_args()
    
    generate_rsa_keys(args.key_dir, args.key_size) 
