"""Facilitator only: convert the pretrained chest X-ray model to ONNX (needs PyTorch).

Participants never run this. It produces cxr_densenet121.onnx, which lets laptops compute
image features with onnxruntime alone (about 15 MB to install, instead of 2-3 GB for PyTorch).

    uv venv --python 3.12 fenv
    uv pip install --python fenv torch --index-url https://download.pytorch.org/whl/cpu
    uv pip install --python fenv torchxrayvision onnx onnxruntime==1.23.2
    fenv/bin/python export_onnx.py

The model is torchxrayvision's DenseNet-121 "all" (Cohen et al., https://github.com/mlmed/torchxrayvision,
Apache-2.0 code), trained on public chest X-ray datasets that do not include the TB sets used here.
"""
import numpy as np
import onnxruntime as ort
import torch
import torchxrayvision as xrv

model = xrv.models.DenseNet(weights="densenet121-res224-all").eval()


class Features(torch.nn.Module):
    """Return the 1024 numbers the network computes just before its final layer."""

    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, x):
        return self.m.features2(x)


net = Features(model).eval()
x = torch.rand(2, 1, 224, 224) * 2048 - 1024          # the model expects pixels scaled to [-1024, 1024]
torch.onnx.export(net, x, "cxr_densenet121.onnx", input_names=["image"], output_names=["features"],
                  dynamic_axes={"image": {0: "batch"}, "features": {0: "batch"}}, opset_version=17, dynamo=False)

# check the ONNX copy gives the same answer as PyTorch
diff = np.abs(net(x).detach().numpy() - ort.InferenceSession("cxr_densenet121.onnx").run(None, {"image": x.numpy()})[0]).max()
print(f"exported cxr_densenet121.onnx; max difference from PyTorch: {diff:.1e}")
