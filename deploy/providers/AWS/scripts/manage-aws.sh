#!/bin/bash
# Terraform state management (force-unlock).

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/utils.sh"

check_aws_profile

action="${1:?Action required: force-unlock}"

case "$action" in
    force-unlock)
        lock_id="${2:?Lock ID is required: force-unlock <lock-id>}"
        log_info "Force unlocking Terraform state (ID: $lock_id)..."
        if terraform force-unlock -force "$lock_id"; then
            log_success "Lock released"
        else
            log_error "Failed to release lock"
            exit 1
        fi
        ;;

    *)
        log_error "Unknown action: $action"
        echo "Usage: $(basename "$0") force-unlock <lock-id>"
        exit 1
        ;;
esac
