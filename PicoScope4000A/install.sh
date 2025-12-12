# 1. Import public key (only once, no need to repeat)
sudo bash -c 'wget -O- https://labs.picotech.com/Release.gpg.key | gpg --dearmor > /usr/share/keyrings/picotech-archive-keyring.gpg'

# 2. Configure your system repository
sudo bash -c 'echo "deb [signed-by=/usr/share/keyrings/picotech-archive-keyring.gpg] https://labs.picotech.com/picoscope7/debian/ picoscope main" >/etc/apt/sources.list.d/picoscope7.list'

# 3. Update package manager cache
sudo apt-get update

# 4. Installing drivers only
sudo apt-get install libps4000a

