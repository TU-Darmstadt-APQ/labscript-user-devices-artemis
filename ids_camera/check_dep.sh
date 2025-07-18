#!/bin/bash
# This script checks for and installs dependencies for the IDS Software Suite.

# Color codes for output, ANSI escape seqs.
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Required dependencies
REQUIRED_PACKAGES=(
	libc6
	libstdc++6
	libqt5widgets5
	libqt5gui5
	libqt5network5
	libqt5concurrent5
	libqt5xml5
	libqt5opengl5
	libcap2
	libusb-1.0-0
	libomp5
	libatomic1
	debconf
	build-essential
)

# Optional (suggested) dependencies
OPTIONAL_PACKAGES=(
	cmake
)

echo -e "${YELLOW}Checking dependencies for IDS Software Suite...${NC}\n"

MISSING_PACKAGES=()

for pkg in "${REQUIRED_PACKAGES[@]}"; do
	if dpkg -l | grep -q "$pkg" &> /dev/null; # if dpkg -s "$pkg"
	  then
	  	echo -e "$pkg: ${GREEN}installed${NC}"
	else
		echo -e "$pkg: ${RED}missing${NC}"
		MISSING_PACKAGES+=("$pkg")
	fi
done

# Install missing dependencies if needed
if [ ${#MISSING_PACKAGES[@]} -eq 0 ]
  then
	  echo -e "\n${GREEN}All required dependencies are installed.${NC}"
else
	echo -e "\n${YELLOW}Missing dependencies detected. Do you want to install them? [y/n]${NC}"
	read -r answer
	if [[ "$answer" == "y" ]] # compare strings
	  then
      sudo apt-get update
      sudo apt-get install -y "${MISSING_PACKAGES[@]}"
	else
		echo -e "${RED}No? Ok, install it manually.${NC}"
	fi
fi
