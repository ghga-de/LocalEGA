#!/usr/bin/env bash

[ ${BASH_VERSINFO[0]} -lt 4 ] && echo 'Bash 4 (or higher) is required' 1>&2 && exit 1

HERE=$(dirname ${BASH_SOURCE[0]})
MAIN_REPO=${HERE}/..

# Some variables for these tests
DOCKER_PATH=${MAIN_REPO}/deploy
EGA_PUB_KEY=${DOCKER_PATH}/private/pgp/ega.pub

# Find inbox port mapping. Usually 2222:9000
run docker port inbox 9000
INSTANCE_PORT=${output##*:}

# Default log file, in case the bats file does not overwrite its location.
DEBUG_LOG=${HERE}/output.debug

# Convenience function to capture _all_ outputs
function legarun {
    echo -e "+++ $@" >> $DEBUG_LOG
    run "$@"
    echo -e "$output" >> $DEBUG_LOG
    echo -e "--- Status: $status" >> $DEBUG_LOG
}

# For OSX and Linux
function get_shasum {
    if command -v shasum &>/dev/null; then
        shasum -a 256 $1 | cut -d' ' -f1
    else
        sha256sum $1 | cut -d' ' -f1
    fi
}

# Check status $1 for a command, $2 times. Wait $3 seconds between retries.
function retry_until {
	local expected=$1
	local attempts=$2
	local delay=$3
	shift
	shift
	shift
	local i

	for ((i=0; i < attempts; i++)); do
	    echo -e "*** Attempt: ${i}/${attempts}" >> $DEBUG_LOG
	    legarun "$@"
	    if [[ "$status" -eq "$expected" ]] ; then
		return 0
	    fi
	    sleep $delay
	done

	echo -e "Command \"$@\" failed $attempts times. Output: $output" >> $DEBUG_LOG
	false
}
