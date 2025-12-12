#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

PACKAGES=(
  libqt5core5a
  libqt5gui5
  libqt5widgets5
  libqt5quick5
  qml-module-qtquick-window2
  qml-module-qtquick2
  qtbase5-dev
  qtdeclarative5-dev
  libqt5multimedia5
  libqt5x11extras5
)

OTHER_PACKAGES=(
  libusb-1.0-0
  libatomic1
)


MISSING_PACKAGES=()

echo
echo "Checking core dependencies..."
for pkg in "${PACKAGES[@]}"; do
  if dpkg -s "$pkg" &>/dev/null; then
    echo -e "$pkg: ${GREEN}installed${NC}"
  else
    echo -e "$pkg: ${RED}missing${NC}"
    MISSING_PACKAGES+=("$pkg")
  fi
done

echo
echo "Checking other packages..."
for pkg in "${OTHER_PACKAGES[@]}"; do
  if dpkg -s "$pkg" &>/dev/null; then
    echo -e "$pkg: ${GREEN}installed${NC}"
  else
    echo -e "$pkg: ${RED}missing${NC}"
    MISSING_PACKAGES+=("$pkg")
  fi
done


# Install missing dependencies if needed
echo
if [ ${#MISSING_PACKAGES[@]} -eq 0 ]; then
  echo -e "${GREEN}All required dependencies are installed.${NC}"
else
  echo -e "${YELLOW}Some dependencies are missing.${NC}"

  sudo apt-get update

  for pkg in "${MISSING_PACKAGES[@]}"; do
    echo
    echo -en "${YELLOW}Install $pkg? [y/n]: ${NC}"
    read -r answer
    if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
      echo -e "${GREEN}Installing $pkg...${NC}"
      sudo apt-get install -y "$pkg"
    else
      echo -e "${RED}Skipped $pkg${NC}"
    fi
  done
fi
