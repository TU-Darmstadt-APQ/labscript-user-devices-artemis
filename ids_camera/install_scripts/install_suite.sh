#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

PACKAGES=(
  ueye-api_4.96.1.2054_amd64.deb
  ueye-common_4.96.1.2054_amd64.deb
  ueye-demos_4.96.1.2054_amd64.deb
  ueye-dev_4.96.1.2054_amd64.deb
  ueye-driver-eth_4.96.1.2054_amd64.deb
  ueye-driver-usb_4.96.1.2054_amd64.deb
  ueye-interfaces-halcon_4.96.1.2054_amd64.deb
  ueye-tools-cli_4.96.1.2054_amd64.deb
  ueye-tools-qt5_4.96.1.2054_amd64.deb
  ueye-drivers_4.96.1.2054_amd64.deb
  ueye-manual-de_4.96.1.2054_amd64.deb
  ueye-manual-en_4.96.1.2054_amd64.deb
  ueye-manuals_4.96.1.2054_amd64.deb
  ueye_4.96.1.2054_amd64.deb
)

MISSING_PACKAGES=()

echo "Checking installed packages..."

for pkg in "${PACKAGES[@]}"; do
  # ueye-api_4.96.1.2054_amd64.deb -> ueye-api
  pkgname=$(echo "$pkg" | cut -d'_' -f1)

  if dpkg -s "$pkgname" &> /dev/null; then
    echo -e "$pkgname: ${GREEN}installed${NC}"
  else
    echo -e "$pkgname: ${RED}missing${NC}"
    MISSING_PACKAGES+=("$pkg")
  fi
done

if [ ${#MISSING_PACKAGES[@]} -eq 0 ]; then
  echo -e "${GREEN}All packages are already installed.${NC}"
  exit 0
fi

echo -e "Do you want to install missing packages? [y/n]"
read -r answer

TARGET_DIR=~/Downloads/ids-software-suite-linux-64-4.96.1-debian
cd "$TARGET_DIR" || exit 1

if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
  for pkg in "${MISSING_PACKAGES[@]}"; do
    echo -e "Do you want to install ${GREEN}$pkg${NC}? [y/N]"
    read -r install_answer
    if [[ "$install_answer" =~ ^[Yy]$ ]]; then
      echo "Installing: $pkg"
      sudo dpkg -i "$pkg" || {
        echo -e "${RED}dpkg failed. Attempting to fix broken dependencies...${NC}"
        sudo apt --fix-broken install
      }
    else
      echo -e "${RED}Skipped${NC}: $pkg"
    fi
  done
else
  echo "Installation aborted."
fi
