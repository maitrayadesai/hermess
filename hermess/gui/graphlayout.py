# © 2024-2026 ETH Zurich
# Original author: Milos Katanic
# Simulation-only fork & maintainer: Maitraya Avadhut Desai
#
# Licensed under the GNU General Public License v3.0 or later;
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     https://www.gnu.org/licenses/gpl-3.0.en.html
#
# This software is distributed "AS IS", WITHOUT WARRANTY OF ANY KIND,
# express or implied. See the License for specific language governing
# permissions and limitations under the License.
#
# Simulation-only fork of PowerDynamicEstimator
# (https://doi.org/10.5905/ethz-1007-842); dynamic state estimation removed.
# For inquiries, contact: mdesai@ethz.ch

"""Deterministic force-directed layout for the one-line diagram.

The system files carry no coordinates, so bus positions are computed with a
small Fruchterman-Reingold iteration. The seed is fixed: the same system
always lays out the same way, and the user can drag nodes afterwards.
"""

from __future__ import annotations

import numpy as np


def outward_directions(pos: np.ndarray, edges: "list[tuple[int, int]]") -> np.ndarray:
    """Per-node unit vector into the locally empty sector: away from the
    node's neighbors, which is where labels and device glyphs fit without
    landing on lines or other buses. Falls back to the perpendicular of the
    first edge for nodes whose neighbors cancel out (straight chains), and to
    straight up for isolated nodes."""
    n = pos.shape[0]
    acc = np.zeros((n, 2))
    first_edge_unit = {}
    for i, j in edges:
        span = pos[j] - pos[i]
        norm = np.linalg.norm(span)
        if norm < 1e-9:
            continue
        unit = span / norm
        acc[i] += unit
        acc[j] -= unit
        first_edge_unit.setdefault(i, unit)
        first_edge_unit.setdefault(j, -unit)
    out = np.zeros((n, 2))
    for i in range(n):
        norm = np.linalg.norm(acc[i])
        if norm > 1e-6:
            out[i] = -acc[i] / norm
        elif i in first_edge_unit:
            unit = first_edge_unit[i]
            out[i] = np.array([-unit[1], unit[0]])  # perpendicular
        else:
            out[i] = np.array([0.0, 1.0])
    return out


def spring_layout(
    n: int,
    edges: "list[tuple[int, int]]",
    seed: int = 7,
    iterations: int = 300,
) -> np.ndarray:
    """Positions (n, 2) in roughly the unit box for ``n`` nodes and edge pairs."""
    if n == 0:
        return np.zeros((0, 2))
    rng = np.random.default_rng(seed)
    pos = rng.uniform(-0.5, 0.5, (n, 2))
    if n == 1:
        return pos

    k = 1.0 / np.sqrt(n)  # ideal pairwise distance
    edge_idx = np.array(edges, dtype=int).reshape(-1, 2)
    temperature = 0.1

    for _ in range(iterations):
        delta = pos[:, None, :] - pos[None, :, :]
        dist = np.linalg.norm(delta, axis=-1)
        np.fill_diagonal(dist, 1.0)
        dist = np.maximum(dist, 1e-6)

        # Repulsion between all pairs, attraction along edges.
        force = (k**2 / dist**2)[:, :, None] * delta
        displacement = force.sum(axis=1)
        if edge_idx.size:
            span = pos[edge_idx[:, 0]] - pos[edge_idx[:, 1]]
            span_len = np.maximum(np.linalg.norm(span, axis=-1), 1e-6)
            pull = (span_len / k)[:, None] * span / span_len[:, None]
            np.add.at(displacement, edge_idx[:, 0], -pull)
            np.add.at(displacement, edge_idx[:, 1], pull)

        length = np.maximum(np.linalg.norm(displacement, axis=-1), 1e-6)
        pos += displacement / length[:, None] * np.minimum(length, temperature)[:, None]
        temperature *= 0.98

    # Normalize into the unit box, preserving the aspect ratio.
    pos -= pos.min(axis=0)
    extent = max(pos.max(), 1e-6)
    pos /= extent

    # Even out the packing: FR leaves dense clusters in large graphs, and the
    # labels and device glyphs are drawn at fixed pixel size, so any pair
    # closer than a fraction of the mean spacing is pushed apart until the
    # whole layout keeps air. Runs in the final (normalized) units and skips
    # the rescale afterwards, so the separation is not squeezed away again.
    # Deterministic (no randomness involved).
    d_min = 0.72 / np.sqrt(n)
    with np.errstate(invalid="ignore"):
        for _ in range(150):
            delta = pos[:, None, :] - pos[None, :, :]
            dist = np.linalg.norm(delta, axis=-1)
            np.fill_diagonal(dist, np.inf)
            close = dist < d_min
            if not close.any():
                break
            safe = np.maximum(dist, 1e-9)
            push = np.where(
                close[:, :, None],
                delta / safe[:, :, None] * (d_min - dist)[:, :, None] * 0.5,
                0.0,
            )
            pos += push.sum(axis=1)

    return pos - pos.min(axis=0)
