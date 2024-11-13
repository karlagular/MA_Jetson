import torch

# Check if CUDA is available
if torch.cuda.is_available():
    device = torch.device("cuda")  # Use GPU if available
    print(f"CUDA is available. Using device: {torch.cuda.get_device_name(device)}")
    
    # Create a tensor on the GPU
    x = torch.randn(3, 3, device=device)
    print("Tensor on GPU:", x)
    
    # Perform a simple operation on the GPU
    y = x * 2
    print("Tensor after operation:", y)
    
    # Move tensor back to CPU
    y_cpu = y.cpu()
    print("Tensor moved to CPU:", y_cpu)
else:
    print("CUDA is not available. Using CPU.")
    # Fall back to CPU if CUDA is not available
    x = torch.randn(3, 3)
    print("Tensor on CPU:", x)
