
# IDS Cameras (UI-5240SE-GL-Rev.2)

## Install IDS Software Suite
To be able to use new IDS peak, you need to have IDS Software SUite >4.95 to be installed.
If you already have the suite and want to upgrade it, make sure that the old versions are deleted first. 

NOTE: To be able to access Software Suite, you must be authorized with ids account.
The readme installation guide you can find here: [readme.html](https://de.ids-imaging.com/files/downloads/ids-software-suite/readme/readme-ids-software-suite-linux-4.96.1_EN.html)

Note: before executing bash scripts you may need to make them executable:
`chmod +x ./install_suite.sh`, `chmod +x ./check_suite_deps.sh`, ` chmod +x ./check_peak_deps.sh`.

### Step-by-step installation
1. Download deb packages from [website](https://de.ids-imaging.com/download-details/AB.0010.1.48702.23.html?os=linux&version=&bus=64&floatcalc=)
2. Install software suite dependencies:
```bash
./check_suite_deps.sh
```
3. Install Software Suite packages
```bash
./install_suite.sh 
```

### First run
0. `ps -p 1 -o comm=` --> systemd?
1. After installation, you may start the uEye daemons separately with systemd by typing:
```bash 
[user@pc]$ sudo systemctl start ueyeethdrc
[user@pc]$ sudo systemctl start ueyeusbdrc
# If your system does not support systemd yet, you can use the following commands:
[user@pc]$ sudo /etc/init.d/ueyeethdrc start
[user@pc]$ sudo /etc/init.d/ueyeusbdrc start
# Before you stop the uEye daemons, make sure that there are no connections to it:
[user@pc]$ sudo systemctl stop ueyeethdrc
[user@pc]$ sudo systemctl stop ueyeusbdrc
# Or without systemd:
[user@pc]$ sudo /etc/init.d/ueyeethdrc stop
[user@pc]$ sudo /etc/init.d/ueyeusbdrc stop
```
2. To check if the daemons for ethernet cameras are active:
`sudo /opt/ids/ueye/ueyeusbdemo`


## Install IDS Peak
[Readme](https://de.ids-imaging.com/files/downloads/ids-peak/readme/ids-peak-linux-readme-2.17.0_EN.html)

1. Check and install dependencies
```bash
./check_peak_deps.sh
```

2. Install IDS Peak
```bash
sudo apt install ~/Downloads/ids-peak-with-ueyetl_2.17.0.0-488_amd64.deb
```

3. Install the IDS Peak Python bindings (First, ensure pip is installed: `sudo apt install python3-pip`)
```bash
python -m pip install ids_peak_ipl
python -m pip install ids_peak
python -m pip install ids_peak_afl
```

If you cannot install system-wide (e.g. error: externally-managed-environment), use a virtual environment.

If you installed labscript using the 
[TU-Darmstadt-AQP/labscript-install](https://github.com/TU-Darmstadt-APQ/labscript-install)
script, a virtual environment already exists under the labscript-suite folder.

Activate it:
```bash
cd ~/labscript-suite
source venv/bin/activate
```
Now you can install the packages inside the virtual environment:
``` bash
pip install ids-peak ids-peak-ipl ids-peak-afl 
```

## Run IDS Peak

NOTICE! Some Linux distributions disconnect network interfaces 
when no network device is connected to them (e.g. a switch, a camera) 
and reconnect them as soon as a device gets connected to them. 
This means that you have to **restart the IDS peak Cockpit** when a
camera is added directly to a network port after the IDS peak 
Cockpit has started because the transport layer only searches for
new network interfaces during **initialization**.

# Configure camera

`sudo ip addr add 0.0.0.0/0 dev <interface>` if no camera in list in IDS Camera Manager.

# Prototyping

Python libraries:
```commandline
pip install pyueye
```