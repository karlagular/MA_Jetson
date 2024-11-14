# Jetson Nano/Orin Jetpack 6.0 Setup Guide

## Install Conda
```bash
cd Downloads/
sudo apt upgrade
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh
chmod +x Miniconda3-latest-Linux-aarch64.sh
./Miniconda3-latest-Linux-aarch64.sh
cd ~
```

## Create Conda Environment
```bash
conda create --name syntcv2inf python==3.10.12
conda activate syntcv2inf
```

## Install Ultralytics and Torch/Torchvision
```bash
pip install ultralytics[export]
sudo reboot

sudo apt-get install libopenmpi-dev libopenblas-base libomp-dev -y
pip install https://github.com/ultralytics/assets/releases/download/v0.0.0/torch-2.3.0-cp310-cp310-linux_aarch64.whl
pip install https://github.com/ultralytics/assets/releases/download/v0.0.0/torchvision-0.18.0a0+6043bc2-cp310-cp310-linux_aarch64.whl
```

## Install ONNX Runtime
```bash
wget https://nvidia.box.com/shared/static/48dtuob7meiw6ebgfsfqakc9vse62sg4.whl -O onnxruntime_gpu-1.18.0-cp310-cp310-linux_aarch64.whl
pip install onnxruntime_gpu-1.18.0-cp310-cp310-linux_aarch64.whl
```

## Reinstall Numpy
```bash
pip install numpy==1.23.5
```

## Install OpenCV Dependencies
```bash
sudo apt-get update
sudo apt-get install -y libgtk2.0-dev pkg-config
sudo apt-get install -y libgtk-3-dev
```

## Setup OpenCV Python

### Define Environment Variables
```bash
CONDA_PREFIX=~/miniconda3/envs/syntcv2inf
PYTHON_VERSION=3.10.12
OPENCV_VER="master"
TMPDIR=$(mktemp -d)
```

### Set CMake Flags and Paths
```bash
export CPLUS_INCLUDE_PATH=$CONDA_PREFIX/lib/python$PYTHON_VERSION
```

### Clone and Build OpenCV-Python
```bash
cd "${TMPDIR}"
git clone --branch ${OPENCV_VER} --depth 1 --recurse-submodules --shallow-submodules https://github.com/opencv/opencv-python.git opencv-python-${OPENCV_VER}
cd opencv-python-${OPENCV_VER}

export CMAKE_ARGS="-G Ninja -DWITH_GSTREAMER=ON -DWITH_QT=ON -DWITH_GTK=ON"
export PYTHON3_LIBRARY=$CONDA_PREFIX/lib/libpython$PYTHON_VERSION
export PYTHON3_INCLUDE_DIR=$CONDA_PREFIX/include/python$PYTHON_VERSION
export PYTHON3_EXECUTABLE=$CONDA_PREFIX/bin/python$PYTHON_VERSION
export PYTHON3_PACKAGES_PATH=$CONDA_PREFIX/lib/python$PYTHON_VERSION/site-packages
export OPENCV_EXTRA_MODULES_PATH=../../opencv_contrib/modules

python3 -m pip wheel . --verbose
```

### Install OpenCV Wheel
```bash
python3 -m pip install opencv_python*.whl
```

## Test OpenCV

### Python Script
```python
import cv2
print(cv2.getBuildInformation())
```

## Check YOLO

### Python Script
```python
from ultralytics import YOLO 
# Load a YOLO11n PyTorch model 
model = YOLO("yolo11n.pt") 
# Run inference 
results = model("https://ultralytics.com/images/bus.jpg")
```

## Install PyQt5
```bash
pip3 install pyqt5 --config-settings --confirm-license= --verbose
```

## First Steps Done!

## Detailed Steps for Migration:

```bash
sudo apt-get install nano
```

Install to SD, follow guide to copy, go into folder in SSD change extlinux.conf, download gpartet, unmount SSD, make partition bigger, shutdown, remove SD and be Happy

### Clone the SD Card to the SSD
Use `dd` or `rsync` as outlined before to clone your SD card. Since Jetson devices may have boot partitions that require special handling, a sector-by-sector copy (`dd`) is generally preferable:

```bash
sudo dd if=/dev/mmcblk0 of=/dev/nvme0n1 bs=4M status=progress
```

### Verify and Adjust Partition Layout
After cloning, check the partition structure using `lsblk` or `fdisk`:

```bash
sudo fdisk -l /dev/nvme0n1
```

Ensure that the boot and root partitions were copied successfully. If you need to expand the root partition to utilize the entire space of the SSD, use `gparted` or `parted` as described earlier.

### Update the Bootloader Configuration
The Jetson Orin Nano might need boot configuration adjustments:

1. Check for the `extlinux.conf` file, typically found under `/boot/extlinux/extlinux.conf`.
2. Update the `root` parameter in `extlinux.conf` to point to your SSD. Replace `/dev/mmcblk0p1` or similar references with `/dev/nvme0n1p1` (or the specific partition identifier of the root partition on the SSD).

```bash
sudo nano /boot/extlinux/extlinux.conf
```

Ensure that the `APPEND` line references the correct device:

```text
APPEND ... root=/dev/nvme0n1p1 ...
```

## install geparted and go into GUI

```bash
sudo apt-get install gparted
sudo gparted
```

## shutdown 
After shutdown remove sd and reboot

```bash
sudo shutdown
```


