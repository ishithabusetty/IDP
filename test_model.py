import numpy as np

mean = np.load("IDP_Fall_Detection/norm_mean.npy")
std = np.load("IDP_Fall_Detection/norm_std.npy")

print("Mean shape:", mean.shape)
print("Std shape :", std.shape)

print("\nMean:")
print(mean)

print("\nStd:")
print(std)