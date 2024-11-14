# Comments and Text written by ChatGPT, I felt Lazy.

# Jetson Nano/Orin Jetpack 6.0 Setup Guide

This guide outlines the step-by-step process for setting up the Jetson Nano or Jetson Orin with Jetpack 6.0, configuring an environment optimized for machine learning and computer vision tasks. Below, you’ll find instructions on installing necessary software, setting up a Python environment, and configuring the system to use SSDs for better performance.

## Install Conda

Conda is a powerful package manager and environment management tool widely used in data science and AI development. Follow these commands to install Miniconda on your Jetson device:

```bash
cd Downloads/   # Navigate to the Downloads directory.
sudo apt upgrade  # Update and upgrade your system packages.
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh  # Download the Miniconda installer for ARM architecture.
chmod +x Miniconda3-latest-Linux-aarch64.sh  # Make the installer executable.
./Miniconda3-latest-Linux-aarch64.sh  # Run the installer.
cd ~  # Return to the home directory.
```
## Install code

```bash
cd Downloads/
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
sudo install -o root -g root -m 644 packages.microsoft.gpg /etc/apt/trusted.gpg.d/
sudo sh -c 'echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/trusted.gpg.d/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list'
rm -f packages.microsoft.gpg
sudo apt install apt-transport-https
sudo apt update
sudo apt install code
```

## Create Conda Environment

To create an isolated environment specifically for AI and CV tasks:

```bash
conda create --name syntcv2inf python==3.10.12  # Create a new environment named 'syntcv2inf' with Python 3.10.12.
conda activate syntcv2inf  # Activate the environment.
```

## Install Ultralytics and Torch/Torchvision

The Ultralytics library (used for YOLO models) and PyTorch are essential for deep learning applications.

```bash
pip install ultralytics[export]  # Install Ultralytics for advanced machine learning model usage.
sudo reboot  # Reboot the system to ensure all changes take effect.

sudo apt-get install libopenmpi-dev libopenblas-base libomp-dev -y  # Install necessary libraries for PyTorch.
pip install https://github.com/ultralytics/assets/releases/download/v0.0.0/torch-2.3.0-cp310-cp310-linux_aarch64.whl  # Install a specific version of Torch.
pip install https://github.com/ultralytics/assets/releases/download/v0.0.0/torchvision-0.18.0a0+6043bc2-cp310-cp310-linux_aarch64.whl  # Install Torchvision.
```

## Install ONNX Runtime

ONNX Runtime is essential for running machine learning models efficiently on NVIDIA hardware.

```bash
wget https://nvidia.box.com/shared/static/48dtuob7meiw6ebgfsfqakc9vse62sg4.whl -O onnxruntime_gpu-1.18.0-cp310-cp310-linux_aarch64.whl  # Download the ONNX Runtime wheel.
pip install onnxruntime_gpu-1.18.0-cp310-cp310-linux_aarch64.whl  # Install the ONNX Runtime wheel.
```

## Reinstall Numpy

Reinstalling Numpy ensures compatibility with your specific version of Python and other packages.

```bash
pip install numpy==1.23.5  # Install a compatible version of Numpy.
```

## Install OpenCV Dependencies

OpenCV is a critical library for computer vision projects. Install the required dependencies:

```bash
sudo apt-get update  # Update package lists.
sudo apt-get install -y libgtk2.0-dev pkg-config  # Install GTK 2.0 development libraries.
sudo apt-get install -y libgtk-3-dev  # Install GTK 3 development libraries.
```

## Setup OpenCV Python

### Define Environment Variables

Set up environment variables for building OpenCV:

```bash
CONDA_PREFIX=~/miniconda3/envs/syntcv2inf  # Set the path to the Conda environment.
PYTHON_VERSION=3.10.12  # Specify the Python version.
OPENCV_VER="master"  # Choose the OpenCV version (latest master branch).
TMPDIR=$(mktemp -d)  # Create a temporary directory for building.
```

### Set CMake Flags and Paths

Ensure CMake is configured with the right paths:

