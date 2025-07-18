#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

REQUIRED_LIBC="2.27"
REQUIRED_LIBSTDCPP="7.4"
REQUIRED_QT="5.9.5"

QT_PACKAGES=(
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

check_package_version() {
  local name=$1
  local min_version=$2
  local current_version=$(dpkg -s "$name" 2>/dev/null | grep '^Version:' | awk '{print $2}')

  if [ -z "$current_version" ]; then
    echo -e "$name: ${RED}not installed${NC}"
  elif dpkg --compare-versions "$current_version" ge "$min_version"; then
    echo -e "$name: ${GREEN}$current_version >= $min_version (OK)${NC}"
  else
    echo -e "$name: ${RED}$current_version < $min_version (Too old)${NC}"
  fi
}

echo "Checking core library versions..."

# Check libc version
glibc_version=$(ldd --version | head -n1 | grep -oP '\d+\.\d+')
if dpkg --compare-versions "$glibc_version" ge "$REQUIRED_LIBC"; then
  echo -e "libc6: ${GREEN}$glibc_version >= $REQUIRED_LIBC (OK)${NC}"
else
  echo -e "libc6: ${RED}$glibc_version < $REQUIRED_LIBC (Too old)${NC}"
fi

# Check libstdc++ version
libstdcpp_version=$(
  strings /usr/lib/x86_64-linux-gnu/libstdc++.so.6 2>/dev/null | grep '^GLIBCXX_' | sort -V | tail -n1 | sed 's/GLIBCXX_//'
)
if dpkg --compare-versions "$libstdcpp_version" ge "$REQUIRED_LIBSTDCPP"; then
  echo -e "libstdc++: ${GREEN}$libstdcpp_version >= $REQUIRED_LIBSTDCPP (OK)${NC}"
else
  echo -e "libstdc++: ${RED}$libstdcpp_version < $REQUIRED_LIBSTDCPP (Too old)${NC}"
fi

echo
echo "Checking Qt dependencies..."
for pkg in "${QT_PACKAGES[@]}"; do
  dpkg -s "$pkg" &>/dev/null && echo -e "$pkg: ${GREEN}installed${NC}" || echo -e "$pkg: ${RED}missing${NC}"
done

echo
echo "Checking other required packages..."
for pkg in "${OTHER_PACKAGES[@]}"; do
  dpkg -s "$pkg" &>/dev/null && echo -e "$pkg: ${GREEN}installed${NC}" || echo -e "$pkg: ${RED}missing${NC}"
done
