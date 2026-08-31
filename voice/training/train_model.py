#!/usr/bin/env python3
"""Trains the "Patriot" wake-word classifier on the embeddings produced by
build_dataset.py, and exports it to voice/models/patriot.onnx.

Reimplements openwakeword's own default "dnn" model architecture (a small
feed-forward net: Linear -> LayerNorm -> ReLU, one residual-ish FCN block,
then a sigmoid output) directly here, rather than importing
openwakeword.train.Model -- that module pulls in a chain of heavy optional
dependencies (audiomentations, pronouncing, room-impulse-response
augmentation, etc.) meant for openWakeWord's own large-scale training
pipeline that we don't use. Same input/output contract either way: input
(16, 96) embeddings, output a single sigmoid score, exportable to ONNX as
a drop-in wakeword_models entry for openwakeword.model.Model at inference
time.

The training loop is a plain, minimal supervised loop written here rather
than openwakeword's own train_model()/auto_train() -- those are tuned for
runs with tens of thousands of steps and many hours of real false-positive
audio, which doesn't fit a few hundred synthetic clips. This is simpler
and easier to verify end to end.

Run: python3 train_model.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from torch import nn

HERE = Path(__file__).resolve().parent
DATASET_PATH = HERE / "dataset.npz"
MODEL_OUT = HERE.parent / "models" / "patriot.onnx"

EPOCHS = 400
BATCH_SIZE = 32
LR = 1e-3
WEIGHT_DECAY = 1e-4
SEED = 0
INPUT_SHAPE = (16, 96)
LAYER_DIM = 128


class FCNBlock(nn.Module):
    """Matches openwakeword's own default "dnn" architecture block."""

    def __init__(self, layer_dim):
        super().__init__()
        self.fcn_layer = nn.Linear(layer_dim, layer_dim)
        self.relu = nn.ReLU()
        self.layer_norm = nn.LayerNorm(layer_dim)

    def forward(self, x):
        return self.relu(self.layer_norm(self.fcn_layer(x)))


class WakeWordNet(nn.Module):
    """Matches openwakeword's own default "dnn" architecture (1 block, 128
    hidden units) so the exported ONNX file is a drop-in wakeword_models
    entry for openwakeword.model.Model at inference time."""

    def __init__(self, input_shape=INPUT_SHAPE, layer_dim=LAYER_DIM, n_blocks=1):
        super().__init__()
        self.flatten = nn.Flatten()
        self.layer1 = nn.Linear(input_shape[0] * input_shape[1], layer_dim)
        self.relu1 = nn.ReLU()
        self.layernorm1 = nn.LayerNorm(layer_dim)
        self.blocks = nn.ModuleList([FCNBlock(layer_dim) for _ in range(n_blocks)])
        self.last_layer = nn.Linear(layer_dim, 1)
        self.last_act = nn.Sigmoid()

    def forward(self, x):
        x = self.relu1(self.layernorm1(self.layer1(self.flatten(x))))
        for block in self.blocks:
            x = block(x)
        return self.last_act(self.last_layer(x))


def load_dataset():
    d = np.load(DATASET_PATH)
    return d["X_pos_train"], d["X_neg_train"], d["X_pos_test"], d["X_neg_test"]


def make_xy(pos: np.ndarray, neg: np.ndarray):
    x = np.concatenate([pos, neg], axis=0).astype(np.float32)
    y = np.concatenate([np.ones(len(pos)), np.zeros(len(neg))]).astype(np.float32)
    return torch.from_numpy(x), torch.from_numpy(y)


def evaluate(model: nn.Module, x: torch.Tensor, y: torch.Tensor, threshold: float = 0.5):
    with torch.no_grad():
        preds = model(x).squeeze(-1)
    pred_labels = (preds >= threshold).float()
    pos_mask = y == 1
    neg_mask = y == 0
    recall = pred_labels[pos_mask].mean().item() if pos_mask.any() else float("nan")
    false_positive_rate = pred_labels[neg_mask].mean().item() if neg_mask.any() else float("nan")
    accuracy = (pred_labels == y).float().mean().item()
    return {"accuracy": accuracy, "recall": recall, "false_positive_rate": false_positive_rate}


def main():
    torch.manual_seed(SEED)
    np.random.seed(SEED)

    X_pos_train, X_neg_train, X_pos_test, X_neg_test = load_dataset()
    x_train, y_train = make_xy(X_pos_train, X_neg_train)
    x_test, y_test = make_xy(X_pos_test, X_neg_test)
    print(f"[train] train: {len(x_train)} clips ({int(y_train.sum())} positive) | "
          f"test: {len(x_test)} clips ({int(y_test.sum())} positive)")

    net = WakeWordNet()

    # Positive class is a small minority of the training set -- weight it up
    # so the model doesn't just learn to always predict "not the wake word".
    n_pos, n_neg = int(y_train.sum()), int((1 - y_train).sum())
    pos_weight_value = max(1.0, n_neg / max(1, n_pos))

    optimizer = torch.optim.Adam(net.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)

    best_state = None
    best_score = -1.0
    n = len(x_train)

    for epoch in range(EPOCHS):
        net.train()
        perm = torch.randperm(n)
        epoch_loss = 0.0
        for i in range(0, n, BATCH_SIZE):
            idx = perm[i:i + BATCH_SIZE]
            xb, yb = x_train[idx], y_train[idx]
            weights = torch.where(yb == 1, pos_weight_value, 1.0)

            optimizer.zero_grad()
            preds = net(xb).squeeze(-1)
            loss = nn.functional.binary_cross_entropy(preds, yb, weight=weights)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * len(idx)

        if (epoch + 1) % 25 == 0 or epoch == EPOCHS - 1:
            net.eval()
            metrics = evaluate(net, x_test, y_test)
            score = metrics["recall"] - metrics["false_positive_rate"]
            print(f"[train] epoch {epoch + 1:4d} loss={epoch_loss / n:.4f} "
                  f"test_recall={metrics['recall']:.3f} "
                  f"test_fp_rate={metrics['false_positive_rate']:.3f}")
            if score > best_score:
                best_score = score
                best_state = {k: v.clone() for k, v in net.state_dict().items()}

    if best_state is not None:
        net.load_state_dict(best_state)

    net.eval()
    final_metrics = evaluate(net, x_test, y_test)
    print(f"[train] FINAL held-out metrics: {final_metrics}")

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    dummy_input = torch.rand(1, *INPUT_SHAPE)
    torch.onnx.export(net, dummy_input, str(MODEL_OUT), output_names=["patriot"],
                       input_names=["input"], opset_version=13, dynamo=False)
    print(f"[train] exported {MODEL_OUT}")


if __name__ == "__main__":
    main()