```bash
export CPLUS_INCLUDE_PATH=$CONDA_PREFIX/lib/python$PYTHON_VERSION  # Set include path for C++.
```

### Clone and Build OpenCV-Python

Download and compile OpenCV with Python bindings:

```bash
cd "${TMPDIR}"  # Navigate to the temporary build directory.
git clone --branch ${OPENCV_VER} --depth 1 --recurse-submodules --shallow-submodules https://github.com/opencv/opencv-python.git opencv-python-${OPENCV_VER}  # Clone the OpenCV-Python repository.
cd opencv-python-${OPENCV_VER}  # Enter the cloned directory.

export CMAKE_ARGS="-G Ninja -DWITH_GSTREAMER=ON -DWITH_QT=ON -DWITH_GTK=ON"  # Set CMake arguments for build configuration.
export PYTHON3_LIBRARY=$CONDA_PREFIX/lib/libpython$PYTHON_VERSION  # Define Python library path.
export PYTHON3_INCLUDE_DIR=$CONDA_PREFIX/include/python$PYTHON_VERSION  # Define Python include path.
export PYTHON3_EXECUTABLE=$CONDA_PREFIX/bin/python$PYTHON_VERSION  # Set the Python executable path.
export PYTHON3_PACKAGES_PATH=$CONDA_PREFIX/lib/python$PYTHON_VERSION/site-packages  # Set packages path.
export OPENCV_EXTRA_MODULES_PATH=../../opencv_contrib/modules  # Set additional OpenCV module paths.

python3 -m pip wheel . --verbose  # Build the OpenCV Python wheel.
```

### Install OpenCV Wheel

Once the build is complete:

```bash
python3 -m pip install opencv_python*.whl  # Install the generated OpenCV wheel.
```

## Test OpenCV

Verify that OpenCV is correctly installed by running:

### Python Script

```python
import cv2
print(cv2.getBuildInformation())  # Print OpenCV build information to confirm installation.
```

## Check YOLO

Ensure YOLO is functioning as expected:

### Python Script

```python
from ultralytics import YOLO
# Load a YOLO11n PyTorch model
model = YOLO("yolo11n.pt")
# Run inference
results = model("https://ultralytics.com/images/bus.jpg")
```

## Install PyQt5

PyQt5 is necessary for GUI-based applications:

```bash
pip3 install pyqt5 --config-settings --confirm-license= --verbose  # Install PyQt5 with verbose output.
```

## First Steps Done!

You have successfully completed the primary setup for your Jetson Nano/Orin device. Below are detailed steps for optimizing your setup by migrating your system to an SSD.

## Detailed Steps for Migration:

Start by ensuring you have a text editor for configuration:

```bash
sudo apt-get install nano  # Install the Nano text editor.
```

### Clone the SD Card to the SSD

Clone your SD card to an SSD for improved performance using `dd`:

```bash
sudo dd if=/dev/mmcblk0 of=/dev/nvme0n1 bs=4M status=progress  # Perform a sector-by-sector copy.
```

### Verify and Adjust Partition Layout

After cloning, inspect the partition layout:

```bash
sudo fdisk -l /dev/nvme0n1  # List the partitions on the SSD.
```

If needed, use `gparted` or `parted` to expand the root partition to use the full SSD capacity.

### Update the Bootloader Configuration

Ensure the Jetson device boots from the SSD:

1. Open and edit the `extlinux.conf` file:

```bash
sudo nano /boot/extlinux/extlinux.conf  # Edit the boot configuration file.
```

2. Modify the `root` parameter to point to the SSD:

```text
APPEND ... root=/dev/nvme0n1p1 ...  # Replace the root device with the SSD identifier.
```

## Install GParted for GUI Partition Management

```bash
sudo apt-get install gparted  # Install GParted.
sudo gparted  # Launch GParted GUI.
```

## Shutdown

After making these changes, power down the system:

```bash
sudo shutdown  # Shut down the system.
```

Remove the SD card and reboot to start using your system with the SSD.

