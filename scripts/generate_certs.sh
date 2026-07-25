#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${1:-certs}"
mkdir -p "${OUTPUT_DIR}"

echo "==> Generating Certificate Authority (CA)..."
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -keyout "${OUTPUT_DIR}/ca.key" \
  -out "${OUTPUT_DIR}/ca.crt" \
  -subj "/CN=MatrixFactoryCA/O=MatrixFactoryTwin" 2>/dev/null

echo "==> Generating Server Key and CSR..."
openssl req -newkey rsa:2048 -nodes \
  -keyout "${OUTPUT_DIR}/server.key" \
  -out "${OUTPUT_DIR}/server.csr" \
  -subj "/CN=localhost/O=MatrixFactoryTwin" 2>/dev/null

echo "==> Signing Server Certificate..."
cat <<EOF > "${OUTPUT_DIR}/server_ext.cnf"
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
EOF

openssl x509 -req -days 365 \
  -in "${OUTPUT_DIR}/server.csr" \
  -CA "${OUTPUT_DIR}/ca.crt" \
  -CAkey "${OUTPUT_DIR}/ca.key" \
  -CAcreateserial \
  -out "${OUTPUT_DIR}/server.crt" \
  -extfile "${OUTPUT_DIR}/server_ext.cnf" 2>/dev/null

echo "==> Generating Client Key and CSR..."
openssl req -newkey rsa:2048 -nodes \
  -keyout "${OUTPUT_DIR}/client.key" \
  -out "${OUTPUT_DIR}/client.csr" \
  -subj "/CN=MatrixFactoryClient/O=MatrixFactoryTwin" 2>/dev/null

echo "==> Signing Client Certificate..."
cat <<EOF > "${OUTPUT_DIR}/client_ext.cnf"
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth
EOF

openssl x509 -req -days 365 \
  -in "${OUTPUT_DIR}/client.csr" \
  -CA "${OUTPUT_DIR}/ca.crt" \
  -CAkey "${OUTPUT_DIR}/ca.key" \
  -CAcreateserial \
  -out "${OUTPUT_DIR}/client.crt" \
  -extfile "${OUTPUT_DIR}/client_ext.cnf" 2>/dev/null

# Clean up CSR and ext files
rm -f "${OUTPUT_DIR}/*.csr" "${OUTPUT_DIR}/*.cnf" "${OUTPUT_DIR}/*.srl"

echo "==> Certificates successfully generated in ${OUTPUT_DIR}/:"
ls -l "${OUTPUT_DIR}"
