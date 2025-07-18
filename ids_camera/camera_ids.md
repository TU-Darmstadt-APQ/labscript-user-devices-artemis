[VIMBA](https://github.com/fretchen/synqs_devices/blob/master/MakoCamera/blacs_workers.py)
# IDS Cameras (UI-5240SE-GL-Rev.2)

## Install IDS Software Suite
To be able to use new IDS peak, you need to have IDS Software SUite >4.95 to be installed.
If you already have the suite and want to upgrade it, make sure that the old versions are deleted first. 

NOTE: To be able to access Software Suite, you must be authorized with ids account.
The readme installation guide you can find here: [readme.html](https://de.ids-imaging.com/files/downloads/ids-software-suite/readme/readme-ids-software-suite-linux-4.96.1_EN.html)

Note: before executing bash scripts you may need to make them executable:
`chmod +x ./install_ids_soft_suite.sh`, `chmod +x ./check_dep.sh`

### Step-by-step installation
1. Download deb packages from website
2. Install dependencies:
```bash
./check_dep.sh
```
3. Install the package via dpkg
```bash
./install_ids_soft_suite.sh 
```

### First run
0. `ps -p 1 -o comm=` --> systemd?
1. After installation, you may start the uEye daemons separately with systemd by typing:
[user@pc]$ sudo systemctl start ueyeethdrc
[user@pc]$ sudo systemctl start ueyeusbdrc
If your system does not support systemd yet, you can use the following commands:
[user@pc]$ sudo /etc/init.d/ueyeethdrc start
[user@pc]$ sudo /etc/init.d/ueyeusbdrc start
Before you stop the uEye daemons, make sure that there are no connections to it:
[user@pc]$ sudo systemctl stop ueyeethdrc
[user@pc]$ sudo systemctl stop ueyeusbdrc
Or without systemd:
[user@pc]$ sudo /etc/init.d/ueyeethdrc stop
[user@pc]$ sudo /etc/init.d/ueyeusbdrc stop

2. To check if the deamons for enthernet cameras are active:
`sudo /opt/ids/ueye/ueyeusbdemo`

