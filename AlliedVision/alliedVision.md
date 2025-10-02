# 1800 U-319m (Monochrome) Setup

## Camera Specifications

| Feature                     | Specification |
|-------------------------------|----------------|
| Maximum frame rate            | 54 fps (at ≥200 MByte/s) |
| Exposure time                 | 26 μs to 10 s (at 200 MByte/s) |
| Exposure modes                | Timed, TriggerControlled, TriggerWidth |
| Gain                          | 0 dB to 48 dB (0.1 dB increments) |
| Digital binning               | Horizontal: 1–8 columns; Vertical: 1–8 rows |
| Multiple ROI (H × V)          | Free |
| Image buffer (RAM)            | 256 KByte |
| Non-volatile memory (Flash)   | 1024 KByte |
| GPIOs                         | 4 programmable |
| - Direct inputs (push-pull)   | 0–5.5 VDC |
| - Direct outputs (push-pull)  | 0–3.3 VDC at 12 mA |

---

## 1. Install Vimba SDK on Linux
Download the tar archiv from [website](https://www.alliedvision.com/en/products/software/vimba-x-sdk).

Extract the setup archive:

```commandline
cd Downloads
sudo tar -xzf VimbaX_Setup-2025-2-Linux64.tar.gz -C /opt
```

Install the GenTL path:
```commandline
cd ..
cd /opt/VimbaX_2025-2/cti
sudo ./Install_GenTL_Path.sh
sudo reboot
```
Check installation (You should see directories like bin, cti, doc, etc.):
```commandline
ls /opt/VimbaX_2025-2
```
## 2. Install Python API

Activate your virtual environment and install the wheel file:
```commandline
pip3 install /opt/VimbaX_2025-2/api/python/vmbpy-1.1.1-py3-none-manylinux_2_27_x86_64.whl
```