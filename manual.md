#!/bin/bash

# Set up the environment
conda create -n opencv python=3.10 -y
conda activate opencv

# Install required dependencies
sudo apt-get update
sudo apt-get install -y build-essential cmake git libgtk2.0-dev pkg-config libavcodec-dev libavformat-dev libswscale-dev libv4l-dev
sudo apt-get install -y libatlas-base-dev gfortran libhdf5-dev protobuf-compiler
sudo apt-get install -y libgl1-mesa-glx libglib2.0-dev libgtk2.0-dev libgtk-3-dev
sudo apt-get install -y libjpeg-dev libpng-dev libtiff-dev libatlas-base-dev
sudo apt-get install -y gfortran liblapack-dev libopenblas-dev libopencv-dev
sudo apt-get install -y libgl1-mesa-glx libsm6 libxext6 libxrender-dev
sudo apt-get install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev

# Download and build OpenCV
git clone https://github.com/opencv/opencv.git
git clone https://github.com/opencv/opencv_contrib.git

cd opencv
mkdir build && cd build

cmake -D CMAKE_BUILD_TYPE=RELEASE \
      -D CMAKE_INSTALL_PREFIX=/usr/local \
      -D OPENCV_EXTRA_MODULES_PATH=../../opencv_contrib/modules \
      -D ENABLE_NEON=ON \
      -D ENABLE_VFPV3=ON \
      -D WITH_CUDA=ON \
      -D WITH_CUDNN=ON \
      -D CUDA_ARCH_BIN=5.3 \
      -D CUDA_ARCH_PTX="" \
      -D WITH_GSTREAMER=ON \
      -D WITH_LIBV4L=ON \
      -D WITH_QT=OFF \
      -D WITH_OPENGL=ON \
      -D BUILD_EXAMPLES=OFF ..

make -j4
sudo make install

# Verify installation
python -c "import cv2; print(cv2.__version__)"