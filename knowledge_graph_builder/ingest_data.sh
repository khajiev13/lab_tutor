#!/bin/bash

# Neo4j Data Ingestion Shell Script
# 
# This script provides a simple interface to run the Neo4j data ingestion
# from a shell environment, particularly useful in Docker containers.
#
# Usage:
#   ./ingest_data.sh                    # Auto-detect and ingest (Docker-friendly)
#   ./ingest_data.sh --full             # Full ingestion with detailed output
#   ./ingest_data.sh --clear            # Clear database and ingest
#   ./ingest_data.sh --help             # Show help

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show help
show_help() {
    echo "Neo4j Data Ingestion Script"
    echo ""
    echo "Usage:"
    echo "  $0                    Auto-detect and ingest (Docker-friendly)"
    echo "  $0 --full             Full ingestion with detailed output"
    echo "  $0 --clear            Clear database and ingest"
    echo "  $0 --help             Show this help message"
    echo ""
    echo "Description:"
    echo "  This script ingests extracted Neo4j-ready data into the Neo4j database."
    echo "  It automatically detects the presence of production_output directory"
    echo "  and ingests the data if the database is empty."
    echo ""
    echo "Examples:"
    echo "  # Docker container startup (automatic)"
    echo "  $0"
    echo ""
    echo "  # Manual ingestion with full output"
    echo "  $0 --full"
    echo ""
    echo "  # Force re-ingestion (clear database first)"
    echo "  $0 --clear"
}

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to the script directory
cd "$SCRIPT_DIR"

print_status "Neo4j Data Ingestion Script"
print_status "Working directory: $SCRIPT_DIR"

# Check if Python is available
if ! command -v python &> /dev/null; then
    print_error "Python is not available in PATH"
    exit 1
fi

# Parse command line arguments
case "${1:-}" in
    --help|-h)
        show_help
        exit 0
        ;;
    --full)
        print_status "Running full ingestion with detailed output..."
        python ingest_extracted_data.py
        ;;
    --clear)
        print_status "Running ingestion with database clearing..."
        python ingest_extracted_data.py --clear-db
        ;;
    "")
        print_status "Running Docker-friendly auto-ingestion..."
        python docker_ingest.py
        ;;
    *)
        print_error "Unknown option: $1"
        echo ""
        show_help
        exit 1
        ;;
esac

# Check the exit code of the Python script
if [ $? -eq 0 ]; then
    print_success "Ingestion script completed successfully"
else
    print_error "Ingestion script failed"
    exit 1
fi
